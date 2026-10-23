/** Types and parsers for Phase 3-B recruiting-chat JSON. Do not invent fields. */

export const RECRUITING_CHAT_NAME_MAX = 120;
export const RECRUITING_CHAT_DESCRIPTION_MAX = 2000;

export type RecruitingJoinMode = "open" | "approval";
export type RecruitingListingStatus = "open" | "closed";
export type RecruitingMembershipStatus =
  | "not_joined"
  | "pending"
  | "joined"
  | "rejected"
  | "closed";

export type RecruitingChat = {
  id: number | null;
  organization_id: number | null;
  name: string;
  description: string;
  join_mode: RecruitingJoinMode;
  listing_status: RecruitingListingStatus;
  is_active: boolean;
  member_count: number;
  viewer_state: string;
  membership_status: RecruitingMembershipStatus;
  can_manage: boolean;
  can_discover: boolean;
  can_list_publicly: boolean;
  can_join: boolean;
  can_apply: boolean;
  can_leave: boolean;
  can_withdraw: boolean;
  can_send: boolean;
  room_id: number | null;
  pending_count?: number;
  would_auto_approve_on_open?: boolean;
};

export type RecruitingChatEnvelope = {
  ok: boolean;
  recruiting_chat: RecruitingChat | null;
  can_create: boolean;
  can_manage: boolean;
};

export type RecruitingChatSummary = {
  id: number | null;
  name: string;
  join_mode: RecruitingJoinMode;
  listing_status: RecruitingListingStatus;
  membership_status: RecruitingMembershipStatus;
  can_join: boolean;
  can_apply: boolean;
  can_manage: boolean;
  room_id: number | null;
  member_count: number;
};

export type RecruitingApplication = {
  id: number;
  user_id: number | null;
  username: string;
  display_name: string;
  avatar_url: string;
  status: string;
  created_at: string;
  reviewed_at: string | null;
};

export type RecruitingMember = {
  user_id: number | null;
  username: string;
  display_name: string;
  avatar_url: string;
  joined_at: string;
  role: string;
};

export type RecruitingRoom = {
  id: number;
  kind: "recruiting";
  name: string;
  can_send: boolean;
  latest_id: number;
  member_count: number;
  viewer_role: string;
  organization_id: number | null;
  organization_slug: string;
  organization_name: string;
  membership_status: string;
};

export type RecruitingChatForm = {
  name: string;
  description: string;
  join_mode: RecruitingJoinMode;
  listing_status: RecruitingListingStatus;
};

