/** Pure helpers for ImageLightbox swipe-to-dismiss (testable without DOM). */

export const SWIPE_EDGE_GUARD_PX = 24;
export const SWIPE_AXIS_LOCK_PX = 10;
export const SWIPE_DISMISS_DISTANCE_PX = 110;
export const SWIPE_DISMISS_VELOCITY = 0.65; // px/ms
export const SWIPE_CLICK_SUPPRESS_MS = 450;

export type SwipeAxis = "undecided" | "vertical" | "horizontal";

export type SwipeSample = {
  startX: number;
  startY: number;
  x: number;
  y: number;
  axis: SwipeAxis;
};

export function isEdgeBackGestureStart(clientX: number, viewportWidth: number): boolean {
  if (viewportWidth <= 0) return clientX < SWIPE_EDGE_GUARD_PX;
  return clientX < SWIPE_EDGE_GUARD_PX || clientX > viewportWidth - SWIPE_EDGE_GUARD_PX;
}

export function resolveSwipeAxis(
  startX: number,
  startY: number,
  x: number,
  y: number,
  current: SwipeAxis
): SwipeAxis {
  if (current !== "undecided") return current;
  const dx = x - startX;
  const dy = y - startY;
  const absX = Math.abs(dx);
  const absY = Math.abs(dy);
  if (absX < SWIPE_AXIS_LOCK_PX && absY < SWIPE_AXIS_LOCK_PX) return "undecided";
  // Prefer vertical only when clearly dominant — avoid accidental dismiss on pans.
  if (absY >= absX * 1.15) return "vertical";
  return "horizontal";
}

export function swipeDragOffsetY(startY: number, y: number, axis: SwipeAxis): number {
  if (axis !== "vertical") return 0;
  // Only follow downward motion (Instagram-style dismiss).
  return Math.max(0, y - startY);
}

export function shouldDismissSwipe(opts: {
  offsetY: number;
  elapsedMs: number;
  axis: SwipeAxis;
  dismissDistance?: number;
}): boolean {
  if (opts.axis !== "vertical") return false;
  const distance = opts.dismissDistance ?? SWIPE_DISMISS_DISTANCE_PX;
  if (opts.offsetY >= distance) return true;
  if (opts.elapsedMs <= 0) return false;
  const velocity = opts.offsetY / opts.elapsedMs;
  return opts.offsetY >= distance * 0.55 && velocity >= SWIPE_DISMISS_VELOCITY;
}

export function backdropOpacityForOffset(offsetY: number, maxFade = 220): number {
  if (offsetY <= 0) return 1;
  const t = Math.min(1, offsetY / maxFade);
  return Math.max(0.35, 1 - t * 0.65);
}

export function scaleForOffset(offsetY: number, maxShrink = 320): number {
  if (offsetY <= 0) return 1;
  const t = Math.min(1, offsetY / maxShrink);
  return Math.max(0.88, 1 - t * 0.12);
}

export function prefersReducedMotion(
  matchMediaFn?: (query: string) => { matches: boolean }
): boolean {
  const mm =
    matchMediaFn ??
    (typeof globalThis.matchMedia === "function"
      ? globalThis.matchMedia.bind(globalThis)
      : null);
  if (!mm) return false;
  try {
    return Boolean(mm("(prefers-reduced-motion: reduce)")?.matches);
  } catch {
    return false;
  }
}
