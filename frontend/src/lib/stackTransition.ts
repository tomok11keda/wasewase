import type { NavigationType } from "react-router-dom";
import { isStackPopState } from "./messageStack.ts";

/**
 * Reusable iOS-style stack slide. Opt in per route with `isStackPath`.
 * Header + outlet travel together; keep-alive underlay can parallax separately.
 *
 * CSS duration/easing must stay in sync with shell.css.
 */
export const STACK_PUSH_CLASS = "wase-stack-push";
export const STACK_POP_CLASS = "wase-stack-pop";
export const STACK_PREPARE_PUSH_CLASS = "wase-stack-prepare-push";
export const STACK_PREPARE_POP_CLASS = "wase-stack-prepare-pop";
export const STACK_UNDERLAY_CLASS = "wase-stack-underlay";
export const STACK_PUSH_MS = 360;
export const STACK_EASING = "cubic-bezier(0.22, 1, 0.36, 1)";

const STACK_CLASSES = [
  STACK_PUSH_CLASS,
  STACK_POP_CLASS,
  STACK_PREPARE_PUSH_CLASS,
  STACK_PREPARE_POP_CLASS,
  STACK_UNDERLAY_CLASS,
] as const;

export function shouldPlayStackPush(input: {
  navigationType: NavigationType;
  pathname: string;
  isSessionStart: boolean;
  state?: unknown;
  isStackPath: (pathname: string) => boolean;
}): boolean {
  if (input.isSessionStart) return false;
  if (input.navigationType !== "PUSH") return false;
  if (isStackPopState(input.state)) return false;
  return input.isStackPath(input.pathname);
}

export function queryStackSurface(): HTMLElement | null {
  if (typeof document === "undefined") return null;
  return (
    (document.querySelector(
      ".tab-keep-alive-outlet:not(.is-hidden)"
    ) as HTMLElement | null) ||
    (document.querySelector(".main-column") as HTMLElement | null)
  );
}

function bumpStackSurfaces(): void {
  if (typeof document === "undefined") return;
  document
    .querySelectorAll(
      ".tab-keep-alive-outlet:not(.is-hidden), .site-header--detail, .tab-keep-alive-stack.is-back-underlay"
    )
    .forEach((node) => {
      void (node as HTMLElement).offsetWidth;
    });
}

export function clearStackTransitionClasses(root: HTMLElement): void {
  root.classList.remove(...STACK_CLASSES);
}

export function prepareStackEnter(root: HTMLElement, withUnderlay: boolean): void {
  clearStackTransitionClasses(root);
  if (withUnderlay) root.classList.add(STACK_UNDERLAY_CLASS);
  root.classList.add(STACK_PREPARE_PUSH_CLASS);
  bumpStackSurfaces();
}

export function commitStackEnter(root: HTMLElement): void {
  root.classList.remove(STACK_PREPARE_PUSH_CLASS);
  root.classList.add(STACK_PUSH_CLASS);
}

export function prepareStackExit(root: HTMLElement, withUnderlay: boolean): void {
  root.classList.remove(
    STACK_PUSH_CLASS,
    STACK_PREPARE_PUSH_CLASS,
    STACK_POP_CLASS
  );
  if (withUnderlay) root.classList.add(STACK_UNDERLAY_CLASS);
  else root.classList.remove(STACK_UNDERLAY_CLASS);
  root.classList.add(STACK_PREPARE_POP_CLASS);
  bumpStackSurfaces();
}

export function commitStackExit(root: HTMLElement): void {
  root.classList.remove(STACK_PREPARE_POP_CLASS);
  root.classList.add(STACK_POP_CLASS);
}

/** After the start pose is committed, run `commit` on the next frame. */
export function scheduleStackCommit(commit: () => void): () => void {
  let cancelled = false;
  const frame = window.requestAnimationFrame(() => {
    if (cancelled) return;
    commit();
  });
  return () => {
    cancelled = true;
    window.cancelAnimationFrame(frame);
  };
}

export function waitForStackTransition(
  el: HTMLElement | null,
  timeoutMs = STACK_PUSH_MS
): Promise<void> {
  return new Promise((resolve) => {
    let settled = false;
    const settle = () => {
      if (settled) return;
      settled = true;
      el?.removeEventListener("transitionend", onEnd);
      window.clearTimeout(timer);
      resolve();
    };
    const onEnd = (event: TransitionEvent) => {
      if (event.target !== el) return;
      if (event.propertyName !== "transform") return;
      settle();
    };
    const timer = window.setTimeout(settle, timeoutMs + 80);
    if (!el) {
      settle();
      return;
    }
    el.addEventListener("transitionend", onEnd);
  });
}
