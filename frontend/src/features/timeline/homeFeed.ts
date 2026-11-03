/** Home timeline default. Ranking stays an explicit API sort. */
export const HOME_TIMELINE_SORT = "latest" as const;
export type HomeTimelineSort = "latest" | "recommended";

/** Leftover home filters that hid organization event shares from latest. */
export const HOME_LEFTOVER_SEARCH_KEYS = ["feed", "faculty", "q"] as const;

export function isHomeTimelinePath(pathname: string): boolean {
  return ((pathname || "/").replace(/\/$/, "") || "/") === "/";
}

export function parseHomeTimelineSort(
  raw: string | null | undefined
): HomeTimelineSort {
  return raw === "recommended" ? "recommended" : HOME_TIMELINE_SORT;
}

/**
 * Strip leftover home-only query keys.
 * Keep-alive HomePage stays mounted on other tabs, so this must no-op unless
 * the current route is actually the home timeline.
 * `sort` is kept so おすすめ/最新 can be selected without being wiped.
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
