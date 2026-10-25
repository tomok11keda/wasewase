import assert from "node:assert/strict";
import test from "node:test";
import {
  chatContentPhase,
  chatRoomMatches,
} from "./chatContentPhase.ts";
import {
  isLatestRequest,
  isSameUserScope,
  nextRequestId,
} from "./userScopedResult.ts";

const idle = {
  loading: false,
  error: null as string | null,
  hasRoom: false,
  hydrated: false,
  messageCount: 0,
};

test("first load and permission checks use a skeleton", () => {
  assert.equal(chatContentPhase({ ...idle, loading: true }), "skeleton");
  assert.equal(chatContentPhase({ ...idle }), "skeleton");
});

test("an empty hydrated room is empty, not a skeleton", () => {
  assert.equal(
    chatContentPhase({
      ...idle,
      hasRoom: true,
      hydrated: true,
      messageCount: 0,
    }),
    "empty"
  );
});

test("a hydrated thread stays ready during a later poll", () => {
  assert.equal(
    chatContentPhase({
      ...idle,
      hasRoom: true,
      hydrated: true,
      messageCount: 3,
      loading: true,
    }),
    "ready"
  );
});

test("403/404 without a room are errors, not lingering skeletons", () => {
  assert.equal(
    chatContentPhase({ ...idle, hydrated: true, error: "forbidden" }),
    "error"
  );
  assert.equal(
    chatContentPhase({ ...idle, hydrated: true, error: "not_found" }),
    "error"
  );
});

test("unjoined recruiting or pending access is gated, not a thread", () => {
  assert.equal(
    chatContentPhase({
      ...idle,
      hydrated: true,
      gated: true,
      messageCount: 4,
    }),
    "gated"
  );
});

test("a stale room id is not the current chat", () => {
  assert.equal(chatRoomMatches({ id: 4 }, 4), true);
  assert.equal(chatRoomMatches({ id: 4 }, 9), false);
  assert.equal(chatRoomMatches(null, 4), false);
});

test("later chat requests win and user switches drop in-flight rows", () => {
  const ref = { current: 0 };
  const first = nextRequestId(ref);
  const second = nextRequestId(ref);
  assert.equal(isLatestRequest(ref, first), false);
  assert.equal(isLatestRequest(ref, second), true);
  assert.equal(isSameUserScope(3, 8), false);
  assert.equal(isSameUserScope(3, 3), true);
});
