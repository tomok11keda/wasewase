import assert from "node:assert/strict";
import test from "node:test";
import type { ThreadSummary } from "./api.ts";
import {
  communityThreadDetailState,
  publicThreadPreview,
  readInitialThread,
} from "./threadNav.ts";

const summary: ThreadSummary = {
  id: 8,
  title: "練習日程",
  body: "本文",
  body_preview: "本文",
  created_at: "2026-10-24T00:00:00Z",
  updated_at: "2026-10-24T00:00:00Z",
  replies_count: 4,
  can_delete: true,
  is_mine: true,
  can_report: true,
  anonymous_label: "1",
  community: {
    id: 3,
    slug: "circle",
    name: "サークル",
    description: "desc",
    faculty: "政経",
    category: "club",
    is_official: false,
  },
};

test("public thread previews strip delete/report flags from list snapshots", () => {
  const preview = publicThreadPreview(summary);
  assert.equal(preview.can_delete, false);
  assert.equal(preview.is_mine, false);
  assert.equal(preview.can_report, false);
  assert.equal(preview.title, "練習日程");
});

test("readInitialThread hydrates a matching thread without replies or privileges", () => {
  const state = communityThreadDetailState(summary);
  const next = readInitialThread(state, 8);
  assert.ok(next);
  assert.equal(next?.id, 8);
  assert.equal(next?.title, "練習日程");
  assert.equal(next?.can_delete, false);
  assert.equal(next?.can_report, false);
  assert.deepEqual(next?.replies, []);
  assert.equal(readInitialThread(state, 99), null);
  assert.equal(readInitialThread(null, 8), null);
});
