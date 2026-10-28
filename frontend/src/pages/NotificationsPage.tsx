import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ListRowSkeleton } from "../components/skeleton";
import { useSession } from "../lib/session";
import {
  fetchNotifications,
  type NotificationItem,
} from "../features/notifications/api";
import {
  clearNotificationsCache,
  readNotificationsCache,
  writeNotificationsCacheForUser,
} from "../features/notifications/notificationsCache";
import { spaLoginPath } from "../features/auth/api";
import { useConversationBackState } from "../lib/conversationBack";
import { spaHrefTo } from "../lib/spaHref";
import {
  isLatestRequest,
  isSameUserScope,
  nextRequestId,
} from "../lib/userScopedResult";
import { analytics } from "../lib/analytics/events";
import { PullToRefresh } from "../lib/usePullToRefresh";

function formatBadgeCount(n: number): string {
  if (n > 99) return "99+";
  return String(n);
}

function isAuthLostError(err: unknown): boolean {
  const status =
    err && typeof err === "object" && "status" in err
      ? Number((err as { status?: number }).status)
      : 0;
  if (status === 401 || status === 403) return true;
  const msg = err instanceof Error ? err.message : String(err);
  return /unauthorized|forbidden|not_authenticated|http_401|http_403/i.test(msg);
}

function NotificationRow({ item }: { item: NotificationItem }) {
  const conversationBackState = useConversationBackState({
    fromWaseWase: true,
  });
  const body = (
    <>
      <p className="notification-message">{item.message}</p>
      <time className="notification-time">{item.created_at}</time>
    </>
  );

  if (item.spa_path) {
    return (
      <Link
        to={spaHrefTo(item.spa_path)}
        state={conversationBackState}
        onClick={() => analytics.notificationOpened()}
      >
        {body}
      </Link>
    );
  }
  // Prefer in-SPA navigation when link is already under /app/
  if (item.link?.startsWith("/app/") || item.link === "/app" || item.link?.startsWith("/app?")) {
    const raw = item.link === "/app" ? "/" : item.link.replace(/^\/app/, "") || "/";
    return (
      <Link
        to={spaHrefTo(raw)}
        state={conversationBackState}
        onClick={() => analytics.notificationOpened()}
      >
        {body}
      </Link>
    );
  }
  if (item.link) {
    // Classic paths: Django redirects GET → /app/… when WASE_REACT_SPA is on
    return (
      <a href={item.link} onClick={() => analytics.notificationOpened()}>
        {body}
      </a>
    );
  }
  return <div className="notification-static">{body}</div>;
}

