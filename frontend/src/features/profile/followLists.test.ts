import assert from "node:assert/strict";
import test from "node:test";
import {
  FOLLOW_LIST_TABS,
  followListEmptyCopy,
  followListForbiddenCopy,
  followListKindFromPath,
  followListLoadErrorCopy,
  followListPath,
  followListTitle,
} from "./followLists.ts";

test("follow list paths keep deep links and default to followers", () => {
  assert.equal(followListKindFromPath("/users/9/followers"), "followers");
  assert.equal(followListKindFromPath("/app/users/9/following"), "following");
  assert.equal(followListKindFromPath("/users/9/mutuals"), "mutuals");
  assert.equal(followListKindFromPath("/users/9/followers/"), "followers");
  assert.equal(followListPath(9, "mutuals"), "/users/9/mutuals");
  assert.equal(
    `/api/v1/profile/9/${followListKindFromPath("/users/9/mutuals")}/`,
    "/api/v1/profile/9/mutuals/"
  );
  assert.equal(followListTitle("mutuals"), "共通の友達");
  assert.equal(followListEmptyCopy("following"), "フォロー中はまだいません");
});

test("follow list always exposes the three Instagram-style tabs", () => {
  assert.deepEqual(
    FOLLOW_LIST_TABS.map((tab) => tab.kind),
    ["mutuals", "followers", "following"]
  );
});

test("follow list errors stay user-facing for private, blocked, and missing users", () => {
  assert.equal(
    followListForbiddenCopy(),
    "非公開アカウントか、表示できない関係です。"
  );
  assert.equal(
    followListLoadErrorCopy("follow_list_404"),
    "このユーザーは見つかりません。"
  );
  assert.equal(followListLoadErrorCopy("load_failed"), "一覧を表示できません。");
});
