const POST_HASH_RE = /^#?post-(\d+)$/;
const POST_PATH_RE = /^\/(?:app\/)?posts\/(\d+)\/?$/;

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
