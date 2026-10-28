import assert from "node:assert/strict";
import test from "node:test";
import {
  initialTimelineShareUi,
  reduceTimelineShareUi,
  timelineShareTapSendsRequest,
  type TimelineShareUiAction,
} from "./eventTimelineShareFlow.ts";

test("first tap opens the intro composer and does not submit", () => {
  const opened = reduceTimelineShareUi(initialTimelineShareUi(), {
    type: "tap_open",
  });
  assert.equal(opened.composerOpen, true);
  assert.equal(opened.submitting, false);
  assert.equal(opened.body, "");
  assert.equal(timelineShareTapSendsRequest({ type: "tap_open" }), false);
});

test("intro can be empty and submit is a second tap", () => {
  let state = reduceTimelineShareUi(initialTimelineShareUi(), { type: "tap_open" });
  state = reduceTimelineShareUi(state, { type: "edit", body: "" });
  const submit: TimelineShareUiAction = { type: "tap_submit" };
  state = reduceTimelineShareUi(state, submit);
  assert.equal(state.composerOpen, true);
  assert.equal(state.submitting, true);
  assert.equal(timelineShareTapSendsRequest(submit), true);
});

test("failure keeps the composer open with an error and does not look successful", () => {
  let state = reduceTimelineShareUi(initialTimelineShareUi(), { type: "tap_open" });
  state = reduceTimelineShareUi(state, { type: "tap_submit" });
  state = reduceTimelineShareUi(state, {
    type: "failure",
    message: "同じイベントは10分間に1回までシェアできます。しばらく待ってからもう一度お試しください。",
  });
  assert.equal(state.composerOpen, true);
  assert.equal(state.submitting, false);
  assert.match(state.error || "", /10分間/);
});

test("success closes the composer so the page can show the post link", () => {
  let state = reduceTimelineShareUi(initialTimelineShareUi(), { type: "tap_open" });
  state = reduceTimelineShareUi(state, { type: "edit", body: "新歓に来てね" });
  state = reduceTimelineShareUi(state, { type: "tap_submit" });
  state = reduceTimelineShareUi(state, { type: "success" });
  assert.deepEqual(state, initialTimelineShareUi());
});

test("close is ignored while submitting so a hung request cannot look idle", () => {
  let state = reduceTimelineShareUi(initialTimelineShareUi(), { type: "tap_open" });
  state = reduceTimelineShareUi(state, { type: "tap_submit" });
  const closed = reduceTimelineShareUi(state, { type: "close" });
  assert.equal(closed.composerOpen, true);
  assert.equal(closed.submitting, true);
});
