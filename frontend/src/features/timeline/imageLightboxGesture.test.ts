import assert from "node:assert/strict";
import test from "node:test";
import {
  backdropOpacityForOffset,
  EDGE_SWIPE_DISMISS_DISTANCE_PX,
  isEdgeBackGestureStart,
  isLeftEdgeGestureStart,
  prefersReducedMotion,
  resolveSwipeAxis,
  scaleForOffset,
  shouldDismissEdgeBackSwipe,
  shouldDismissSwipe,
  swipeDragOffsetX,
  swipeDragOffsetY,
  SWIPE_DISMISS_DISTANCE_PX,
  SWIPE_EDGE_GUARD_PX,
} from "./imageLightboxGesture.ts";

test("edge back gesture starts are detected near left/right screen edges", () => {
  assert.equal(isEdgeBackGestureStart(0, 390), true);
  assert.equal(isEdgeBackGestureStart(SWIPE_EDGE_GUARD_PX - 1, 390), true);
  assert.equal(isEdgeBackGestureStart(200, 390), false);
  assert.equal(isEdgeBackGestureStart(390 - SWIPE_EDGE_GUARD_PX + 1, 390), true);
});

test("left-edge dismiss eligibility is left-only", () => {
  assert.equal(isLeftEdgeGestureStart(0), true);
  assert.equal(isLeftEdgeGestureStart(SWIPE_EDGE_GUARD_PX), true);
  assert.equal(isLeftEdgeGestureStart(SWIPE_EDGE_GUARD_PX + 1), false);
  assert.equal(isLeftEdgeGestureStart(380), false);
});

test("axis lock prefers vertical only when clearly dominant", () => {
  assert.equal(resolveSwipeAxis(0, 0, 4, 4, "undecided"), "undecided");
  assert.equal(resolveSwipeAxis(0, 0, 3, 20, "undecided"), "vertical");
  assert.equal(resolveSwipeAxis(0, 0, 20, 3, "undecided"), "horizontal");
  assert.equal(resolveSwipeAxis(0, 0, 20, 18, "undecided"), "horizontal");
  assert.equal(resolveSwipeAxis(0, 0, 20, 3, "vertical"), "vertical");
});

test("drag offset only follows downward vertical swipes", () => {
  assert.equal(swipeDragOffsetY(100, 180, "vertical"), 80);
  assert.equal(swipeDragOffsetY(100, 40, "vertical"), 0);
  assert.equal(swipeDragOffsetY(100, 180, "horizontal"), 0);
  assert.equal(swipeDragOffsetY(100, 180, "undecided"), 0);
});

test("horizontal drag offset only tracks rightward left-edge starts", () => {
  assert.equal(swipeDragOffsetX(10, 90, "horizontal", true), 80);
  assert.equal(swipeDragOffsetX(10, 0, "horizontal", true), 0);
  assert.equal(swipeDragOffsetX(10, 90, "horizontal", false), 0);
  assert.equal(swipeDragOffsetX(10, 90, "vertical", true), 0);
  assert.equal(swipeDragOffsetX(10, 90, "undecided", true), 0);
});

test("dismiss requires distance or fast downward flick", () => {
  assert.equal(
    shouldDismissSwipe({
      offsetY: SWIPE_DISMISS_DISTANCE_PX,
      elapsedMs: 400,
      axis: "vertical",
    }),
    true
  );
  assert.equal(
    shouldDismissSwipe({
      offsetY: 40,
      elapsedMs: 400,
      axis: "vertical",
    }),
    false
  );
  assert.equal(
    shouldDismissSwipe({
      offsetY: 70,
      elapsedMs: 80,
      axis: "vertical",
    }),
    true
  );
  assert.equal(
    shouldDismissSwipe({
      offsetY: 200,
      elapsedMs: 100,
      axis: "horizontal",
    }),
    false
  );
});

test("edge-back dismiss requires left-edge start + rightward horizontal travel", () => {
  assert.equal(
    shouldDismissEdgeBackSwipe({
      fromLeftEdge: true,
      offsetX: EDGE_SWIPE_DISMISS_DISTANCE_PX,
      elapsedMs: 300,
      axis: "horizontal",
    }),
    true
  );
  assert.equal(
    shouldDismissEdgeBackSwipe({
      fromLeftEdge: true,
      offsetX: 30,
      elapsedMs: 300,
      axis: "horizontal",
    }),
    false
  );
  assert.equal(
    shouldDismissEdgeBackSwipe({
      fromLeftEdge: false,
      offsetX: 200,
      elapsedMs: 100,
      axis: "horizontal",
    }),
    false
  );
  assert.equal(
    shouldDismissEdgeBackSwipe({
      fromLeftEdge: true,
      offsetX: 200,
      elapsedMs: 100,
      axis: "vertical",
    }),
    false
  );
  assert.equal(
    shouldDismissEdgeBackSwipe({
      fromLeftEdge: true,
      offsetX: 50,
      elapsedMs: 60,
      axis: "horizontal",
    }),
    true
  );
});

test("backdrop opacity and scale ease down with offset", () => {
  assert.equal(backdropOpacityForOffset(0), 1);
  assert.ok(backdropOpacityForOffset(110) < 1);
  assert.ok(backdropOpacityForOffset(110) >= 0.35);
  assert.equal(scaleForOffset(0), 1);
  assert.ok(scaleForOffset(160) < 1);
  assert.ok(scaleForOffset(160) >= 0.88);
});

test("prefersReducedMotion reads matchMedia", () => {
  assert.equal(
    prefersReducedMotion(() => ({ matches: true })),
    true
  );
  assert.equal(
    prefersReducedMotion(() => ({ matches: false })),
    false
  );
});
