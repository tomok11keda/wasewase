import assert from "node:assert/strict";
import test from "node:test";
import {
  bootHeaderTitle,
  bootShowsBottomNav,
  bootShowsHomeSortTabs,
  bootSkeletonKind,
} from "./bootSkeleton.ts";

test("home and main tabs use a timeline-shaped boot skeleton", () => {
  assert.equal(bootSkeletonKind("/"), "timeline");
  assert.equal(bootSkeletonKind("/app"), "timeline");
  assert.equal(bootSkeletonKind("/app/"), "timeline");
  assert.equal(bootSkeletonKind("/communities"), "timeline");
  assert.equal(bootSkeletonKind("/search"), "timeline");
  assert.equal(bootSkeletonKind("/flea"), "timeline");
  assert.equal(bootSkeletonKind("/timetable"), "timeline");
});

test("deep links use a neutral skeleton and never encode personal data", () => {
  assert.equal(bootSkeletonKind("/notifications"), "neutral");
  assert.equal(bootSkeletonKind("/dm"), "neutral");
  assert.equal(bootSkeletonKind("/dm/99"), "neutral");
  assert.equal(bootSkeletonKind("/posts/12"), "neutral");
  assert.equal(bootSkeletonKind("/users/42/posts"), "neutral");
  assert.equal(bootSkeletonKind("/orgs/secret-club"), "neutral");
  assert.equal(bootHeaderTitle("/users/42/posts"), "プロフィール");
  assert.equal(bootHeaderTitle("/orgs/secret-club"), "団体");
  assert.equal(bootHeaderTitle("/notifications"), "通知");
  assert.equal(bootHeaderTitle("/posts/12"), "投稿");
  assert.equal(bootHeaderTitle("/dm"), "メッセージ");
});

test("conversation deep links hide the decorative bottom nav", () => {
  assert.equal(bootShowsBottomNav("/"), true);
  assert.equal(bootShowsBottomNav("/notifications"), true);
  assert.equal(bootShowsBottomNav("/dm"), true);
  assert.equal(bootShowsBottomNav("/dm/12"), false);
  assert.equal(bootShowsBottomNav("/flea/chats/3"), false);
});

test("main tabs hide the center title like the live shell", () => {
  assert.equal(bootHeaderTitle("/"), null);
  assert.equal(bootHeaderTitle("/communities"), null);
  assert.equal(bootHeaderTitle("/search"), null);
});

test("decorative sort tabs appear only on the home timeline boot", () => {
  assert.equal(bootShowsHomeSortTabs("/"), true);
  assert.equal(bootShowsHomeSortTabs("/app/"), true);
  assert.equal(bootShowsHomeSortTabs("/search"), false);
  assert.equal(bootShowsHomeSortTabs("/flea"), false);
  assert.equal(bootShowsHomeSortTabs("/communities"), false);
  assert.equal(bootShowsHomeSortTabs("/notifications"), false);
  assert.equal(bootShowsHomeSortTabs("/posts/12"), false);
});
