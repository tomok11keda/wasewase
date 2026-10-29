import assert from "node:assert/strict";
import test from "node:test";
import {
  clearInboxCache,
  clearInboxRoomUnread,
  findInboxItemForUser,
  INBOX_CACHE_FRESH_MS,
  isInboxCacheFresh,
  readInboxCache,
  writeInboxCache,
  type InboxCacheEntry,
} from "./inboxCache.ts";

function entry(
  userId: number,
  tab = "all",
  fetchedAt = Date.now()
): InboxCacheEntry {
  return {
    userId,
    tab,
    items: [
      {
        kind: "dm",
        room_id: userId,
        display_name: `user-${userId}`,
        subtitle: "",
        status_label: "",
        thumbnail_url: "",
        unread_count: 0,
        is_blocked: false,
        updated_at: "",
        latest_body: "secret",
        latest_sender_name: "",
        partner: null,
        product_id: null,
        spa_path: `/dm/${userId}`,
      },
    ],
    counts: { all: 1 },
    requestCount: 0,
    fetchedAt,
  };
}

test("inbox cache is keyed by user id and never returns another user's rows", () => {
  clearInboxCache();
  writeInboxCache(entry(11));
  writeInboxCache(entry(22));
  assert.equal(readInboxCache(11, "all")?.items[0]?.display_name, "user-11");
  assert.equal(readInboxCache(22, "all")?.items[0]?.display_name, "user-22");
  assert.equal(readInboxCache(33, "all"), null);
  clearInboxCache(11);
  assert.equal(readInboxCache(11, "all"), null);
  assert.equal(readInboxCache(22, "all")?.userId, 22);
  clearInboxCache();
});

test("inbox lookup never returns another user's conversation", () => {
  clearInboxCache();
  writeInboxCache(entry(11));
  assert.equal(findInboxItemForUser(11, (row) => row.room_id === 11)?.display_name, "user-11");
  assert.equal(findInboxItemForUser(22, (row) => row.room_id === 11), null);
  assert.equal(findInboxItemForUser(null, (row) => row.room_id === 11), null);
  clearInboxCache();
});

test("inbox cache rejects invalid user ids", () => {
  clearInboxCache();
  writeInboxCache(entry(0));
  writeInboxCache(entry(-4));
  assert.equal(readInboxCache(0, "all"), null);
  assert.equal(readInboxCache(-4, "all"), null);
  assert.equal(readInboxCache(1, "all"), null);
});

test("clearing one room unread does not touch other rooms or users", () => {
  clearInboxCache();
  const user11 = entry(11);
  user11.items = [
    { ...user11.items[0]!, room_id: 1, unread_count: 3, spa_path: "/dm/1" },
    { ...user11.items[0]!, room_id: 2, unread_count: 2, spa_path: "/dm/2" },
  ];
  writeInboxCache(user11);
  const user22 = entry(22);
  user22.items = [{ ...user22.items[0]!, unread_count: 8 }];
  writeInboxCache(user22);
  assert.equal(clearInboxRoomUnread(11, "dm", 1), 3);
  assert.equal(readInboxCache(11, "all")?.items[0]?.unread_count, 0);
  assert.equal(readInboxCache(11, "all")?.items[1]?.unread_count, 2);
  assert.equal(readInboxCache(22, "all")?.items[0]?.unread_count, 8);
  assert.equal(clearInboxRoomUnread(11, "dm", 1), 0);
  clearInboxCache();
});

test("fresh window is short so the cache is not long-lived", () => {
  const now = 1_000_000;
  assert.equal(
    isInboxCacheFresh(entry(1, "all", now - INBOX_CACHE_FRESH_MS + 1), now),
    true
  );
  assert.equal(
    isInboxCacheFresh(entry(1, "all", now - INBOX_CACHE_FRESH_MS), now),
    false
  );
});
