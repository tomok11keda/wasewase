import assert from "node:assert/strict";
import test from "node:test";
import {
  isLatestRequest,
  isSameUserScope,
  nextRequestId,
} from "./userScopedResult.ts";

test("later requests win over in-flight responses from the same user", () => {
  const ref = { current: 0 };
  const first = nextRequestId(ref);
  const second = nextRequestId(ref);
  assert.equal(isLatestRequest(ref, first), false);
  assert.equal(isLatestRequest(ref, second), true);
});


test("guest-to-guest responses may apply", () => {
  assert.equal(isSameUserScope(null, null), true);
  assert.equal(isSameUserScope(undefined, undefined), true);
});

test("login, logout, and user switch discard in-flight responses", () => {
  assert.equal(isSameUserScope(null, 11), false);
  assert.equal(isSameUserScope(11, null), false);
  assert.equal(isSameUserScope(11, 22), false);
  assert.equal(isSameUserScope(11, 11), true);
});

test("invalid ids never match a real user", () => {
  assert.equal(isSameUserScope(0, 0), true);
  assert.equal(isSameUserScope(-1, -1), true);
  assert.equal(isSameUserScope(0, 11), false);
  assert.equal(isSameUserScope(11, 0), false);
});
