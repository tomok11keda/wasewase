import assert from "node:assert/strict";
import test from "node:test";
import { isMessageStackPath } from "./messageStack.ts";
import {
  STACK_EASING,
  STACK_PUSH_MS,
  shouldPlayStackPush,
} from "./stackTransition.ts";

test("stack motion uses a 360ms iOS-style ease-out, not a snap", () => {
  assert.equal(STACK_PUSH_MS, 360);
  assert.equal(STACK_EASING, "cubic-bezier(0.22, 1, 0.36, 1)");
});

const stack = (pathname: string) => isMessageStackPath(pathname);

test("stack push plays for inbox and rooms on SPA PUSH, not on boot or POP", () => {
  assert.equal(
    shouldPlayStackPush({
      navigationType: "PUSH",
      pathname: "/dm",
      isSessionStart: false,
      isStackPath: stack,
    }),
    true
  );
  assert.equal(
    shouldPlayStackPush({
      navigationType: "PUSH",
      pathname: "/dm/4",
      isSessionStart: false,
      isStackPath: stack,
    }),
    true
  );
  assert.equal(
    shouldPlayStackPush({
      navigationType: "PUSH",
      pathname: "/dm",
      isSessionStart: true,
      isStackPath: stack,
    }),
    false
  );
  assert.equal(
    shouldPlayStackPush({
      navigationType: "POP",
      pathname: "/dm",
      isSessionStart: false,
      isStackPath: stack,
    }),
    false
  );
});

test("stack push does not run on POP, including conversation header back", () => {
  assert.equal(
    shouldPlayStackPush({
      navigationType: "POP",
      pathname: "/dm",
      isSessionStart: false,
      isStackPath: stack,
    }),
    false
  );
  assert.equal(
    shouldPlayStackPush({
      navigationType: "REPLACE",
      pathname: "/dm",
      isSessionStart: false,
      isStackPath: stack,
    }),
    false
  );
});

test("stack push does not apply to posts, timetable, or other details", () => {
  assert.equal(
    shouldPlayStackPush({
      navigationType: "PUSH",
      pathname: "/posts/1",
      isSessionStart: false,
      isStackPath: stack,
    }),
    false
  );
  assert.equal(
    shouldPlayStackPush({
      navigationType: "PUSH",
      pathname: "/timetable",
      isSessionStart: false,
      isStackPath: stack,
    }),
    false
  );
});