export function NotificationsPage() {
  const { me, loading: sessionLoading, refresh } = useSession();
  const navigate = useNavigate();
  const userId = me?.authenticated ? me.user?.id ?? null : null;
  const prevUserIdRef = useRef<number | null>(null);
  const userIdRef = useRef<number | null>(userId);
  const loadGenRef = useRef(0);
  const [items, setItems] = useState<NotificationItem[]>([]);
  const [pendingFollowRequests, setPendingFollowRequests] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const applyEntry = useCallback(
    (nextItems: NotificationItem[], nextPending: number) => {
      setItems(nextItems);
      setPendingFollowRequests(nextPending);
      setError(null);
    },
    []
  );

  const load = useCallback(
    async (
      mode: "initial" | "soft" | "revalidate" = "initial",
      signal?: AbortSignal,
      forUserId?: number
    ) => {
      const scopedUserId = forUserId ?? userId;
      if (scopedUserId == null) return false;
      const requestId = nextRequestId(loadGenRef);
      if (mode === "initial") {
        setLoading(true);
        setError(null);
      }
      try {
        const data = await fetchNotifications(mode !== "soft");
        if (signal?.aborted || !isLatestRequest(loadGenRef, requestId)) {
          return false;
        }
        if (!isSameUserScope(scopedUserId, userIdRef.current)) return false;
        const nextItems = data.notifications || [];
        const nextPending = Number(data.pending_follow_request_count || 0);
        applyEntry(nextItems, nextPending);
        writeNotificationsCacheForUser(userIdRef.current, {
          userId: scopedUserId,
          items: nextItems,
          pendingFollowRequests: nextPending,
          fetchedAt: Date.now(),
        });
        if (mode !== "soft") void refresh();
        return true;
      } catch (err) {
        if (signal?.aborted || !isLatestRequest(loadGenRef, requestId)) {
          return false;
        }
        if (!isSameUserScope(scopedUserId, userIdRef.current)) return false;
        if (isAuthLostError(err)) {
          clearNotificationsCache(scopedUserId);
        }
        if (mode !== "initial") return false;
        setError(err instanceof Error ? err.message : "load_failed");
        return false;
      } finally {
        if (
          mode === "initial" &&
          !signal?.aborted &&
          isLatestRequest(loadGenRef, requestId) &&
          isSameUserScope(scopedUserId, userIdRef.current)
        ) {
          setLoading(false);
        }
      }
    },
    [applyEntry, refresh, userId]
  );

  useEffect(() => {
    const previousUserId = prevUserIdRef.current;
    if (previousUserId != null && previousUserId !== userId) {
      clearNotificationsCache(previousUserId);
      setItems([]);
      setPendingFollowRequests(0);
    }
    if (userId == null) {
      clearNotificationsCache();
      setItems([]);
      setPendingFollowRequests(0);
    }
    prevUserIdRef.current = userId;
    userIdRef.current = userId;
  }, [userId]);

  useEffect(() => {
    if (sessionLoading) return;
    if (userId == null) {
      navigate(spaLoginPath("/app/notifications"), { replace: true });
      return;
    }
    const cached = readNotificationsCache(userId);
    if (cached) {
      applyEntry(cached.items, cached.pendingFollowRequests);
      setLoading(false);
    } else {
      setItems([]);
      setPendingFollowRequests(0);
      setLoading(true);
      setError(null);
    }
    const ac = new AbortController();
    void load(cached ? "revalidate" : "initial", ac.signal, userId);
    return () => ac.abort();
  }, [sessionLoading, userId, load, navigate, applyEntry]);

  const showSafeChrome = sessionLoading || userId == null;
  const showSkeleton = showSafeChrome || (loading && items.length === 0 && !error);
  const showEmpty = !error && !showSkeleton && items.length === 0;

  return (
    <div className="notifications-page" data-spa-page="通知">
      <PullToRefresh
        enabled={Boolean(me?.authenticated) && !showSafeChrome}
        onRefresh={async () => {
          if (!(await load("soft"))) throw new Error("refresh_failed");
        }}
      />
      <main className="main-inner">
        <Link
          className="follow-request-entry"
          to="/settings/follow-requests"
          aria-label={
            pendingFollowRequests > 0
              ? `フォローリクエスト、未処理${pendingFollowRequests}件`
              : "フォローリクエスト"
          }
        >
          <span className="follow-request-entry__label">フォローリクエスト</span>
          {pendingFollowRequests > 0 ? (
            <span className="follow-request-entry__badge" aria-hidden="true">
              {formatBadgeCount(pendingFollowRequests)}
            </span>
          ) : null}
          <span className="follow-request-entry__chevron" aria-hidden="true">
            ›
          </span>
        </Link>

        {error && items.length === 0 ? (
          <p className="empty-message">読み込みに失敗しました（{error}）</p>
        ) : showSkeleton ? (
          <ListRowSkeleton rows={6} />
        ) : showEmpty ? (
          <p className="empty-message">通知はまだありません。</p>
        ) : (
          <ul className="notification-list">
            {items.map((n) => (
              <li
                key={n.id}
                className={`notification-item${n.is_read ? "" : " is-unread"}`}
              >
                <NotificationRow item={n} />
              </li>
            ))}
          </ul>
        )}
      </main>
    </div>
  );
}
