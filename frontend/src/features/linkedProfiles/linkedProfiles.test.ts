import assert from "node:assert/strict";
import test from "node:test";
import type { MeResponse } from "../../lib/api.ts";
import {
  canAddLinkedProfile,
  linkedProfileMax,
  linkedProfilesFromMe,
  shouldOpenOwnProfileAfterSwitch,
} from "./linkedProfiles.ts";

function me(partial: Partial<MeResponse> = {}): MeResponse {
  return {
    authenticated: true,
    is_browse_mode: false,
    react_spa_enabled: true,
    user: {
      id: 11,
      email: "a@waseda.jp",
      username: "alpha",
      display_name: "Alpha",
      avatar_url: "",
      initial: "A",
    },
    unread_notifications: 0,
    dm_unread_total: 0,
    ...partial,
  };
}

test("falls back to the current user when linked_profiles is missing", () => {
  const rows = linkedProfilesFromMe(me());
  assert.equal(rows.length, 1);
  assert.equal(rows[0]?.id, 11);
  assert.equal(rows[0]?.is_current, true);
});

test("uses server linked_profiles and add flag", () => {
  const rows = linkedProfilesFromMe(
    me({
      can_add_linked_profile: false,
      linked_profiles: [
        {
          id: 11,
          username: "alpha",
          display_name: "Alpha",
          avatar_url: "",
          initial: "A",
          is_current: true,
          is_credential: true,
        },
        {
          id: 22,
          username: "beta",
          display_name: "Beta",
          avatar_url: "",
          initial: "B",
          is_current: false,
          is_credential: false,
        },
      ],
    })
  );
  assert.equal(rows.length, 2);
  assert.equal(canAddLinkedProfile(me({ can_add_linked_profile: true })), true);
  assert.equal(canAddLinkedProfile(me({ can_add_linked_profile: false })), false);
});

test("linked profile max comes from the server payload", () => {
  assert.equal(linkedProfileMax(me()), 2);
  assert.equal(linkedProfileMax(me({ linked_profile_max: 3 })), 3);
});

test("own-profile path follows the newly selected user after a switch", () => {
  assert.equal(shouldOpenOwnProfileAfterSwitch("/users/11/posts", 11, 22), true);
  assert.equal(shouldOpenOwnProfileAfterSwitch("/users/11", 11, 22), true);
  assert.equal(shouldOpenOwnProfileAfterSwitch("/", 11, 22), false);
  assert.equal(shouldOpenOwnProfileAfterSwitch("/users/99/posts", 11, 22), false);
});
