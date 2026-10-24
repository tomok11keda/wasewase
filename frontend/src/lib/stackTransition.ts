import type { NavigationType } from "react-router-dom";
import { isStackPopState } from "./messageStack.ts";

/**
 * Reusable iOS-style stack slide. Opt in per route with `isStackPath`.
 * Uses transform on `.main-column` so the page header travels with the screen.
 */
export const STACK_PUSH_CLASS = "wase-stack-push";
export const STACK_POP_CLASS = "wase-stack-pop";
export const STACK_PUSH_MS = 280;
export const STACK_ENTER_ANIMATION = "wase-stack-push-in";
export const STACK_EXIT_ANIMATION = "wase-stack-pop-out";

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
  return document.querySelector(".main-column");
}

export function clearStackTransitionClasses(root: HTMLElement): void {
  root.classList.remove(STACK_PUSH_CLASS, STACK_POP_CLASS);
}

export function applyStackEnter(root: HTMLElement): void {
  clearStackTransitionClasses(root);
  void root.offsetWidth;
  root.classList.add(STACK_PUSH_CLASS);
}

export function applyStackExit(root: HTMLElement): void {
  root.classList.remove(STACK_PUSH_CLASS);
  root.classList.remove(STACK_POP_CLASS);
  void root.offsetWidth;
  root.classList.add(STACK_POP_CLASS);
}
