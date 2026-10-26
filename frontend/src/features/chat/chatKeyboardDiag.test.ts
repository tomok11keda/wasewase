import assert from "node:assert/strict";
import test from "node:test";
import {
  isChatKeyboardDiagEnabled,
  readChatKeyboardDiagSnapshot,
} from "./chatKeyboardDiag.ts";

test("keyboard diag is off unless the query flag is exactly 1", () => {
  assert.equal(isChatKeyboardDiagEnabled(""), false);
  assert.equal(isChatKeyboardDiagEnabled("?tab=latest"), false);
  assert.equal(isChatKeyboardDiagEnabled("?chat_kb_diag=0"), false);
  assert.equal(isChatKeyboardDiagEnabled("?chat_kb_diag=1"), true);
  assert.equal(isChatKeyboardDiagEnabled("?q=hi&chat_kb_diag=1"), true);
});

test("diag snapshot is geometry-only and never copies message text", () => {
  const snap = readChatKeyboardDiagSnapshot({
    innerHeight: 844,
    scrollY: 12,
    visualViewport: { height: 508, offsetTop: 336 },
    frame: { height: 508, offsetTop: 336 },
    rects: {
      page: { top: 336, bottom: 844, height: 508 },
      compose: { top: 780, bottom: 844, height: 64 },
      input: { top: 790, bottom: 830, height: 40 },
      send: { top: 792, bottom: 832, height: 40 },
    },
  });
  assert.equal(snap.vvHeight, 508);
  assert.equal(snap.composeBottom, 844);
  assert.equal(snap.sendTop, 792);
  const keys = Object.keys(snap).join(",");
  assert.equal(keys.includes("body"), false);
  assert.equal(keys.includes("message"), false);
  assert.equal(keys.includes("email"), false);
});
