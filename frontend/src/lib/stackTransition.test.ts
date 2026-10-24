import assert from "node:assert/strict";
import test from "node:test";
import { isMessageStackPath } from "./messageStack.ts";
import { shouldPlayStackPush } from "./stackTransition.ts";

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

test("stack push skips returning from a chat via explicit pop state", () => {
  assert.equal(
    shouldPlayStackPush({
      navigationType: "PUSH",
      pathname: "/dm",
      isSessionStart: false,
      state: { waseStackPop: true },
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
