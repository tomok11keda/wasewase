import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";
import {
  initialTimelineShareUi,
  reduceTimelineShareUi,
  timelineShareTapSendsRequest,
  type TimelineShareUiAction,
  type TimelineShareUiState,
} from "./eventTimelineShareFlow.ts";

const root = dirname(fileURLToPath(import.meta.url));
const view = readFileSync(join(root, "OrganizationEventDetailView.tsx"), "utf8");
const sheet = readFileSync(join(root, "EventTimelineShareSheet.tsx"), "utf8");
const page = readFileSync(
  join(root, "../../pages/OrganizationEventDetailPage.tsx"),
  "utf8"
);
const css = readFileSync(join(root, "../../styles/org.css"), "utf8");

function simulateShareUi(onTimelineShare: (body: string) => Promise<void>) {
  let state: TimelineShareUiState = initialTimelineShareUi();
  const dispatch = (action: TimelineShareUiAction) => {
    state = reduceTimelineShareUi(state, action);
  };
  return {
    get state() {
      return state;
    },
    tapShareButton() {
      dispatch({ type: "tap_open" });
    },
    edit(body: string) {
      dispatch({ type: "edit", body });
    },
    async tapSubmit() {
      if (state.submitting || !state.composerOpen) return;
      const body = state.body;
      dispatch({ type: "tap_submit" });
      try {
        await onTimelineShare(body);
        dispatch({ type: "success" });
      } catch (err) {
        dispatch({
          type: "failure",
          message: err instanceof Error ? err.message : "failed",
        });
      }
    },
  };
}

test("tapping タイムラインにシェア opens the intro sheet and does not call the API", async () => {
  const calls: string[] = [];
  const ui = simulateShareUi(async (body) => {
    calls.push(body);
  });
  ui.tapShareButton();
  assert.equal(ui.state.composerOpen, true);
  assert.equal(ui.state.submitting, false);
  assert.equal(timelineShareTapSendsRequest({ type: "tap_open" }), false);
  assert.deepEqual(calls, []);
  ui.edit("新歓に来てね");
  await ui.tapSubmit();
  assert.deepEqual(calls, ["新歓に来てね"]);
  assert.equal(ui.state.composerOpen, false);
});

test("submit failure keeps the intro sheet open with an error", async () => {
  const ui = simulateShareUi(async () => {
    throw new Error("同じイベントは10分間に1回までシェアできます。");
  });
  ui.tapShareButton();
  await ui.tapSubmit();
  assert.equal(ui.state.composerOpen, true);
  assert.equal(ui.state.submitting, false);
  assert.match(ui.state.error || "", /10分間/);
});

test("view first click only opens the composer; API stays on the page submit path", () => {
  const timelineCase = view.split('case "timeline_share":')[1] || "";
  assert.match(timelineCase.slice(0, 180), /dispatchShare\(\{\s*type:\s*"tap_open"\s*\}\)/);
  assert.equal(timelineCase.slice(0, 180).includes("onTimelineShare("), false);
  assert.equal(view.includes("shareOrganizationEventToTimeline"), false);
  assert.equal(view.includes("EventTimelineShareSheet"), true);
  assert.equal(view.includes('data-action={action}'), true);
  assert.equal(view.includes("htmlFor=\"event-timeline-body\""), false);
  assert.match(
    view,
    /action === "timeline_share" && shareUi\.submitting/
  );
  assert.match(
    view,
    /action !== "timeline_share" && busy/
  );
});

test("page timeline share bypasses silent busyRef run() and still reports errors", () => {
  const handler = page.split("onTimelineShare=")[1] || "";
  const shareBlock = handler.slice(0, 1200);
  assert.equal(shareBlock.includes("void run("), false);
  assert.equal(shareBlock.includes("busyRef.current"), false);
  assert.equal(shareBlock.includes("shareOrganizationEventToTimeline"), true);
  assert.equal(shareBlock.includes("invalidateTimelineFeed"), true);
  assert.equal(shareBlock.includes("throw err"), true);
  assert.equal(shareBlock.includes("setActionError"), true);
  assert.equal(shareBlock.includes("setShareNote"), true);
});

test("intro sheet portals to document.body with iOS viewport and 44px taps", () => {
  assert.equal(sheet.includes("createPortal"), true);
  assert.equal(sheet.includes("document.body"), true);
  assert.equal(sheet.includes("visualViewport"), true);
  assert.equal(sheet.includes("紹介文（任意）"), true);
  assert.equal(sheet.includes("シェアする"), true);
  assert.equal(sheet.includes('data-action="submit-timeline-share"'), true);
  assert.match(
    css,
    /\.org-event-share-modal\.compose-modal\s*\{[^}]*z-index: 500/
  );
  assert.match(
    css,
    /\.org-event-share-modal \.btn\s*\{[^}]*min-height: 44px/
  );
  assert.match(
    css,
    /\.org-event-detail \.org-event-timeline-share-open\s*\{[^}]*touch-action: manipulation/
  );
  assert.match(
    css,
    /\.org-event-share-modal__textarea\s*\{[^}]*font-size: 16px/
  );
});
