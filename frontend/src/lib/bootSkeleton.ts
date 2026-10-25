import { matchDetailChrome, matchChromeMode } from "./chrome.ts";
import { matchMainTab, normalizeSpaPath, shouldHideBottomNav } from "./tabs.ts";

export type BootSkeletonKind = "timeline" | "neutral";

export function bootSkeletonKind(pathname: string): BootSkeletonKind {
  return matchMainTab(normalizeSpaPath(pathname)) != null
    ? "timeline"
    : "neutral";
}

export function bootShowsBottomNav(pathname: string): boolean {
  return !shouldHideBottomNav(normalizeSpaPath(pathname));
}

/** Home no longer has おすすめ/最新 tabs. Kept so boot chrome tests stay explicit. */
export function bootShowsHomeSortTabs(_pathname: string): boolean {
  return false;
}

/** Route titles only — never a username, org name, or unread count. */
export function bootHeaderTitle(pathname: string): string | null {
  const path = normalizeSpaPath(pathname);
  if (matchMainTab(path) != null) return null;
  if (matchChromeMode(path) === "conversation") return "わせわせ";
  return matchDetailChrome(path)?.title || "わせわせ";
}
