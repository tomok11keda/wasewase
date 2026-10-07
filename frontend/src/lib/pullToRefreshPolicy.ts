/** Classic Timeline PTR values — keep these as the SPA source of truth. */
export const PTR_THRESHOLD_PX = 72;
export const PTR_MAX_PULL_PX = 120;
export const PTR_ARM_PX = 8;
export const PTR_EDGE_GUARD_PX = 24;
export const PTR_TOP_MAX_SCROLL_Y = 1;
export const PTR_MOBILE_MAX_WIDTH_PX = 1023;
export const PTR_ERROR_MS = 2000;
export const PTR_MOBILE_MEDIA = `(max-width: ${PTR_MOBILE_MAX_WIDTH_PX}px)`;

export type PtrStatus = "idle" | "pulling" | "armed" | "refreshing" | "error";

export function isPtrAtPageTop(scrollY: number): boolean {
  return scrollY <= PTR_TOP_MAX_SCROLL_Y;
}

export function isPtrLeftEdge(clientX: number): boolean {
  return clientX <= PTR_EDGE_GUARD_PX;
}

export function isPtrHorizontalGesture(dx: number, dy: number): boolean {
  return Math.abs(dx) > Math.abs(dy);
}

export function clampPtrPull(dy: number): number {
  if (dy <= 0) return 0;
  return dy > PTR_MAX_PULL_PX ? PTR_MAX_PULL_PX : dy;
}

export function isPtrArmed(pullPx: number): boolean {
  return pullPx >= PTR_THRESHOLD_PX;
}

export function shouldPtrPreventDefault(activated: boolean, dy: number): boolean {
  return activated || dy > PTR_ARM_PX;
}

export function canStartPtrGesture(input: {
  enabled: boolean;
  isMobile: boolean;
  refreshing: boolean;
  touchCount: number;
  scrollY: number;
  clientX: number;
}): boolean {
  if (!input.enabled || !input.isMobile || input.refreshing) return false;
  if (input.touchCount !== 1) return false;
  if (!isPtrAtPageTop(input.scrollY)) return false;
  if (isPtrLeftEdge(input.clientX)) return false;
  return true;
}

export function shouldActivatePtrPull(dx: number, dy: number): boolean {
  if (dy <= PTR_ARM_PX) return false;
  if (dy < 0) return false;
  if (isPtrHorizontalGesture(dx, dy)) return false;
  return true;
}

export function shouldCancelPtrBeforeActivate(dx: number, dy: number): boolean {
  if (dy < 0) return true;
  return isPtrHorizontalGesture(dx, dy);
}
