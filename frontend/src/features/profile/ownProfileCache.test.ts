import assert from "node:assert/strict";
import test from "node:test";
import type { ProfilePayload } from "./api.ts";
import {
  clearOwnProfileCache,
  invalidateOwnProfileCacheAfterEdit,
  isOwnProfileCacheFresh,
  OWN_PROFILE_CACHE_FRESH_MS,
  readOwnProfileCache,
  writeOwnProfileCache,
} from "./ownProfileCache.ts";

function profile(userId: number, isOwn = true): ProfilePayload {
  return {
    ok: true,
    user: {
      id: userId,
      username: `u${userId}`,
      display_name: `name-${userId}`,
      avatar_url: "",
      initial: "N",
      bio: "secret",
      department: "",
      grade: "",
      department_grade: "",
    },
    stats: {
      post_count: 0,
      product_count: 0,
      follower_count: 0,
      following_count: 0,
      left_label: "投稿",
      left_count: 0,
    },
    is_own: isOwn,
    is_following: false,
    is_private: false,
    follow_state: isOwn ? "self" : "none",
    can_view_content: true,
    is_blocked: false,
    can_send_dm: false,
    dm_room_id: null,
    show_safety_menu: !isOwn,
    can_view_timetable: true,
    is_timetable_public: true,
    can_view_bookmarks: isOwn,
  };
}

test("own profile cache stores only the viewer's own profile", () => {
  clearOwnProfileCache();
  writeOwnProfileCache(11, profile(22, false));
  assert.equal(readOwnProfileCache(11), null);
  writeOwnProfileCache(11, profile(22, true));
  assert.equal(readOwnProfileCache(11), null);
  writeOwnProfileCache(11, profile(11, true));
  assert.equal(readOwnProfileCache(11)?.profile.user.display_name, "name-11");
  assert.equal(readOwnProfileCache(22), null);
  writeOwnProfileCache(22, profile(22, true));
  assert.equal(readOwnProfileCache(11), null);
  assert.equal(readOwnProfileCache(22)?.viewerId, 22);
  clearOwnProfileCache(22);
  assert.equal(readOwnProfileCache(22), null);
});

test("successful own-profile edit invalidates only that viewer", () => {
  clearOwnProfileCache();
  writeOwnProfileCache(11, profile(11, true));
  writeOwnProfileCache(11, {
    ...profile(11, true),
    user: { ...profile(11, true).user, display_name: "古い名前" },
  });
  assert.equal(readOwnProfileCache(11)?.profile.user.display_name, "古い名前");
  invalidateOwnProfileCacheAfterEdit(22);
  assert.equal(readOwnProfileCache(11)?.profile.user.display_name, "古い名前");
  invalidateOwnProfileCacheAfterEdit(11);
  assert.equal(readOwnProfileCache(11), null);
});

test("failed own-profile edit leaves the cache untouched", () => {
  clearOwnProfileCache();
  writeOwnProfileCache(11, profile(11, true));
  assert.equal(readOwnProfileCache(11)?.profile.user.display_name, "name-11");
  invalidateOwnProfileCacheAfterEdit(0);
  assert.equal(readOwnProfileCache(11)?.profile.user.display_name, "name-11");
});

test("own profile cache fresh window is short", () => {
  const now = 3_000_000;
  writeOwnProfileCache(5, profile(5, true));
  const hit = readOwnProfileCache(5);
  assert.ok(hit);
  assert.equal(
    isOwnProfileCacheFresh({ ...hit, fetchedAt: now - OWN_PROFILE_CACHE_FRESH_MS + 1 }, now),
    true
  );
  assert.equal(
    isOwnProfileCacheFresh({ ...hit, fetchedAt: now - OWN_PROFILE_CACHE_FRESH_MS }, now),
    false
  );
  clearOwnProfileCache();
});