function asString(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function asFiniteNumber(value: unknown): number | null {
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

function asBool(value: unknown): boolean {
  return value === true;
}

function parseJoinMode(value: unknown): RecruitingJoinMode {
  return value === "approval" ? "approval" : "open";
}

function parseListingStatus(value: unknown): RecruitingListingStatus {
  return value === "closed" ? "closed" : "open";
}

function parseMembershipStatus(value: unknown): RecruitingMembershipStatus {
  if (
    value === "pending" ||
    value === "joined" ||
    value === "rejected" ||
    value === "closed"
  ) {
    return value;
  }
  return "not_joined";
}

export function recruitingChatPath(slug: string): string {
  return `/organizations/${slug}/recruiting-chat`;
}

export function recruitingChatSettingsPath(slug: string): string {
  return `${recruitingChatPath(slug)}/settings`;
}

export function recruitingChatApplicationsPath(slug: string): string {
  return `${recruitingChatPath(slug)}/applications`;
}

export function recruitingChatMembersPath(slug: string): string {
  return `${recruitingChatPath(slug)}/members`;
}

/** Inbox spa_path is basename-relative; tolerate a leftover /app prefix. */
export function inboxSpaHref(spaPath: string): string {
  const raw = (spaPath || "").trim();
  if (!raw) return "/dm";
  if (raw === "/app") return "/";
  if (raw.startsWith("/app/")) return raw.slice(4) || "/";
  return raw.startsWith("/") ? raw : `/${raw}`;
}

export function joinModeLabel(mode: RecruitingJoinMode): string {
  return mode === "approval" ? "承認制" : "自由参加";
}

export function listingStatusLabel(status: RecruitingListingStatus): string {
  return status === "closed" ? "募集停止" : "募集中";
}

export function membershipStatusLabel(
  status: RecruitingMembershipStatus
): string {
  if (status === "pending") return "承認待ち";
  if (status === "joined") return "参加中";
  if (status === "rejected") return "参加が承認されませんでした";
  if (status === "closed") return "現在は新規参加を受け付けていません";
  return "未参加";
}

export function recruitingChatErrorMessage(
  code: string | undefined,
  fallback: string
): string {
  switch (code) {
    case "empty_name":
      return "チャット名を入力してください。";
    case "name_too_long":
      return `チャット名は${RECRUITING_CHAT_NAME_MAX}文字以内で入力してください。`;
    case "description_too_long":
      return `説明は${RECRUITING_CHAT_DESCRIPTION_MAX}文字以内で入力してください。`;
    case "invalid_join_mode":
      return "参加方式が正しくありません。";
    case "invalid_listing_status":
      return "募集状態が正しくありません。";
    case "already_exists":
      return "この団体の新歓チャットはすでに作成されています。";
    case "forbidden":
      return "この操作を行う権限がありません。";
    case "not_found":
      return "新歓チャットが見つからないか、表示できません。";
    case "unauthorized":
      return "ログインが必要です。";
    case "not_joinable":
      return "現在は参加できません。";
    case "already_member":
      return "すでに参加しています。";
    case "already_pending":
      return "すでに参加を申請しています。";
    case "not_pending":
      return "取り下げられる申請がありません。";
    case "not_member":
      return "このチャットの参加者ではありません。";
    case "confirm_auto_approve_required":
      return "承認待ちの申請があるため、自由参加への切り替えには確認が必要です。";
    case "rate_limited":
      return "短時間に操作が集中しています。少し待ってからもう一度お試しください。";
    default:
      return fallback;
  }
}

export function parseRecruitingChatSummary(
  raw: unknown
): RecruitingChatSummary | null {
  if (!raw || typeof raw !== "object") return null;
  const data = raw as Record<string, unknown>;
  const membership_status = parseMembershipStatus(data.membership_status);
  const join_mode = parseJoinMode(data.join_mode);
  const listing_status = parseListingStatus(data.listing_status);
  const id = asFiniteNumber(data.id);
  const roomId = data.room_id == null ? null : asFiniteNumber(data.room_id);
  return {
    id,
    name: asString(data.name),
    join_mode,
    listing_status,
    membership_status,
    can_join: asBool(data.can_join),
    can_apply: asBool(data.can_apply),
    can_manage: asBool(data.can_manage),
    room_id: roomId,
    member_count: asFiniteNumber(data.member_count) ?? 0,
  };
}

export function parseRecruitingChat(raw: unknown): RecruitingChat | null {
  if (!raw || typeof raw !== "object") return null;
  const data = raw as Record<string, unknown>;
  const summary = parseRecruitingChatSummary(data);
  if (!summary) return null;
  const chat: RecruitingChat = {
    id: summary.id,
    organization_id: asFiniteNumber(data.organization_id),
    name: summary.name,
    description: asString(data.description),
    join_mode: summary.join_mode,
    listing_status: summary.listing_status,
    is_active: data.is_active !== false,
    member_count: summary.member_count,
    viewer_state: asString(data.viewer_state),
    membership_status: summary.membership_status,
    can_manage: summary.can_manage,
    can_discover: asBool(data.can_discover),
    can_list_publicly: asBool(data.can_list_publicly),
    can_join: summary.can_join,
    can_apply: summary.can_apply,
    can_leave: asBool(data.can_leave),
    can_withdraw: asBool(data.can_withdraw),
    can_send: asBool(data.can_send),
    room_id: summary.room_id,
  };
  if ("pending_count" in data) {
    chat.pending_count = asFiniteNumber(data.pending_count) ?? 0;
  }
  if ("would_auto_approve_on_open" in data) {
    chat.would_auto_approve_on_open = asBool(data.would_auto_approve_on_open);
  }
  return chat;
}

export function parseRecruitingChatEnvelope(
  data: Record<string, unknown>
): RecruitingChatEnvelope | null {
  if (data.ok === false) return null;
  const raw = data.recruiting_chat;
  if (raw == null) {
    return {
      ok: true,
      recruiting_chat: null,
      can_create: asBool(data.can_create),
      can_manage: asBool(data.can_manage),
    };
  }
  const chat = parseRecruitingChat(raw);
  if (!chat) return null;
  return {
    ok: true,
    recruiting_chat: chat,
    can_create: asBool(data.can_create),
    can_manage: asBool(data.can_manage) || chat.can_manage,
  };
}

export function parseRecruitingApplication(
  raw: unknown
): RecruitingApplication | null {
  if (!raw || typeof raw !== "object") return null;
  const data = raw as Record<string, unknown>;
  const id = asFiniteNumber(data.id);
  if (id == null) return null;
  return {
    id,
    user_id: asFiniteNumber(data.user_id),
    username: asString(data.username),
    display_name: asString(data.display_name),
    avatar_url: asString(data.avatar_url),
    status: asString(data.status) || "pending",
    created_at: asString(data.created_at),
    reviewed_at:
      data.reviewed_at == null || data.reviewed_at === ""
        ? null
        : asString(data.reviewed_at),
  };
}

export function parseRecruitingMember(raw: unknown): RecruitingMember | null {
  if (!raw || typeof raw !== "object") return null;
  const data = raw as Record<string, unknown>;
  return {
    user_id: asFiniteNumber(data.user_id),
    username: asString(data.username),
    display_name: asString(data.display_name),
    avatar_url: asString(data.avatar_url),
    joined_at: asString(data.joined_at),
    role: asString(data.role),
  };
}

export function parseRecruitingRoom(raw: unknown): RecruitingRoom | null {
  if (!raw || typeof raw !== "object") return null;
  const data = raw as Record<string, unknown>;
  const id = asFiniteNumber(data.id);
  if (id == null) return null;
  return {
    id,
    kind: "recruiting",
    name: asString(data.name),
    can_send: asBool(data.can_send),
    latest_id: asFiniteNumber(data.latest_id) ?? 0,
    member_count: asFiniteNumber(data.member_count) ?? 0,
    viewer_role: asString(data.viewer_role),
    organization_id: asFiniteNumber(data.organization_id),
    organization_slug: asString(data.organization_slug),
    organization_name: asString(data.organization_name),
    membership_status: asString(data.membership_status) || "joined",
  };
}

export function formFromRecruitingChat(
  chat: RecruitingChat | null
): RecruitingChatForm {
  return {
    name: chat?.name || "",
    description: chat?.description || "",
    join_mode: chat?.join_mode === "approval" ? "approval" : "open",
    listing_status: chat?.listing_status === "closed" ? "closed" : "open",
  };
}

export function validateRecruitingChatForm(
  form: RecruitingChatForm
): Record<string, string> {
  const errors: Record<string, string> = {};
  const name = form.name.trim();
  if (!name) {
    errors.name = "チャット名を入力してください。";
  } else if (name.length > RECRUITING_CHAT_NAME_MAX) {
    errors.name = `チャット名は${RECRUITING_CHAT_NAME_MAX}文字以内で入力してください。`;
  }
  if (form.description.length > RECRUITING_CHAT_DESCRIPTION_MAX) {
    errors.description = `説明は${RECRUITING_CHAT_DESCRIPTION_MAX}文字以内で入力してください。`;
  }
  if (form.join_mode !== "open" && form.join_mode !== "approval") {
    errors.join_mode = "参加方式を選択してください。";
  }
  if (form.listing_status !== "open" && form.listing_status !== "closed") {
    errors.listing_status = "募集状態を選択してください。";
  }
  return errors;
}

export function autoApproveConfirmMessage(pendingCount: number): string {
  const count = Math.max(0, pendingCount);
  return `承認待ちが${count}件あります。自由参加に切り替えると、全員が自動承認されます。続行しますか？`;
}

export function shouldConfirmAutoApprove(
  current: RecruitingChat | null,
  nextJoinMode: RecruitingJoinMode
): boolean {
  if (!current) return false;
  if (current.join_mode !== "approval" || nextJoinMode !== "open") return false;
  return Boolean(
    current.would_auto_approve_on_open || (current.pending_count || 0) > 0
  );
}

export function formatRecruitingDate(value: string): string {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("ja-JP", {
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function shouldShowRecruitingSection(
  envelope: RecruitingChatEnvelope | null
): boolean {
  if (!envelope) return false;
  if (envelope.can_create || envelope.can_manage) return true;
  return envelope.recruiting_chat != null;
}
