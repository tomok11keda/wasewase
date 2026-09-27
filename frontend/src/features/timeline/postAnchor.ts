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

export type TimelinePostDetailNavState = {
  fromWaseWase?: boolean;
  focusComposer?: boolean;
};

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
