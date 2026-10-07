/**
 * Executable PTR policy tests. Keep numeric constants in sync with
 * frontend/src/lib/pullToRefreshPolicy.ts — Django asserts they match.
 */
export const PTR_THRESHOLD_PX = 72;
export const PTR_MAX_PULL_PX = 120;
export const PTR_ARM_PX = 8;
export const PTR_EDGE_GUARD_PX = 24;
export const PTR_TOP_MAX_SCROLL_Y = 1;
export const PTR_MOBILE_MAX_WIDTH_PX = 1023;
export const PTR_ERROR_MS = 2000;

function isPtrAtPageTop(scrollY) {
  return scrollY <= PTR_TOP_MAX_SCROLL_Y;
}

function isPtrLeftEdge(clientX) {
  return clientX <= PTR_EDGE_GUARD_PX;
}

function isPtrHorizontalGesture(dx, dy) {
  return Math.abs(dx) > Math.abs(dy);
}

function clampPtrPull(dy) {
  if (dy <= 0) return 0;
  return dy > PTR_MAX_PULL_PX ? PTR_MAX_PULL_PX : dy;
}

function isPtrArmed(pullPx) {
  return pullPx >= PTR_THRESHOLD_PX;
}

function shouldPtrPreventDefault(activated, dy) {
  return activated || dy > PTR_ARM_PX;
}

function canStartPtrGesture(input) {
  if (!input.enabled || !input.isMobile || input.refreshing) return false;
  if (input.touchCount !== 1) return false;
  if (!isPtrAtPageTop(input.scrollY)) return false;
  if (isPtrLeftEdge(input.clientX)) return false;
  return true;
}

function shouldActivatePtrPull(dx, dy) {
  if (dy <= PTR_ARM_PX) return false;
  if (dy < 0) return false;
  if (isPtrHorizontalGesture(dx, dy)) return false;
  return true;
}

function shouldCancelPtrBeforeActivate(dx, dy) {
  if (dy < 0) return true;
  return isPtrHorizontalGesture(dx, dy);
}

function assert(cond, msg) {
  if (!cond) {
    console.error("FAIL:", msg);
    process.exitCode = 1;
  }
}

const startOk = {
  enabled: true,
  isMobile: true,
  refreshing: false,
  touchCount: 1,
  scrollY: 0,
  clientX: 80,
};

assert(canStartPtrGesture({ ...startOk, scrollY: 0 }), "scrollY 0 can start");
assert(canStartPtrGesture({ ...startOk, scrollY: 1 }), "scrollY 1 can start");
assert(!canStartPtrGesture({ ...startOk, scrollY: 2 }), "scrollY 2 cannot start");
assert(!canStartPtrGesture({ ...startOk, scrollY: 80 }), "mid-list cannot start");
assert(!canStartPtrGesture({ ...startOk, touchCount: 2 }), "multi-touch cannot start");
assert(!canStartPtrGesture({ ...startOk, clientX: 12 }), "left edge cannot start");
assert(!canStartPtrGesture({ ...startOk, clientX: 24 }), "24px edge cannot start");
assert(canStartPtrGesture({ ...startOk, clientX: 25 }), "25px can start");
assert(!canStartPtrGesture({ ...startOk, isMobile: false }), "desktop cannot start");
assert(!canStartPtrGesture({ ...startOk, enabled: false }), "disabled cannot start");
assert(!canStartPtrGesture({ ...startOk, refreshing: true }), "refreshing cannot start");

assert(!shouldActivatePtrPull(0, 7), "7px does not activate");
assert(!shouldPtrPreventDefault(false, 7), "7px does not steal scroll");
assert(shouldActivatePtrPull(0, 9), "9px vertical activates");
assert(shouldPtrPreventDefault(true, 9), "activated pull preventDefault");
assert(shouldCancelPtrBeforeActivate(20, 8), "horizontal cancels");
assert(isPtrHorizontalGesture(30, 10), "dx>dy is horizontal");
assert(!shouldActivatePtrPull(30, 10), "horizontal does not activate");
assert(shouldCancelPtrBeforeActivate(0, -12), "upward cancels");

assert(!isPtrArmed(71), "71px not armed");
assert(isPtrArmed(72), "72px armed");
assert(clampPtrPull(200) === PTR_MAX_PULL_PX, "maxPull 120");
assert(clampPtrPull(-10) === 0, "negative pull clamps to 0");
assert(clampPtrPull(80) === 80, "mid pull unchanged");

assert(PTR_THRESHOLD_PX === 72, "threshold 72");
assert(PTR_MAX_PULL_PX === 120, "maxPull 120");
assert(PTR_ARM_PX === 8, "arm 8");
assert(PTR_EDGE_GUARD_PX === 24, "edge 24");
assert(PTR_TOP_MAX_SCROLL_Y === 1, "top max 1");
assert(PTR_MOBILE_MAX_WIDTH_PX === 1023, "mobile 1023");
assert(PTR_ERROR_MS === 2000, "error 2000");

if (process.exitCode) {
  console.error("PTR policy tests failed");
  process.exit(1);
}
console.log("PTR policy tests ok");
