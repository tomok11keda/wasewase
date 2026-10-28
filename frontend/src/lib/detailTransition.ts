import { useLayoutEffect, useRef } from "react";
import {
  useLocation,
  useNavigationType,
  type NavigateFunction,
  type NavigationType,
} from "react-router-dom";
import { matchChromeMode, resolveDetailBack } from "./chrome";
import { allowUnsavedNavigation } from "./unsavedChangesGuard";
import { conversationBack } from "./conversationBack";
import {
  DM_INBOX_SCROLL_KEY,
  isDmInboxPath,
  isMessageStackPath,
} from "./messageStack";
import {
  clearStackTransitionClasses,
  commitStackEnter,
  commitStackExit,
  prepareStackEnter,
  prepareStackExit,
  queryStackSurface,
  scheduleStackCommit,
  shouldPlayStackPush,
  STACK_PUSH_MS,
  STACK_UNDERLAY_CLASS,
  waitForStackTransition,
} from "./stackTransition";
import { matchMainTab, normalizeSpaPath } from "./tabs";
import {
  restoreScrollPosition,
  saveScrollPosition,
  readScrollPosition,
} from "../features/profile/api";

export const DETAIL_PUSH_CLASS = "wase-detail-push";
export const DETAIL_POP_CLASS = "wase-detail-pop";
export const DETAIL_PUSH_MS = 400;
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
  const root = document.documentElement;
  return (
    root.classList.contains(DETAIL_POP_CLASS) ||
    root.classList.contains(STACK_UNDERLAY_CLASS)
  );
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
 * Isolate window.scrollY across BottomNav main tabs.
 * First visit of a tab restores 0. Does not run on detail PUSH (caller gates).
 * Detail POP still restores the list via restoreScrollPosition after this.
 */
export function syncMainTabWindowScroll(
  previousPath: string,
  nextPath: string
): void {
  if (previousPath === nextPath) return;
  const fromKey = mainTabScrollKey(previousPath);
  const toKey = mainTabScrollKey(nextPath);
  if (fromKey && fromKey !== toKey) {
    saveScrollPosition(fromKey);
  }
  if (toKey) {
    window.scrollTo(0, readScrollPosition(toKey));
  }
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
  state: unknown,
  search = ""
): void {
  const dest = resolveDetailBack(pathname, state, search);
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
  animationName: string,
  timeoutMs = DETAIL_PUSH_MS
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
    const timer = window.setTimeout(settle, timeoutMs + 40);
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
  state: unknown,
  search = ""
): void {
  if (!allowUnsavedNavigation()) return;
  if (detailBackInFlight) return;
  if (matchChromeMode(pathname) !== "detail") {
    executeDetailBack(navigate, pathname, state, search);
    return;
  }

  detailBackInFlight = true;
  let navigated = false;

  const go = () => {
    if (navigated) return;
    navigated = true;
    executeDetailBack(navigate, pathname, state, search);
    window.setTimeout(releaseDetailBackLock, 80);
  };

  if (prefersReducedMotion()) {
    go();
    return;
  }

  const root = document.documentElement;
  root.classList.remove(DETAIL_PUSH_CLASS);
  clearStackTransitionClasses(root);
  setHtmlPopClass(false);

  if (isMessageStackPath(pathname)) {
    const withUnderlay = matchChromeMode(pathname) === "detail";
    prepareStackExit(root, withUnderlay);
    notifyDetailPopVisual();
    scheduleStackCommit(() => {
      commitStackExit(root);
      void waitForStackTransition(queryStackSurface(), STACK_PUSH_MS).then(go);
    });
    return;
  }

  void root.offsetWidth;
  setHtmlPopClass(true);

  void waitForNamedAnimation(
    queryVisibleDetailOutlet(),
    DETAIL_EXIT_ANIMATION
  ).then(go);
}

/**
 * Conversation-header back: play the stack pop, then POP or replace.
 * Never PUSH a new inbox entry — that loops with the inbox header history back.
 */
export function requestStackHeaderBack(
  navigate: NavigateFunction,
  to: string,
  state?: unknown
): void {
  if (detailBackInFlight) return;
  detailBackInFlight = true;
  let navigated = false;

  const go = () => {
    if (navigated) return;
    navigated = true;
    conversationBack.execute(navigate, to, state);
    window.setTimeout(releaseDetailBackLock, 80);
  };

  if (prefersReducedMotion()) {
    go();
    return;
  }

  const root = document.documentElement;
  root.classList.remove(DETAIL_PUSH_CLASS);
  setHtmlPopClass(false);
  prepareStackExit(root, false);
  notifyDetailPopVisual();
  scheduleStackCommit(() => {
    commitStackExit(root);
    void waitForStackTransition(queryStackSurface(), STACK_PUSH_MS).then(go);
  });
}

/** Apply enter animation on <html> for one navigation, then drop it. */
export function useDetailPushTransition(): void {
  const location = useLocation();
  const navigationType = useNavigationType();
  const sessionStartRef = useRef(true);
  const prevPathRef = useRef(location.pathname);

  const playStack = shouldPlayStackPush({
    navigationType,
    pathname: location.pathname,
    isSessionStart: sessionStartRef.current,
    state: location.state,
    isStackPath: isMessageStackPath,
  });
  const playDetail =
    !playStack &&
    !isMessageStackPath(location.pathname) &&
    shouldPlayDetailPush({
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
    clearStackTransitionClasses(root);
    setHtmlPopClass(false);
    releaseDetailBackLock();
    notifyDetailPopVisual();

    const samePath =
      normalizeSpaPath(previousPath) === normalizeSpaPath(location.pathname);

    if (isDmInboxPath(previousPath) && !isDmInboxPath(location.pathname)) {
      saveScrollPosition(DM_INBOX_SCROLL_KEY);
    }

    if (playStack && !samePath) {
      const fromKey = mainTabScrollKey(previousPath);
      if (fromKey) saveScrollPosition(fromKey);
      window.scrollTo(0, 0);
      if (prefersReducedMotion()) return;
      detailBackInFlight = true;
      const fromMain = matchMainTab(previousPath) != null;
      prepareStackEnter(root, fromMain);
      notifyDetailPopVisual();
      const cancelCommit = scheduleStackCommit(() => {
        commitStackEnter(root);
      });
      const timer = window.setTimeout(() => {
        clearStackTransitionClasses(root);
        releaseDetailBackLock();
        notifyDetailPopVisual();
      }, STACK_PUSH_MS + 80);
      return () => {
        cancelCommit();
        window.clearTimeout(timer);
        clearStackTransitionClasses(root);
        releaseDetailBackLock();
        notifyDetailPopVisual();
      };
    }

    if (!playDetail) {
      syncMainTabWindowScroll(previousPath, location.pathname);
      if (navigationType === "POP") {
        const key = mainTabScrollKey(location.pathname);
        if (key) restoreScrollPosition(key, true);
      }
      if (isDmInboxPath(location.pathname) && !samePath) {
        restoreScrollPosition(DM_INBOX_SCROLL_KEY, true);
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
  }, [
    location.key,
    location.pathname,
    location.state,
    navigationType,
    playDetail,
    playStack,
  ]);
}
