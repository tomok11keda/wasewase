import { useLayoutEffect, useRef } from "react";
import {
  useLocation,
  useNavigationType,
  type NavigateFunction,
  type NavigationType,
} from "react-router-dom";
import { matchChromeMode, resolveDetailBack } from "./chrome";
import { matchMainTab, normalizeSpaPath } from "./tabs";
import {
  restoreScrollPosition,
  saveScrollPosition,
} from "../features/profile/api";

export const DETAIL_PUSH_CLASS = "wase-detail-push";
export const DETAIL_POP_CLASS = "wase-detail-pop";
export const DETAIL_PUSH_MS = 500;
export const DETAIL_EXIT_ANIMATION = "wase-detail-push-out";

let detailBackInFlight = false;
const popVisualListeners = new Set<() => void>();

function notifyDetailPopVisual(): void {
  popVisualListeners.forEach((listener) => listener());
}

export function subscribeDetailPopVisual(onChange: () => void): () => void {
  popVisualListeners.add(onChange);
  return () => {
    popVisualListeners.delete(onChange);
  };
}

export function getDetailPopVisualSnapshot(): boolean {
  if (typeof document === "undefined") return false;
  return document.documentElement.classList.contains(DETAIL_POP_CLASS);
}

function setHtmlPopClass(on: boolean): void {
  const root = document.documentElement;
  root.classList.toggle(DETAIL_POP_CLASS, on);
  notifyDetailPopVisual();
}

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

export function prefersReducedMotion(): boolean {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
    return false;
  }
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

/** Existing AppDetailHeader back semantics — destination logic stays in chrome.ts. */
export function executeDetailBack(
  navigate: NavigateFunction,
  pathname: string,
  state: unknown
): void {
  const dest = resolveDetailBack(pathname, state);
  if (dest.mode === "history") {
    navigate(-1);
    return;
  }
  navigate(dest.to, dest.replace ? { replace: true } : undefined);
}

function queryVisibleDetailOutlet(): HTMLElement | null {
  return document.querySelector(
    ".tab-keep-alive-outlet:not(.is-hidden)"
  ) as HTMLElement | null;
}

function waitForNamedAnimation(
  el: HTMLElement | null,
  animationName: string
): Promise<void> {
  return new Promise((resolve) => {
    let settled = false;
    const settle = () => {
      if (settled) return;
      settled = true;
      el?.removeEventListener("animationend", onEnd);
      window.clearTimeout(timer);
      resolve();
    };
    const onEnd = (event: AnimationEvent) => {
      if (event.target !== el) return;
      if (event.animationName !== animationName) return;
      settle();
    };
    const timer = window.setTimeout(settle, DETAIL_PUSH_MS + 40);
    if (!el) {
      settle();
      return;
    }
    el.addEventListener("animationend", onEnd);
  });
}

function releaseDetailBackLock(): void {
  detailBackInFlight = false;
}

/**
 * AppDetailHeader back only. Never called for WKWebView edge-swipe / history POP.
 * Double-tap is ignored while the exit animation (or immediate reduced-motion
 * navigation) is in flight.
 */
export function requestDetailHeaderBack(
  navigate: NavigateFunction,
  pathname: string,
  state: unknown
): void {
  if (detailBackInFlight) return;
  if (matchChromeMode(pathname) !== "detail") {
    executeDetailBack(navigate, pathname, state);
    return;
  }

  detailBackInFlight = true;
  let navigated = false;

  const go = () => {
    if (navigated) return;
    navigated = true;
    executeDetailBack(navigate, pathname, state);
    window.setTimeout(releaseDetailBackLock, 80);
  };

  if (prefersReducedMotion()) {
    go();
    return;
  }

  const root = document.documentElement;
  root.classList.remove(DETAIL_PUSH_CLASS);
  setHtmlPopClass(false);
  void root.offsetWidth;
  setHtmlPopClass(true);

  void waitForNamedAnimation(
    queryVisibleDetailOutlet(),
    DETAIL_EXIT_ANIMATION
  ).then(go);
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
    setHtmlPopClass(false);
    releaseDetailBackLock();

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
