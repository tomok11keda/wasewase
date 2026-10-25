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

test("organization events use detail chrome and not the message thread", () => {
  assert.equal(isConversationPath("/organizations/circle/events/11"), false);
  assert.equal(matchChromeMode("/organizations/circle/events/11"), "detail");
  assert.equal(matchDetailChrome("/organizations/circle/events/11")?.title, "イベント");
  assert.equal(
    matchDetailChrome("/organizations/circle/events/11")?.back.to,
    "/orgs/circle"
  );
  assert.equal(
    matchDetailChrome("/organizations/circle/events/manage")?.title,
    "イベント管理"
  );
  assert.equal(
    matchDetailChrome("/organizations/circle/events/new")?.title,
    "イベントを作成"
  );
  assert.equal(
    matchDetailChrome("/organizations/circle/events/11/edit")?.title,
    "イベントを編集"
  );
  assert.equal(
    matchDetailChrome("/organizations/circle/events/11/registrations")?.title,
    "申込者"
  );
  assert.equal(
    matchDetailChrome("/organizations/circle/events/11/lottery")?.title,
    "抽選"
  );
  assert.equal(
    isConversationPath("/organizations/circle/events/11/lottery"),
    false
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
    isConversationPath("/organizations/circle/recruiting-chat/invites"),
    false
  );
  assert.equal(
    isConversationPath("/organizations/circle/recruiting-chat/invite"),
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
    "団体チャット設定"
  );
  assert.equal(
    matchDetailChrome("/organizations/circle/recruiting-chat/applications")?.title,
    "参加申請"
  );
  assert.equal(
    matchDetailChrome("/organizations/circle/recruiting-chat/invites")?.title,
    "学生を招待"
  );
  assert.equal(
    matchDetailChrome("/organizations/circle/recruiting-chat/invite")?.title,
    "団体チャット招待"
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

test("follow list chrome keeps profile back and titles per tab", () => {
  assert.equal(matchDetailChrome("/users/9/followers")?.title, "フォロワー");
  assert.equal(matchDetailChrome("/users/9/following")?.title, "フォロー中");
  assert.equal(matchDetailChrome("/users/9/mutuals")?.title, "共通の友達");
  assert.equal(
    matchDetailChrome("/users/9/mutuals")?.back.to,
    "/users/9/posts"
  );
});

test("settings header back prefers history so the account menu can reopen", () => {
  assert.equal(matchDetailChrome("/settings")?.back.kind, "history-or-fallback");
  assert.equal(matchDetailChrome("/settings")?.back.to, "/");
  assert.equal(matchDetailChrome("/settings/profile")?.title, "プロフィール設定");
  assert.equal(
    matchDetailChrome("/settings/profile")?.back.kind,
    "history-or-fallback"
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

test("inbox compose picker uses detail chrome and keeps personal/group/org paths", () => {
  assert.equal(isConversationPath("/dm/new"), false);
  assert.equal(matchChromeMode("/dm/new"), "detail");
  assert.equal(matchDetailChrome("/dm/new")?.title, "新しいチャット");
  assert.equal(matchDetailChrome("/dm/new/direct")?.title, "個人チャット");
  assert.equal(matchDetailChrome("/dm/new/org-chat")?.title, "団体チャット");
  assert.equal(matchDetailChrome("/dm/groups/new")?.title, "グループ作成");
  assert.equal(matchDetailChrome("/dm/groups/new")?.back.to, "/dm/new");
  assert.equal(
    matchDetailChrome("/dm/new")?.back.kind,
    "history-or-fallback"
  );
  assert.equal(
    matchDetailChrome("/dm/new/org-chat")?.back.kind,
    "history-or-fallback"
  );
});
