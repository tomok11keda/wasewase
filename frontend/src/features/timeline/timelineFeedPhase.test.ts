import assert from "node:assert/strict";
import test from "node:test";
import {
  TIMELINE_FEED_SKELETON_COUNT,
  timelineFeedPhase,
} from "./timelineFeedPhase.ts";

const idle = {
  browsePreview: false,
  sessionLoading: false,
  feedLoading: false,
  waitingForTarget: false,
  postUnavailable: false,
  error: null as string | null,
  postCount: 0,
};

test("first load and delayed session show a skeleton, not an empty feed", () => {
  assert.equal(
    timelineFeedPhase({ ...idle, feedLoading: true }),
    "skeleton"
  );
  assert.equal(
    timelineFeedPhase({ ...idle, sessionLoading: true }),
    "skeleton"
  );
  assert.equal(
    timelineFeedPhase({ ...idle, waitingForTarget: true }),
    "skeleton"
  );
});

test("browse preview never uses the logged-in feed skeleton", () => {
  assert.equal(
    timelineFeedPhase({ ...idle, browsePreview: true, feedLoading: true }),
    "browse"
  );
  assert.equal(
    timelineFeedPhase({ ...idle, browsePreview: true, sessionLoading: true }),
    "browse"
  );
});

test("soft refetch and tab revisit keep already loaded posts", () => {
  assert.equal(
    timelineFeedPhase({ ...idle, feedLoading: true, postCount: 3 }),
    "ready"
  );
  assert.equal(
    timelineFeedPhase({
      ...idle,
      waitingForTarget: true,
      sessionLoading: true,
      postCount: 2,
    }),
    "ready"
  );
});

test("home feed skeleton count stays aligned with the boot timeline", () => {
  assert.equal(TIMELINE_FEED_SKELETON_COUNT, 4);
});

test("empty feed, error, and unavailable stay distinct from first load", () => {
  assert.equal(timelineFeedPhase(idle), "empty");
  assert.equal(
    timelineFeedPhase({ ...idle, error: "load_failed" }),
    "error"
  );
  assert.equal(
    timelineFeedPhase({ ...idle, postUnavailable: true }),
    "unavailable"
  );
  assert.equal(
    timelineFeedPhase({
      ...idle,
      feedLoading: true,
      error: "load_failed",
    }),
    "skeleton"
  );
});
