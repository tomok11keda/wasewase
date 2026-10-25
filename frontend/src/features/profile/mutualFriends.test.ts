import assert from "node:assert/strict";
import test from "node:test";
import {
  formatMutualFriendsLabel,
  parseMutualFriendsPreview,
} from "./mutualFriends.ts";

test("mutual friends preview refuses guessed counts and people", () => {
  assert.equal(parseMutualFriendsPreview(undefined), null);
  assert.equal(parseMutualFriendsPreview({ count: 0, users: [] }), null);
  assert.equal(parseMutualFriendsPreview({ users: [{ id: 1 }] }), null);
  const parsed = parseMutualFriendsPreview({
    count: 10,
    users: [
      { id: 1, display_name: "A", username: "a", avatar_url: "", initial: "A" },
      { id: 2, display_name: "B", username: "b", avatar_url: "/b.png", initial: "B" },
      { id: 3, display_name: "C", username: "c", avatar_url: "", initial: "C" },
      { id: 4, display_name: "D", username: "d", avatar_url: "", initial: "D" },
    ],
  });
  assert.equal(parsed?.count, 10);
  assert.equal(parsed?.users.length, 3);
  assert.equal(parsed?.users[2]?.display_name, "C");
});

test("mutual friends copy uses at most two names and the server count", () => {
  assert.equal(
    formatMutualFriendsLabel({
      count: 1,
      users: [
        { id: 1, display_name: "A", username: "a", avatar_url: "", initial: "A" },
      ],
    }),
    "Aさんがフォロー中"
  );
  assert.equal(
    formatMutualFriendsLabel({
      count: 2,
      users: [
        { id: 1, display_name: "A", username: "a", avatar_url: "", initial: "A" },
        { id: 2, display_name: "B", username: "b", avatar_url: "", initial: "B" },
      ],
    }),
    "Aさん、Bさんがフォロー中"
  );
  assert.equal(
    formatMutualFriendsLabel({
      count: 10,
      users: [
        { id: 1, display_name: "A", username: "a", avatar_url: "", initial: "A" },
        { id: 2, display_name: "B", username: "b", avatar_url: "", initial: "B" },
        { id: 3, display_name: "C", username: "c", avatar_url: "", initial: "C" },
      ],
    }),
    "Aさん、Bさん、ほか8人がフォロー中"
  );
  assert.equal(
    formatMutualFriendsLabel({
      count: 3,
      users: [
        { id: 1, display_name: "A", username: "a", avatar_url: "", initial: "A" },
        { id: 2, display_name: "B", username: "b", avatar_url: "", initial: "B" },
        { id: 3, display_name: "C", username: "c", avatar_url: "", initial: "C" },
      ],
    }),
    "Aさん、Bさん、ほか1人がフォロー中"
  );
  assert.equal(
    formatMutualFriendsLabel({ count: 4, users: [] }),
    "4人がフォロー中"
  );
});
