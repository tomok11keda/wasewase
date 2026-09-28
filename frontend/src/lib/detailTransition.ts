import { useLayoutEffect, useRef } from "react";
import {
  useLocation,
  useNavigationType,
  type NavigationType,
} from "react-router-dom";
import { matchChromeMode } from "./chrome";
import { matchMainTab, normalizeSpaPath } from "./tabs";
import {
  restoreScrollPosition,
  saveScrollPosition,
} from "../features/profile/api";

export const DETAIL_PUSH_CLASS = "wase-detail-push";
export const DETAIL_PUSH_MS = 340;

/** Main-tab sessionStorage key, or null when the path is not a keep-alive tab. */
export function mainTabScrollKey(pathname: string): string | null {
  const normalized = normalizeSpaPath(pathname);
  return matchMainTab(normalized) == null ? null : normalized;
}

/**
 * Forward-only detail enter. POP / REPLACE / boot / main tabs / conversations
 * must not play the React horizontal slide — native edge-swipe owns back.
 */
export function shouldPlayDetailPush(input: {
  navigationType: NavigationType;
  pathname: string;
  isSessionStart: boolean;
}): boolean {
  if (input.isSessionStart) return false;
  if (input.navigationType !== "PUSH") return false;
  return matchChromeMode(input.pathname) === "detail";
}

/** Same gate as the enter animation: only PUSH detail resets window scroll to top. */
export function shouldResetDetailWindowScroll(input: {
  navigationType: NavigationType;
  pathname: string;
  isSessionStart: boolean;
}): boolean {
  return shouldPlayDetailPush(input);
}

/** Apply `wase-detail-push` on <html> for one enter animation, then drop it. */
export function useDetailPushTransition(): void {
  const location = useLocation();
  const navigationType = useNavigationType();
  const sessionStartRef = useRef(true);
  const prevPathRef = useRef(location.pathname);

  const play = shouldPlayDetailPush({
    navigationType,
    pathname: location.pathname,
    isSessionStart: sessionStartRef.current,
  });

  useLayoutEffect(() => {
    const previousPath = prevPathRef.current;
    prevPathRef.current = location.pathname;
    sessionStartRef.current = false;
    const root = document.documentElement;
    root.classList.remove(DETAIL_PUSH_CLASS);

    if (!play) {
      if (navigationType === "POP") {
        const key = mainTabScrollKey(location.pathname);
        if (key) restoreScrollPosition(key, true);
      }
      return;
    }

    const fromKey = mainTabScrollKey(previousPath);
    if (fromKey) saveScrollPosition(fromKey);
    window.scrollTo(0, 0);

    void root.offsetWidth;
    root.classList.add(DETAIL_PUSH_CLASS);
    const timer = window.setTimeout(() => {
      root.classList.remove(DETAIL_PUSH_CLASS);
    }, DETAIL_PUSH_MS + 40);
    return () => {
      window.clearTimeout(timer);
      root.classList.remove(DETAIL_PUSH_CLASS);
    };
  }, [location.key, location.pathname, navigationType, play]);
}
