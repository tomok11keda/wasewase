import assert from "node:assert/strict";
import test from "node:test";
import {
  buildChatThread,
  chatDayKey,
  chatDayLabel,
  chatTimeLabel,
} from "./chatThread.ts";

test("parses existing chat timestamps without inventing a year", () => {
  assert.equal(chatDayKey("10/24 14:05"), "10/24");
  assert.equal(chatDayLabel("10/24 14:05"), "10月24日");
  assert.equal(chatTimeLabel("10/24 14:05"), "14:05");
  assert.equal(chatTimeLabel("not-a-date"), "not-a-date");
});

test("inserts a date divider when the calendar day changes", () => {
  const entries = buildChatThread([
    {
      id: 1,
      sender_id: 2,
      is_mine: false,
      created_at: "10/23 23:50",
      sender_name: "A",
    },
    {
      id: 2,
      sender_id: 2,
      is_mine: false,
      created_at: "10/24 00:10",
      sender_name: "A",
    },
  ]);
  assert.equal(entries.filter((e) => e.kind === "day").length, 2);
  assert.equal(entries[0].kind, "day");
  assert.equal(entries[2].kind, "day");
});

test("clusters consecutive messages from the same sender on the same day", () => {
  const entries = buildChatThread(
    [
      {
        id: 1,
        sender_id: 8,
        is_mine: false,
        created_at: "10/24 14:01",
        sender_name: "A",
      },
      {
        id: 2,
        sender_id: 8,
        is_mine: false,
        created_at: "10/24 14:02",
        sender_name: "A",
      },
      {
        id: 3,
        sender_id: 9,
        is_mine: true,
        created_at: "10/24 14:03",
        sender_name: "Me",
      },
    ],
    { showPeerAvatar: true, showPeerName: true }
  );
  const msgs = entries.filter((e) => e.kind === "message");
  assert.equal(msgs.length, 3);
  if (msgs[0].kind !== "message" || msgs[1].kind !== "message") {
    assert.fail("expected message entries");
  }
  assert.equal(msgs[0].layout.showAvatar, true);
  assert.equal(msgs[0].layout.showSender, true);
  assert.equal(msgs[0].layout.cluster, "start");
  assert.equal(msgs[1].layout.showAvatar, false);
  assert.equal(msgs[1].layout.showSender, false);
  assert.equal(msgs[1].layout.cluster, "end");
  assert.equal(msgs[1].layout.showTime, true);
  if (msgs[2].kind !== "message") assert.fail("expected mine");
  assert.equal(msgs[2].layout.showAvatar, false);
  assert.equal(msgs[2].layout.showSender, false);
});

test("personal DM can hide peer avatars and names", () => {
  const entries = buildChatThread(
    [
      {
        id: 1,
        sender_id: 4,
        is_mine: false,
        created_at: "10/24 09:00",
        sender_name: "Partner",
      },
    ],
    { showPeerAvatar: false, showPeerName: false }
  );
  const msg = entries.find((e) => e.kind === "message");
  assert.ok(msg && msg.kind === "message");
  assert.equal(msg.layout.showAvatar, false);
  assert.equal(msg.layout.showSender, false);
});
