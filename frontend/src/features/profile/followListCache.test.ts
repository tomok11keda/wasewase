import assert from "node:assert/strict";
import test from "node:test";
import {
  clearFollowListCache,
  readFollowListCache,
  writeFollowListCache,
} from "./followListCache.ts";

test("follow list cache does not leak across users after a switch", () => {
  writeFollowListCache("11:9:mutuals", {
    users: [
      {
        id: 2,
        username: "bob",
        display_name: "ボブ",
        avatar_url: "",
        initial: "ボ",
      },
    ],
    count: 1,
    forbidden: false,
    error: null,
  });
  assert.equal(readFollowListCache("11:9:mutuals")?.count, 1);
  assert.equal(readFollowListCache("22:9:mutuals"), null);
  clearFollowListCache();
  assert.equal(readFollowListCache("11:9:mutuals"), null);
});
