import { useEffect, useRef, type ReactNode } from "react";
import { PostHogProvider } from "@posthog/react";
import { useSession } from "../session";
import {
  identifyUser,
  initPostHog,
  isPostHogConfigured,
  resetAnalytics,
} from "./client";

/**
 * Sync PostHog identity with Django session.
 * - Login / session restore → identify(internal user id)
 * - Logout / switch user → reset() then identify next user
 */
export function PostHogIdentitySync() {
  const { me, loading } = useSession();
  const lastUserIdRef = useRef<number | null>(null);

  useEffect(() => {
    if (loading) return;
    if (!isPostHogConfigured()) return;

    const authed = Boolean(me?.authenticated && me.user?.id);
    const nextId = authed && me?.user ? me.user.id : null;

    try {
      if (nextId != null) {
        if (lastUserIdRef.current != null && lastUserIdRef.current !== nextId) {
          // Different user on same device without clean logout
          resetAnalytics();
        }
        identifyUser(nextId, {
          username: me?.user?.username,
          department: me?.user?.department,
        });
        lastUserIdRef.current = nextId;
      } else if (lastUserIdRef.current != null) {
        resetAnalytics();
        lastUserIdRef.current = null;
      }
    } catch {
      /* never break session */
    }
  }, [me, loading]);

  return null;
}

export function PostHogAppProvider({ children }: { children: ReactNode }) {
  const client = initPostHog();

  if (!client) {
    return <>{children}</>;
  }

  return <PostHogProvider client={client}>{children}</PostHogProvider>;
}
