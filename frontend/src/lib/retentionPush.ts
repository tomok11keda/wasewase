/** Retention push deep-link helpers. Keep copy/PII out of the query. */

export const RETENTION_PUSH_QUERY = "rp";

export function parseRetentionPushOpen(path: string | null | undefined): {
  kind: string;
  postId: number | null;
} | null {
  if (!path || typeof path !== "string") return null;
  const trimmed = path.trim();
  if (!trimmed) return null;

  let pathname = trimmed;
  let search = "";
  const qIdx = trimmed.indexOf("?");
  const hashIdx = trimmed.indexOf("#");
  const cut = [qIdx, hashIdx].filter((idx) => idx >= 0);
  const end = cut.length ? Math.min(...cut) : -1;
  if (end >= 0) {
    pathname = trimmed.slice(0, end);
    if (qIdx >= 0 && (hashIdx < 0 || qIdx < hashIdx)) {
      search = trimmed.slice(qIdx + 1, hashIdx >= 0 ? hashIdx : undefined);
    }
  }

  const params = new URLSearchParams(search);
  const kind = (params.get(RETENTION_PUSH_QUERY) || "").trim();
  if (!kind) return null;

  const match = pathname.match(/\/posts\/(\d+)\/?$/);
  const postId = match ? Number(match[1]) : null;
  return {
    kind,
    postId: Number.isFinite(postId) ? postId : null,
  };
}
