/** Home timeline is chronological only. Ranking remains an explicit API sort. */
export const HOME_TIMELINE_SORT = "latest" as const;

/** Leftover home filters that hid organization event shares from latest. */
export const HOME_LEFTOVER_SEARCH_KEYS = ["feed", "sort", "faculty", "q"] as const;

export function isHomeTimelinePath(pathname: string): boolean {
  return ((pathname || "/").replace(/\/$/, "") || "/") === "/";
}

/**
 * Strip leftover home-only query keys.
 * Keep-alive HomePage stays mounted on other tabs, so this must no-op unless
 * the current route is actually the home timeline.
 */
export function stripHomeTimelineLeftoverParams(
  pathname: string,
  searchParams: URLSearchParams
): URLSearchParams | null {
  if (!isHomeTimelinePath(pathname)) return null;
  if (!HOME_LEFTOVER_SEARCH_KEYS.some((key) => searchParams.has(key))) {
    return null;
  }
  const next = new URLSearchParams(searchParams);
  for (const key of HOME_LEFTOVER_SEARCH_KEYS) next.delete(key);
  return next;
}
