import assert from "node:assert/strict";
import test from "node:test";
import { matchChromeMode } from "./chrome.ts";
import {
  isDmInboxPath,
  isMessageStackPath,
  isStackPopState,
} from "./messageStack.ts";

test("message stack includes inbox, personal, group, and recruiting rooms", () => {
  assert.equal(isMessageStackPath("/dm"), true);
  assert.equal(isMessageStackPath("/app/dm"), true);
  assert.equal(isMessageStackPath("/dm/4"), true);
  assert.equal(isMessageStackPath("/dm/groups/12"), true);
  assert.equal(isMessageStackPath("/organizations/circle/recruiting-chat"), true);
  assert.equal(isMessageStackPath("/orgs/circle/recruiting-chat"), true);
  assert.equal(isMessageStackPath("/dm/recruiting/44"), true);
});

test("message stack excludes info, create, course, trade, and other details", () => {
  assert.equal(isMessageStackPath("/dm/groups/12/info"), false);
  assert.equal(isMessageStackPath("/dm/groups/new"), false);
  assert.equal(isMessageStackPath("/dm/requests"), false);
  assert.equal(isMessageStackPath("/courses/8/talk"), false);
  assert.equal(isMessageStackPath("/flea/chats/3"), false);
  assert.equal(isMessageStackPath("/"), false);
  assert.equal(isMessageStackPath("/notifications"), false);
  assert.equal(
    isMessageStackPath("/organizations/circle/recruiting-chat/info"),
    false
  );
});

test("inbox path and stack-pop state helpers", () => {
  assert.equal(isDmInboxPath("/dm"), true);
  assert.equal(isDmInboxPath("/dm/4"), false);
  assert.equal(isStackPopState({ waseStackPop: true }), true);
  assert.equal(isStackPopState({}), false);
  assert.equal(isStackPopState(null), false);
});

test("inbox stays on detail chrome; rooms stay conversation chrome", () => {
  assert.equal(matchChromeMode("/dm"), "detail");
  assert.equal(matchChromeMode("/dm/4"), "conversation");
  assert.equal(matchChromeMode("/dm/groups/12"), "conversation");
  assert.equal(
    matchChromeMode("/organizations/circle/recruiting-chat"),
    "conversation"
  );
});
