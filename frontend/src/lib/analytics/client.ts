/**
 * PostHog client bootstrap — never throws into app UI.
 * Env (Vite, build-time):
 *   VITE_PUBLIC_POSTHOG_KEY   — Project API Key (public)
 *   VITE_PUBLIC_POSTHOG_HOST  — e.g. https://us.i.posthog.com
 *   VITE_PUBLIC_POSTHOG_REPLAY — "true" to enable Session Replay (masked)
 */
import posthog from "posthog-js";

const KEY = (import.meta.env.VITE_PUBLIC_POSTHOG_KEY || "").trim();
const HOST = (
  import.meta.env.VITE_PUBLIC_POSTHOG_HOST || "https://us.i.posthog.com"
).trim();
const REPLAY_ENABLED =
  String(import.meta.env.VITE_PUBLIC_POSTHOG_REPLAY || "")
    .trim()
    .toLowerCase() === "true";

let ready = false;

export function isPostHogConfigured(): boolean {
  return Boolean(KEY);
}

export function isPostHogReady(): boolean {
  return ready;
}

/** Initialize once. Safe no-op when key is missing. */
export function initPostHog(): typeof posthog | null {
  if (!KEY || typeof window === "undefined") return null;
  if (ready) return posthog;

  try {
    posthog.init(KEY, {
      api_host: HOST,
      // SPA pageviews via history API (PostHog recommended defaults)
      defaults: "2026-05-30",
      person_profiles: "identified_only",
      persistence: "localStorage+cookie",
      // Autocapture clicks is fine; inputs are masked if replay is on
      capture_pageview: "history_change",
      disable_session_recording: !REPLAY_ENABLED,
      session_recording: REPLAY_ENABLED
        ? {
            // β: mask all inputs + all text (posts/DM/email never leave the device)
            maskAllInputs: true,
            maskTextSelector: "*",
          }
        : undefined,
      loaded: (ph) => {
        if (import.meta.env.DEV) {
          ph.debug(false);
        }
      },
    });
    ready = true;
    return posthog;
  } catch (err) {
    console.warn("[analytics] PostHog init failed", err);
    ready = false;
    return null;
  }
}

export function getPostHog(): typeof posthog | null {
  if (!ready) return null;
  return posthog;
}

export function captureEvent(
  event: string,
  properties?: Record<string, string | number | boolean | null | undefined>
): void {
  try {
    if (!ready) return;
    const clean: Record<string, string | number | boolean> = {};
    if (properties) {
      for (const [k, v] of Object.entries(properties)) {
        if (v === undefined || v === null) continue;
        clean[k] = v;
      }
    }
    posthog.capture(event, clean);
  } catch {
    /* analytics must never break the product */
  }
}

export function identifyUser(
  userId: number,
  traits?: { username?: string; department?: string }
): void {
  try {
    if (!ready || !Number.isFinite(userId)) return;
    // distinct_id = internal numeric id only (never email)
    posthog.identify(String(userId), {
      username: traits?.username || undefined,
      department: traits?.department || undefined,
    });
  } catch {
    /* ignore */
  }
}

/** Clear identity so the next login cannot inherit the previous user. */
export function resetAnalytics(): void {
  try {
    if (!ready) return;
    posthog.reset();
  } catch {
    /* ignore */
  }
}

/** Call on explicit logout before clearing session state. */
export function analyticsLogout(): void {
  resetAnalytics();
}
