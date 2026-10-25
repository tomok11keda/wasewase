export const UNSAVED_DISCARD_MESSAGE = "変更を破棄しますか？";

export type UnsavedPromptState = {
  dirty: boolean;
  bypass: boolean;
};

type LeaveGuard = () => boolean;

let leaveGuard: LeaveGuard | null = null;

export function shouldPromptUnsavedChanges(state: UnsavedPromptState): boolean {
  return Boolean(state.dirty) && !state.bypass;
}

export function confirmDiscardUnsavedChanges(
  state: UnsavedPromptState,
  confirmFn: (message: string) => boolean = defaultConfirm
): boolean {
  if (!shouldPromptUnsavedChanges(state)) return true;
  return confirmFn(UNSAVED_DISCARD_MESSAGE);
}

export function setUnsavedChangesGuard(guard: LeaveGuard | null): void {
  leaveGuard = guard;
}

/** Return false to keep the current screen and its draft. */
export function allowUnsavedNavigation(): boolean {
  if (!leaveGuard) return true;
  return leaveGuard();
}

export function normalizeAppPath(pathname: string): string {
  const withoutApp = pathname.startsWith("/app")
    ? pathname.slice(4) || "/"
    : pathname;
  const trimmed = withoutApp.replace(/\/+$/, "");
  return trimmed || "/";
}

export function spaPathLeavesCurrent(
  nextPathname: string,
  currentPathname: string,
  nextSearch = "",
  currentSearch = ""
): boolean {
  if (normalizeAppPath(nextPathname) !== normalizeAppPath(currentPathname)) {
    return true;
  }
  return nextSearch !== currentSearch;
}

export function isSpaDocumentLink(anchor: HTMLAnchorElement): boolean {
  if (anchor.target && anchor.target !== "_self") return false;
  if (anchor.hasAttribute("download")) return false;
  const href = anchor.getAttribute("href");
  if (!href || href.startsWith("mailto:") || href.startsWith("tel:")) {
    return false;
  }
  try {
    const url = new URL(anchor.href, window.location.href);
    if (url.origin !== window.location.origin) return false;
    return url.pathname === "/app" || url.pathname.startsWith("/app/");
  } catch {
    return false;
  }
}

export function spaLinkLeavesPath(
  anchor: HTMLAnchorElement,
  currentPathname: string
): boolean {
  try {
    const url = new URL(anchor.href, window.location.href);
    return spaPathLeavesCurrent(
      url.pathname,
      currentPathname,
      url.search,
      window.location.search || ""
    );
  } catch {
    return true;
  }
}

function defaultConfirm(message: string): boolean {
  if (typeof window === "undefined" || typeof window.confirm !== "function") {
    return true;
  }
  return window.confirm(message);
}
