import { useLayoutEffect, useRef } from "react";
import {
  useLocation,
  useNavigationType,
  type NavigationType,
} from "react-router-dom";
import { matchChromeMode } from "./chrome";

export const DETAIL_PUSH_CLASS = "wase-detail-push";
export const DETAIL_PUSH_MS = 180;

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

/** Apply `wase-detail-push` on <html> for one enter animation, then drop it. */
export function useDetailPushTransition(): void {
  const location = useLocation();
  const navigationType = useNavigationType();
  const sessionStartRef = useRef(true);

  const play = shouldPlayDetailPush({
    navigationType,
    pathname: location.pathname,
    isSessionStart: sessionStartRef.current,
  });

  useLayoutEffect(() => {
    sessionStartRef.current = false;
    const root = document.documentElement;
    root.classList.remove(DETAIL_PUSH_CLASS);
    if (!play) return;
    void root.offsetWidth;
    root.classList.add(DETAIL_PUSH_CLASS);
    const timer = window.setTimeout(() => {
      root.classList.remove(DETAIL_PUSH_CLASS);
    }, DETAIL_PUSH_MS + 40);
    return () => {
      window.clearTimeout(timer);
      root.classList.remove(DETAIL_PUSH_CLASS);
    };
  }, [location.key, play]);
}
