import assert from "node:assert/strict";
import test from "node:test";
import {
  autoApproveConfirmMessage,
  inboxSpaHref,
  joinModeLabel,
  listingStatusLabel,
  parseRecruitingApplication,
  parseRecruitingChat,
  parseRecruitingChatEnvelope,
  parseRecruitingChatSummary,
  parseRecruitingMember,
  parseRecruitingRoom,
  recruitingChatInfoPath,
  recruitingChatPath,
  shouldConfirmAutoApprove,
  shouldShowRecruitingSection,
  validateRecruitingChatForm,
} from "./recruitingChat.ts";

test("parses organization profile recruiting_chat summary from real API fields", () => {
  const summary = parseRecruitingChatSummary({
    id: 3,
    name: "2026新歓チャット",
    join_mode: "open",
    listing_status: "open",
    membership_status: "not_joined",
    can_join: true,
    can_apply: false,
    can_manage: false,
    room_id: null,
    member_count: 4,
  });
  assert.ok(summary);
  assert.equal(summary?.name, "2026新歓チャット");
  assert.equal(summary?.can_join, true);
  assert.equal(summary?.room_id, null);
  assert.equal(summary?.member_count, 4);
});

test("parses full recruiting chat including manager auto-approve fields", () => {
  const chat = parseRecruitingChat({
    id: 9,
    organization_id: 2,
    name: "新歓",
    description: "説明",
    join_mode: "approval",
    listing_status: "open",
    is_active: true,
    member_count: 1,
    viewer_state: "none",
    membership_status: "not_joined",
    can_manage: true,
    can_discover: true,
    can_list_publicly: true,
    can_join: false,
    can_apply: true,
    can_leave: false,
    can_withdraw: false,
    can_send: true,
    room_id: 44,
    pending_count: 2,
    would_auto_approve_on_open: true,
  });
  assert.ok(chat);
  assert.equal(chat?.join_mode, "approval");
  assert.equal(chat?.pending_count, 2);
  assert.equal(chat?.would_auto_approve_on_open, true);
  assert.equal(chat?.room_id, 44);
});

test("parses limited closed payload without inventing a name", () => {
  const chat = parseRecruitingChat({
    membership_status: "closed",
    join_mode: "open",
    listing_status: "closed",
    can_join: false,
    can_apply: false,
    can_manage: false,
    room_id: null,
  });
  assert.ok(chat);
  assert.equal(chat?.name, "");
  assert.equal(chat?.membership_status, "closed");
  assert.equal(chat?.can_join, false);
});

test("hides the profile section when no chat and viewer cannot create", () => {
  assert.equal(
    shouldShowRecruitingSection({
      ok: true,
      recruiting_chat: null,
      can_create: false,
      can_manage: false,
    }),
    false
  );
  assert.equal(
    shouldShowRecruitingSection({
      ok: true,
      recruiting_chat: null,
      can_create: true,
      can_manage: true,
    }),
    true
  );
});

test("parses GET envelope with can_create when chat is missing", () => {
  const envelope = parseRecruitingChatEnvelope({
    ok: true,
    recruiting_chat: null,
    can_create: true,
    can_manage: true,
  });
  assert.ok(envelope);
  assert.equal(envelope?.recruiting_chat, null);
  assert.equal(envelope?.can_create, true);
});

test("application parser ignores email even if a backend leak appears", () => {
  const row = parseRecruitingApplication({
    id: 11,
    user_id: 5,
    username: "student",
    display_name: "学生",
    avatar_url: "",
    status: "pending",
    created_at: "2026-04-01T12:00:00+09:00",
    reviewed_at: null,
    email: "student@waseda.jp",
  });
  assert.ok(row);
  assert.equal(row?.display_name, "学生");
  assert.equal("email" in row!, false);
});

test("parses members and room payloads from dedicated recruiting APIs", () => {
  const member = parseRecruitingMember({
    user_id: 8,
    username: "owner",
    display_name: "代表",
    avatar_url: "/media/a.png",
    joined_at: "2026-04-01T12:00:00+09:00",
    role: "member",
  });
  assert.equal(member?.user_id, 8);
  const room = parseRecruitingRoom({
    id: 44,
    kind: "recruiting",
    name: "新歓",
    can_send: true,
    latest_id: 90,
    member_count: 3,
    viewer_role: "manager",
    organization_id: 2,
    organization_slug: "circle",
    organization_name: "公開サークル",
    membership_status: "joined",
  });
  assert.equal(room?.kind, "recruiting");
  assert.equal(room?.organization_slug, "circle");
});

test("confirm auto-approve only when switching approval to open with pending", () => {
  const chat = parseRecruitingChat({
    id: 1,
    name: "新歓",
    join_mode: "approval",
    listing_status: "open",
    membership_status: "joined",
    can_manage: true,
    can_send: true,
    room_id: 1,
    pending_count: 3,
    would_auto_approve_on_open: true,
  });
  assert.equal(shouldConfirmAutoApprove(chat, "open"), true);
  assert.equal(shouldConfirmAutoApprove(chat, "approval"), false);
  assert.match(autoApproveConfirmMessage(3), /3件/);
});

test("inbox spa paths stay basename-relative and match recruiting route", () => {
  assert.equal(
    inboxSpaHref("/organizations/circle/recruiting-chat"),
    "/organizations/circle/recruiting-chat"
  );
  assert.equal(
    inboxSpaHref("/app/organizations/circle/recruiting-chat"),
    "/organizations/circle/recruiting-chat"
  );
  assert.equal(inboxSpaHref("/dm/3"), "/dm/3");
  assert.equal(recruitingChatPath("circle"), "/organizations/circle/recruiting-chat");
});

test("pending and closed viewers never receive a room_id in parsed JSON", () => {
  const pending = parseRecruitingChat({
    id: 2,
    name: "新歓",
    join_mode: "approval",
    listing_status: "open",
    membership_status: "pending",
    can_join: false,
    can_apply: false,
    can_send: false,
    room_id: null,
  });
  assert.equal(pending?.membership_status, "pending");
  assert.equal(pending?.room_id, null);
  assert.equal(pending?.can_send, false);
  const lost = parseRecruitingChatEnvelope({
    ok: false,
    error: "forbidden",
  });
  assert.equal(lost, null);
});

test("create form validation matches backend name/description limits", () => {
  const errors = validateRecruitingChatForm({
    name: "  ",
    description: "x".repeat(2001),
    join_mode: "open",
    listing_status: "open",
  });
  assert.ok(errors.name);
  assert.ok(errors.description);
  assert.equal(joinModeLabel("approval"), "承認制");
  assert.equal(listingStatusLabel("closed"), "募集停止");
  assert.equal(
    recruitingChatInfoPath("circle"),
    "/organizations/circle/recruiting-chat/info"
  );
});
