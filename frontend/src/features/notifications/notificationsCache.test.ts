import assert from "node:assert/strict";
import test from "node:test";
import {
  clearNotificationsCache,
  isNotificationsCacheFresh,
  NOTIFICATIONS_CACHE_FRESH_MS,
  readNotificationsCache,
  writeNotificationsCache,
  writeNotificationsCacheForUser,
  type NotificationsCacheEntry,
} from "./notificationsCache.ts";

function entry(
  userId: number,
  fetchedAt = Date.now()
): NotificationsCacheEntry {
  return {
    userId,
    items: [
      {
        id: userId,
        message: `secret-${userId}`,
        link: "",
        spa_path: "",
        is_read: false,
        created_at: "",
      },
    ],
    pendingFollowRequests: 1,
    fetchedAt,
  };
}

test("notifications cache is keyed by user id", () => {
  clearNotificationsCache();
  writeNotificationsCache(entry(11));
  writeNotificationsCache(entry(22));
  assert.equal(readNotificationsCache(11)?.items[0]?.message, "secret-11");
  assert.equal(readNotificationsCache(22)?.items[0]?.message, "secret-22");
  assert.equal(readNotificationsCache(33), null);
  clearNotificationsCache(11);
  assert.equal(readNotificationsCache(11), null);
  assert.equal(readNotificationsCache(22)?.userId, 22);
  clearNotificationsCache();
});

test("notifications cache rejects invalid user ids", () => {
  clearNotificationsCache();
  writeNotificationsCache(entry(0));
  writeNotificationsCache(entry(-3));
  assert.equal(readNotificationsCache(0), null);
  assert.equal(readNotificationsCache(-3), null);
});

test("mark-read overwrites the same user's cached rows", () => {
  clearNotificationsCache();
  writeNotificationsCache(entry(11));
  const previous = readNotificationsCache(11);
  assert.equal(previous?.items[0]?.is_read, false);
  writeNotificationsCache({
    ...previous!,
    items: previous!.items.map((item) => ({ ...item, is_read: true })),
    fetchedAt: Date.now(),
  });
  assert.equal(readNotificationsCache(11)?.items[0]?.is_read, true);
  assert.equal(readNotificationsCache(11)?.items[0]?.message, "secret-11");
  clearNotificationsCache();
});

test("delayed responses are not written after a user switch", () => {
  clearNotificationsCache();
  const started = entry(11);
  assert.equal(writeNotificationsCacheForUser(22, started), false);
  assert.equal(readNotificationsCache(11), null);
  assert.equal(writeNotificationsCacheForUser(11, started), true);
  assert.equal(readNotificationsCache(11)?.userId, 11);
  clearNotificationsCache();
});

test("soft refresh overwrites cached rows without inventing another user", () => {
  clearNotificationsCache();
  writeNotificationsCache(entry(11));
  const next = {
    ...entry(11),
    items: [
      {
        id: 99,
        message: "newer",
        link: "",
        spa_path: "",
        is_read: false,
        created_at: "",
      },
    ],
  };
  assert.equal(writeNotificationsCacheForUser(11, next), true);
  assert.equal(readNotificationsCache(11)?.items[0]?.message, "newer");
  assert.equal(readNotificationsCache(22), null);
  clearNotificationsCache();
});

test("notifications cache fresh window is short", () => {
  const now = 2_000_000;
  assert.equal(
    isNotificationsCacheFresh(
      entry(1, now - NOTIFICATIONS_CACHE_FRESH_MS + 1),
      now
    ),
    true
  );
  assert.equal(
    isNotificationsCacheFresh(entry(1, now - NOTIFICATIONS_CACHE_FRESH_MS), now),
    false
  );
});
