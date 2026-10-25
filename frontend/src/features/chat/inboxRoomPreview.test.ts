import assert from "node:assert/strict";
import test from "node:test";
import type { InboxItem } from "../dm/api.ts";
import {
  clearInboxCache,
  writeInboxCache,
} from "../dm/inboxCache.ts";
import {
  headerPreviewFromInboxItem,
  readDmHeaderPreview,
} from "./inboxRoomPreview.ts";

function item(overrides: Partial<InboxItem> = {}): InboxItem {
  return {
    kind: "dm",
    room_id: 7,
    display_name: "太郎",
    subtitle: "相手",
    status_label: "",
    thumbnail_url: "https://example.com/a.png",
    unread_count: 1,
    is_blocked: false,
    updated_at: "",
    latest_body: "secret body must not leak",
    latest_sender_name: "secret sender",
    partner: {
      id: 2,
      username: "taro",
      display_name: "太郎",
      avatar_url: "https://example.com/a.png",
      initial: "太",
    },
    product_id: null,
    spa_path: "/dm/7",
    ...overrides,
  };
}

test("inbox header previews never copy message bodies", () => {
  const preview = headerPreviewFromInboxItem(item());
  const blob = JSON.stringify(preview);
  assert.equal(preview.title, "太郎");
  assert.equal(blob.includes("secret body must not leak"), false);
  assert.equal(blob.includes("latest_body"), false);
  assert.equal(blob.includes("secret sender"), false);
});

test("blocked DM previews hide the partner identity", () => {
  const preview = headerPreviewFromInboxItem(item({ is_blocked: true }));
  assert.equal(preview.title, "不明なユーザー");
  assert.equal(preview.avatarInitial, "?");
  assert.equal(preview.avatarUrl, undefined);
});

test("trade and recruiting previews stay header-only", () => {
  const trade = headerPreviewFromInboxItem(
    item({
      kind: "trade",
      display_name: "自転車",
      status_label: "取引中",
      thumbnail_url: "https://example.com/bike.png",
    })
  );
  const recruiting = headerPreviewFromInboxItem(
    item({
      kind: "recruiting",
      display_name: "新歓チャット",
      organization_name: "テニスサークル",
    })
  );
  assert.equal(trade.title, "自転車");
  assert.equal(trade.avatarShape, "rounded");
  assert.equal(recruiting.subtitle, "テニスサークル");
  assert.equal(JSON.stringify(trade).includes("secret body must not leak"), false);
  assert.equal(JSON.stringify(recruiting).includes("secret body must not leak"), false);
});

test("header preview is scoped to the current user and matching room", () => {
  clearInboxCache();
  writeInboxCache({
    userId: 11,
    tab: "all",
    items: [item()],
    counts: {},
    requestCount: 0,
    fetchedAt: Date.now(),
  });
  assert.equal(readDmHeaderPreview(11, 7)?.title, "太郎");
  assert.equal(readDmHeaderPreview(22, 7), null);
  assert.equal(readDmHeaderPreview(11, 99), null);
  clearInboxCache();
});
