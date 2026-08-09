/**
 * Timeline impression (view) tracking.
 * Session dedupe via sessionStorage; batch POST to avoid 1-request-per-post.
 */
import { getCsrfToken } from "./api";

const STORAGE_KEY = "wase_timeline_impressions";
const DWELL_MS = 1000;
const FLUSH_MS = 1500;
const FLUSH_BATCH_MAX = 20;

type CountListener = (postId: number, viewCount: number) => void;

const memorySeen = new Set<number>();
const pending = new Set<number>();
const listeners = new Map<number, Set<CountListener>>();
let flushTimer: number | null = null;
let hydrated = false;

function hydrateSeen(): void {
  if (hydrated || typeof sessionStorage === "undefined") return;
  hydrated = true;
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return;
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed)) return;
    for (const item of parsed) {
      const id = Number(item);
      if (Number.isFinite(id) && id > 0) memorySeen.add(id);
    }
  } catch {
    /* ignore corrupt storage */
  }
}

function persistSeen(): void {
  if (typeof sessionStorage === "undefined") return;
  try {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify([...memorySeen]));
  } catch {
    /* quota / private mode */
  }
}

export function hasRecordedImpression(postId: number): boolean {
  hydrateSeen();
  return memorySeen.has(postId);
}

/** Recently impressed post IDs (session) — used to demote repeats in おすすめ. */
export function getImpressedPostIds(limit = 80): number[] {
  hydrateSeen();
  const ids = [...memorySeen];
  if (ids.length <= limit) return ids;
  return ids.slice(ids.length - limit);
}

function markSeen(postId: number): void {
  memorySeen.add(postId);
  persistSeen();
}

function scheduleFlush(): void {
  if (flushTimer != null) return;
  flushTimer = window.setTimeout(() => {
    flushTimer = null;
    void flushImpressions();
  }, FLUSH_MS);
}

async function flushImpressions(): Promise<void> {
  if (!pending.size) return;
  const ids = [...pending].slice(0, FLUSH_BATCH_MAX);
  for (const id of ids) pending.delete(id);

  try {
    const res = await fetch("/api/v1/timeline/impressions/", {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
        "X-CSRFToken": getCsrfToken(),
      },
      body: JSON.stringify({ post_ids: ids }),
    });
    const data = (await res.json().catch(() => ({}))) as {
      ok?: boolean;
      counts?: Record<string, number>;
    };
    if (!res.ok || !data.ok) {
      // Allow retry later in a new session only — keep seen to avoid storms
      return;
    }
    const counts = data.counts || {};
    for (const id of ids) {
      const count = counts[String(id)];
      if (typeof count !== "number") continue;
      const cbs = listeners.get(id);
      if (!cbs) continue;
      for (const cb of cbs) cb(id, count);
      listeners.delete(id);
    }
  } catch {
    /* network — already marked seen; skip requeue to avoid spam */
  }

  if (pending.size) scheduleFlush();
}

/**
 * Queue a post impression once per browser session.
 * Optional listener receives updated view_count after a successful flush.
 */
export function queueImpression(
  postId: number,
  onCounted?: CountListener
): void {
  if (!Number.isFinite(postId) || postId <= 0) return;
  hydrateSeen();
  if (memorySeen.has(postId)) return;
  markSeen(postId);
  pending.add(postId);
  if (onCounted) {
    let set = listeners.get(postId);
    if (!set) {
      set = new Set();
      listeners.set(postId, set);
    }
    set.add(onCounted);
  }
  if (pending.size >= FLUSH_BATCH_MAX) {
    if (flushTimer != null) {
      window.clearTimeout(flushTimer);
      flushTimer = null;
    }
    void flushImpressions();
  } else {
    scheduleFlush();
  }
}

/** Dwell time used by the card IntersectionObserver (ms). */
export const IMPRESSION_DWELL_MS = DWELL_MS;
