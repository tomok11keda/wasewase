import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { clearNotificationsCache } from "../features/notifications/notificationsCache";
import { clearFollowListCache } from "../features/profile/followListCache";
import { clearOwnProfileCache } from "../features/profile/ownProfileCache";
import {
  fetchDmUnreadTotal,
  fetchMe,
  fetchNotificationUnread,
  type MeResponse,
} from "./api";

type SessionState = {
  loading: boolean;
  me: MeResponse | null;
  error: string | null;
  refresh: () => Promise<void>;
  setMeFromAuth: (me: MeResponse) => void;
};

const SessionContext = createContext<SessionState | null>(null);

const emptyMe: MeResponse = {
  authenticated: false,
  is_browse_mode: false,
  react_spa_enabled: true,
  user: null,
  unread_notifications: 0,
  dm_unread_total: 0,
  onboarding_required: false,
  onboarding_completed: true,
};

export function SessionProvider({ children }: { children: ReactNode }) {
  const [loading, setLoading] = useState(true);
  const [me, setMe] = useState<MeResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const prevUserIdRef = useRef<number | null>(null);

  const refresh = useCallback(async () => {
    try {
      const data = await fetchMe();
      setMe(data);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "me_error");
      setMe(emptyMe);
    } finally {
      setLoading(false);
    }
  }, []);

  const setMeFromAuth = useCallback((next: MeResponse) => {
    setMe(next);
    setLoading(false);
    setError(null);
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const sessionUserId =
    me?.authenticated && me.user?.id != null ? me.user.id : null;
  const prevUnreadRef = useRef<number | null>(null);

  useEffect(() => {
    const previousUserId = prevUserIdRef.current;
    if (previousUserId != null && previousUserId !== sessionUserId) {
      clearNotificationsCache(previousUserId);
      clearOwnProfileCache(previousUserId);
      clearFollowListCache();
    }
    if (previousUserId != null && sessionUserId == null) {
      clearNotificationsCache();
      clearOwnProfileCache();
      clearFollowListCache();
    }
    prevUserIdRef.current = sessionUserId;
    if (sessionUserId == null) prevUnreadRef.current = null;
  }, [sessionUserId]);

  useEffect(() => {
    if (sessionUserId == null) return;
    const unread = me?.unread_notifications ?? 0;
    const previousUnread = prevUnreadRef.current;
    if (previousUnread != null && unread > previousUnread) {
      clearNotificationsCache(sessionUserId);
    }
    prevUnreadRef.current = unread;
  }, [sessionUserId, me?.unread_notifications]);

  useEffect(() => {
    if (!me?.authenticated) return;
    const tick = async () => {
      try {
        const [n, d] = await Promise.all([
          fetchNotificationUnread(),
          fetchDmUnreadTotal(),
        ]);
        setMe((prev) =>
          prev
            ? { ...prev, unread_notifications: n, dm_unread_total: d }
            : prev
        );
      } catch {
        /* ignore badge errors */
      }
    };
    const id = window.setInterval(tick, 60000);
    return () => window.clearInterval(id);
  }, [me?.authenticated]);

  const value = useMemo(
    () => ({ loading, me, error, refresh, setMeFromAuth }),
    [loading, me, error, refresh, setMeFromAuth]
  );

  return (
    <SessionContext.Provider value={value}>{children}</SessionContext.Provider>
  );
}

export function useSession(): SessionState {
  const ctx = useContext(SessionContext);
  if (!ctx) {
    throw new Error("useSession must be used within SessionProvider");
  }
  return ctx;
}

/** Unauthenticated Browse Mode preview — no student-data API access. */
export function isBrowsePreview(me: MeResponse | null | undefined): boolean {
  return Boolean(me && !me.authenticated && me.is_browse_mode);
}
