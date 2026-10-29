import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";
import {
  applyOpenedInboxRoomRead,
  nextDmUnreadTotal,
  shouldCommitUnreadFetch,
  unreadTotalAfterReadAttempt,
} from "./acknowledgeRoomRead.ts";
import {
  chooseInboxCacheEntry,
  clearInboxCache,
  readInboxCache,
  writeInboxCache,
  type InboxCacheEntry,
} from "./inboxCache.ts";
import type { InboxItem } from "./api.ts";

function dmItem(
  roomId: number,
  unread: number,
  extras: Partial<InboxItem> = {}
): InboxItem {
  return {
    kind: "dm",
    room_id: roomId,
    display_name: `room-${roomId}`,
    subtitle: "",
    status_label: "",
    thumbnail_url: "",
    unread_count: unread,
    is_blocked: false,
    updated_at: "",
    latest_body: "hello",
    latest_sender_name: "",
    partner: null,
    product_id: null,
    spa_path: `/dm/${roomId}`,
    ...extras,
  };
}

function cacheEntry(
  userId: number,
  items: InboxItem[],
  tab = "all"
): InboxCacheEntry {
  return {
    userId,
    tab,
    items,
    counts: { all: items.length },
    requestCount: 0,
    fetchedAt: Date.now(),
  };
}

test("opening one room zeros its unread and leaves the badge total for other rooms", () => {
  clearInboxCache();
  writeInboxCache(
    cacheEntry(11, [dmItem(1, 3), dmItem(2, 2), { ...dmItem(9, 4), kind: "recruiting" }])
  );
  const first = applyOpenedInboxRoomRead({
    userId: 11,
    kind: "dm",
    roomId: 1,
    currentTotal: 9,
  });
  assert.equal(first.roomUnread, 3);
  assert.equal(first.nextTotal, 6);
  const cached = readInboxCache(11, "all");
  assert.equal(cached?.items.find((row) => row.room_id === 1)?.unread_count, 0);
  assert.equal(cached?.items.find((row) => row.room_id === 2)?.unread_count, 2);
  assert.equal(cached?.items.find((row) => row.room_id === 9)?.unread_count, 4);

  const second = applyOpenedInboxRoomRead({
    userId: 11,
    kind: "dm",
    roomId: 1,
    currentTotal: first.nextTotal,
  });
  assert.equal(second.roomUnread, 0);
  assert.equal(second.nextTotal, 6);
  clearInboxCache();
});

test("read failure keeps the previous total until a server total arrives", () => {
  assert.equal(
    unreadTotalAfterReadAttempt({
      currentTotal: 5,
      roomUnread: 3,
      readSucceeded: false,
    }),
    5
  );
  assert.equal(
    unreadTotalAfterReadAttempt({
      currentTotal: 5,
      roomUnread: 3,
      readSucceeded: true,
    }),
    2
  );
  assert.equal(
    unreadTotalAfterReadAttempt({
      currentTotal: 2,
      roomUnread: 3,
      readSucceeded: true,
      serverTotal: 2,
    }),
    2
  );
  assert.equal(nextDmUnreadTotal(3, 10), 0);
});

test("stale unread fetches from another user or generation are ignored", () => {
  assert.equal(
    shouldCommitUnreadFetch({
      fetchGen: 2,
      currentGen: 2,
      startedUserId: 11,
      currentUserId: 11,
    }),
    true
  );
  assert.equal(
    shouldCommitUnreadFetch({
      fetchGen: 1,
      currentGen: 2,
      startedUserId: 11,
      currentUserId: 11,
    }),
    false
  );
  assert.equal(
    shouldCommitUnreadFetch({
      fetchGen: 2,
      currentGen: 2,
      startedUserId: 11,
      currentUserId: 22,
    }),
    false
  );
});

test("opening a room does not mix another account's inbox unread", () => {
  clearInboxCache();
  writeInboxCache(cacheEntry(11, [dmItem(1, 3)]));
  writeInboxCache(cacheEntry(22, [dmItem(1, 8)]));
  const result = applyOpenedInboxRoomRead({
    userId: 11,
    kind: "dm",
    roomId: 1,
    currentTotal: 3,
  });
  assert.equal(result.nextTotal, 0);
  assert.equal(readInboxCache(11, "all")?.items[0]?.unread_count, 0);
  assert.equal(readInboxCache(22, "all")?.items[0]?.unread_count, 8);
  clearInboxCache();
});

test("dm room page marks the opened thread read and refreshes badges", () => {
  const here = dirname(fileURLToPath(import.meta.url));
  const page = readFileSync(join(here, "../../pages/DmRoomPage.tsx"), "utf8");
  const session = readFileSync(join(here, "../../lib/session.tsx"), "utf8");
  assert.equal(page.includes('acknowledgeInboxRoomRead({ kind: "dm", roomId })'), true);
  assert.equal(page.includes("void refreshUnreadCounts()"), true);
  assert.equal(session.includes("dm_unread_total: nextDmUnreadTotal("), true);
  assert.equal(session.includes("unread_notifications: n, dm_unread_total: d"), true);
  assert.match(session, /UNREAD_POLL_MS = 60_000/);
});

test("an in-flight inbox fetch cannot restore unread after the room was opened", () => {
  clearInboxCache();
  writeInboxCache(cacheEntry(11, [dmItem(4, 3)]));
  applyOpenedInboxRoomRead({
    userId: 11,
    kind: "dm",
    roomId: 4,
    currentTotal: 3,
  });
  const patched = readInboxCache(11, "all");
  assert.equal(patched?.items[0]?.unread_count, 0);
  const stale = cacheEntry(11, [dmItem(4, 3)]);
  const chosen = chooseInboxCacheEntry({
    startedGeneration: 0,
    currentGeneration: 1,
    patched,
    fetched: stale,
  });
  assert.equal(chosen.items[0]?.unread_count, 0);
  assert.equal(
    chooseInboxCacheEntry({
      startedGeneration: 1,
      currentGeneration: 1,
      patched,
      fetched: stale,
    }).items[0]?.unread_count,
    3
  );
  clearInboxCache();
});
