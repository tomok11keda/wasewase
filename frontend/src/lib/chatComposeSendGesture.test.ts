import assert from "node:assert/strict";
import test from "node:test";
import {
  shouldPreventSendPointerDefault,
  shouldRefocusComposeAfterSend,
} from "./chatComposeSendGesture.ts";

test("prevents send pointer default for primary touch/pen/mouse while enabled", () => {
  assert.equal(
    shouldPreventSendPointerDefault({
      disabled: false,
      busy: false,
      pointerType: "touch",
      button: 0,
    }),
    true
  );
  assert.equal(
    shouldPreventSendPointerDefault({
      disabled: false,
      busy: false,
      pointerType: "mouse",
      button: 0,
    }),
    true
  );
});

test("does not prevent when disabled, busy, or non-primary mouse button", () => {
  assert.equal(
    shouldPreventSendPointerDefault({
      disabled: true,
      busy: false,
      pointerType: "touch",
      button: 0,
    }),
    false
  );
  assert.equal(
    shouldPreventSendPointerDefault({
      disabled: false,
      busy: true,
      pointerType: "touch",
      button: 0,
    }),
    false
  );
  assert.equal(
    shouldPreventSendPointerDefault({
      disabled: false,
      busy: false,
      pointerType: "mouse",
      button: 2,
    }),
    false
  );
});

test("refocuses compose after send when still interactive", () => {
  assert.equal(
    shouldRefocusComposeAfterSend({ disabled: false, stillMounted: true }),
    true
  );
  assert.equal(
    shouldRefocusComposeAfterSend({ disabled: true, stillMounted: true }),
    false
  );
  assert.equal(
    shouldRefocusComposeAfterSend({ disabled: false, stillMounted: false }),
    false
  );
});
