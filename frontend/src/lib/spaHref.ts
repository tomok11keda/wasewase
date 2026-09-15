/** Parse a React Router path (basename=/app) into a `Link` `to` object. */
export function spaHrefTo(to: string): {
  pathname: string;
  search?: string;
  hash?: string;
} {
  const trimmed = (to || "/").trim() || "/";
  const hashIdx = trimmed.indexOf("#");
  const hashRaw = hashIdx >= 0 ? trimmed.slice(hashIdx + 1) : "";
  const withoutHash = hashIdx >= 0 ? trimmed.slice(0, hashIdx) : trimmed;
  const qIdx = withoutHash.indexOf("?");
  const pathname = (qIdx >= 0 ? withoutHash.slice(0, qIdx) : withoutHash) || "/";
  const search = qIdx >= 0 ? withoutHash.slice(qIdx) : "";
  const result: { pathname: string; search?: string; hash?: string } = {
    pathname,
  };
  if (search) result.search = search;
  if (hashRaw) result.hash = `#${hashRaw}`;
  return result;
}
