import assert from "node:assert/strict";
import test from "node:test";
import { matchChromeMode, matchDetailChrome } from "./chrome.ts";
import { isConversationPath } from "./tabs.ts";

test("recruiting chat room uses conversation chrome so the composer can use the keyboard", () => {
  assert.equal(
    isConversationPath("/organizations/circle/recruiting-chat"),
    true
  );
  assert.equal(isConversationPath("/orgs/circle/recruiting-chat"), true);
  assert.equal(isConversationPath("/app/organizations/circle/recruiting-chat"), true);
  assert.equal(isConversationPath("/dm/recruiting/44"), true);
  assert.equal(
    matchChromeMode("/organizations/circle/recruiting-chat"),
    "conversation"
  );
});

test("recruiting admin pages stay on detail chrome and do not reuse the message thread", () => {
  assert.equal(
    isConversationPath("/organizations/circle/recruiting-chat/info"),
    false
  );
  assert.equal(
    isConversationPath("/organizations/circle/recruiting-chat/settings"),
    false
  );
  assert.equal(
    isConversationPath("/organizations/circle/recruiting-chat/applications"),
    false
  );
  assert.equal(
    isConversationPath("/organizations/circle/recruiting-chat/members"),
    false
  );
  assert.equal(
    matchDetailChrome("/organizations/circle/recruiting-chat/info")?.title,
    "チャット詳細"
  );
  assert.equal(
    matchDetailChrome("/organizations/circle/recruiting-chat/info")?.back.to,
    "/organizations/circle/recruiting-chat"
  );
  assert.equal(
    matchDetailChrome("/organizations/circle/recruiting-chat/settings")?.title,
    "新歓チャット設定"
  );
  assert.equal(
    matchDetailChrome("/organizations/circle/recruiting-chat/applications")?.title,
    "参加申請"
  );
  assert.equal(
    matchDetailChrome("/dm/groups/12/info")?.title,
    "グループ情報"
  );
  assert.equal(isConversationPath("/dm/groups/12/info"), false);
  assert.equal(
    matchDetailChrome("/organizations/circle/recruiting-chat/settings")?.back.to,
    "/organizations/circle/recruiting-chat/info"
  );
});

test("existing dm group and course rooms stay conversations", () => {
  assert.equal(isConversationPath("/dm/groups/12"), true);
  assert.equal(isConversationPath("/dm/4"), true);
  assert.equal(isConversationPath("/courses/8/talk"), true);
  assert.equal(isConversationPath("/flea/chats/3"), true);
  assert.equal(isConversationPath("/dm"), false);
  assert.equal(matchChromeMode("/dm/groups/12/info"), "detail");
  assert.equal(matchChromeMode("/organizations/circle/recruiting-chat/info"), "detail");
});
