import type { TimelinePost } from "./api";

const POST_HASH_RE = /^#?post-(\d+)$/;
const POST_PATH_RE = /^\/(?:app\/)?posts\/(\d+)\/?$/;

/** Nested controls that must not open the post detail route. */
export const TIMELINE_POST_DETAIL_IGNORE_SELECTOR = [
  "a",
  "button",
  "input",
  "textarea",
  "select",
  '[role="button"]',
  '[role="menu"]',
  '[role="menuitem"]',
  ".timeline-flea-share",
  ".share-card",
  ".tweet-media",
  ".quoted-post-card",
].join(",");

/** Nested controls inside a quoted original card. The card itself is excluded. */
export const QUOTED_POST_INNER_IGNORE_SELECTOR = [
  "a",
  "button",
  "input",
  "textarea",
  "select",
  '[role="button"]',
  '[role="menu"]',
  '[role="menuitem"]',
  ".timeline-flea-share",
  ".share-card",
  ".tweet-media",
].join(",");

export type TimelinePostDetailNavState = {
  fromWaseWase?: boolean;
  focusComposer?: boolean;
  /** List-row snapshot for first paint only — never the source of truth. */
  initialPost?: TimelinePost;
};

/** Drop comments so location.state stays compact (list API already omits them). */
export function compactTimelinePost(post: TimelinePost): TimelinePost {
  return { ...post, comments: [] };
}

export function timelinePostDetailState(
  post: TimelinePost,
  extra?: { focusComposer?: boolean }
): TimelinePostDetailNavState {
  return {
    fromWaseWase: true,
    initialPost: compactTimelinePost(post),
    ...(extra?.focusComposer ? { focusComposer: true } : {}),
  };
}

/**
 * Quoted/repost originals are a truncated feed shell, not a full TimelinePost.
 * Do not invent initialPost — Post Detail fetches the source of truth.
 */
export function quotedPostDetailState(): TimelinePostDetailNavState {
  return { fromWaseWase: true };
}

export function readInitialTimelinePost(
  state: unknown,
  postId: number
): TimelinePost | null {
  if (!state || typeof state !== "object") return null;
  const raw = (state as TimelinePostDetailNavState).initialPost;
  if (!raw || raw.id !== postId) return null;
  return compactTimelinePost(raw);
}

export function parseTimelinePostHash(
  hash: string | undefined | null
): number | null {
  if (!hash) return null;
  const match = POST_HASH_RE.exec(hash.trim());
  if (!match) return null;
  const id = Number(match[1]);
  return Number.isFinite(id) && id > 0 ? id : null;
}

/** Canonical share path: /posts/<id> (basename /app is already stripped). */
export function parseTimelinePostPath(
  pathname: string | undefined | null
): number | null {
  if (!pathname) return null;
  const match = POST_PATH_RE.exec(pathname.trim());
  if (!match) return null;
  const id = Number(match[1]);
  return Number.isFinite(id) && id > 0 ? id : null;
}

export function isTimelinePostDetailIgnoreTarget(
  target: EventTarget | null
): boolean {
  return target instanceof Element
    ? Boolean(target.closest(TIMELINE_POST_DETAIL_IGNORE_SELECTOR))
    : false;
}

export function isQuotedPostInnerIgnoreTarget(
  target: EventTarget | null
): boolean {
  return target instanceof Element
    ? Boolean(target.closest(QUOTED_POST_INNER_IGNORE_SELECTOR))
    : false;
}

export function scrollToTimelinePost(postId: number): boolean {
  const el = document.getElementById(`post-${postId}`);
  if (!el) return false;
  el.scrollIntoView({ behavior: "smooth", block: "center" });
  el.classList.add("tweet-card--highlight");
  window.setTimeout(() => {
    el.classList.remove("tweet-card--highlight");
  }, 2000);
  return true;
}
