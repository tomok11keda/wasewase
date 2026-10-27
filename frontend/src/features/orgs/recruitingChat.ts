/** Types and parsers for Phase 3-B recruiting-chat JSON. Do not invent fields. */

export const RECRUITING_CHAT_NAME_MAX = 120;
export const RECRUITING_CHAT_DESCRIPTION_MAX = 2000;
export const MAX_RECRUITING_INVITEES = 20;
export const RECRUITING_INVITE_QUERY_MIN = 2;

export type RecruitingJoinMode = "open" | "approval" | "invite";
export type RecruitingListingStatus = "open" | "closed";
export type RecruitingVisibility = "public" | "private";
export type RecruitingPostingMode = "all" | "admins";
export type RecruitingMembershipStatus =
  | "not_joined"
  | "pending"
  | "invited"
  | "joined"
  | "rejected"
  | "closed";

export type RecruitingInviteAuthor = {
  id: number | null;
  username: string;
  display_name: string;
  avatar_url: string;
  initial: string;
};

export type RecruitingInvitation = {
  id: number;
  status: string;
  created_at: string;
  responded_at: string | null;
  organization_id: number | null;
  organization_slug: string;
  organization_name: string;
  organization_avatar_url: string;
  chat_name: string;
  inviter: RecruitingInviteAuthor | null;
  invitee?: RecruitingInviteAuthor | null;
};

export type RecruitingInviteCandidate = RecruitingInviteAuthor;

export type RecruitingInviteSkip = {
  id: number | null;
  reason: string;
};

export type RecruitingChat = {
  id: number | null;
  organization_id: number | null;
  name: string;
  description: string;
  join_mode: RecruitingJoinMode;
  listing_status: RecruitingListingStatus;
  visibility: RecruitingVisibility;
  posting_mode: RecruitingPostingMode;
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
  can_invite: boolean;
  can_pin?: boolean;
  pinned_message_id?: number | null;
  room_id: number | null;
  pending_count?: number;
  would_auto_approve_on_open?: boolean;
  invitation?: RecruitingInvitation | null;
};

export type RecruitingChatEnvelope = {
  ok: boolean;
  recruiting_chat: RecruitingChat | null;
  recruiting_chats?: RecruitingChat[];
  can_create: boolean;
  can_manage: boolean;
  chat_count?: number;
  chat_max?: number;
};

export type RecruitingChatSummary = {
  id: number | null;
  name: string;
  join_mode: RecruitingJoinMode;
  listing_status: RecruitingListingStatus;
  visibility?: RecruitingVisibility;
  posting_mode?: RecruitingPostingMode;
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
  visibility: RecruitingVisibility;
  posting_mode: RecruitingPostingMode;
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
  if (value === "approval" || value === "invite") return value;
  return "open";
}

function parseVisibility(value: unknown): RecruitingVisibility {
  return value === "private" ? "private" : "public";
}

function parsePostingMode(value: unknown): RecruitingPostingMode {
  return value === "admins" ? "admins" : "all";
}

function parseListingStatus(value: unknown): RecruitingListingStatus {
  return value === "closed" ? "closed" : "open";
}

function parseMembershipStatus(value: unknown): RecruitingMembershipStatus {
  if (
    value === "pending" ||
    value === "invited" ||
    value === "joined" ||
    value === "rejected" ||
    value === "closed"
  ) {
    return value;
  }
  return "not_joined";
}

export function parseRecruitingChatId(raw: unknown): number | null {
  const n = Number(raw);
  return Number.isInteger(n) && n > 0 ? n : null;
}

export function parseRecruitingChatIdFromSearch(search: string): number | null {
  const params = new URLSearchParams(
    search.startsWith("?") ? search.slice(1) : search
  );
  return parseRecruitingChatId(params.get("chat") || params.get("chat_id"));
}

function withChatQuery(path: string, chatId?: number | null): string {
  const id = parseRecruitingChatId(chatId);
  return id ? `${path}?chat=${id}` : path;
}

export function recruitingChatPath(slug: string, chatId?: number | null): string {
  return withChatQuery(`/organizations/${slug}/recruiting-chat`, chatId);
}

export function recruitingChatInfoPath(slug: string, chatId?: number | null): string {
  return withChatQuery(`${recruitingChatPath(slug)}/info`, chatId);
}

export function recruitingChatSettingsPath(
  slug: string,
  chatId?: number | null
): string {
  return withChatQuery(`${recruitingChatPath(slug)}/settings`, chatId);
}

export function recruitingChatCreatePath(slug: string): string {
  return `${recruitingChatPath(slug)}/settings?create=1`;
}

export function recruitingChatApplicationsPath(
  slug: string,
  chatId?: number | null
): string {
  return withChatQuery(`${recruitingChatPath(slug)}/applications`, chatId);
}

export function recruitingChatMembersPath(
  slug: string,
  chatId?: number | null
): string {
  return withChatQuery(`${recruitingChatPath(slug)}/members`, chatId);
}

export function recruitingChatInvitesPath(
  slug: string,
  chatId?: number | null
): string {
  return withChatQuery(`${recruitingChatPath(slug)}/invites`, chatId);
}

export function recruitingChatInvitePath(slug: string): string {
  return `${recruitingChatPath(slug)}/invite`;
}

export function envelopeChats(envelope: RecruitingChatEnvelope | null): RecruitingChat[] {
  if (!envelope) return [];
  if (envelope.recruiting_chats && envelope.recruiting_chats.length) {
    return envelope.recruiting_chats;
  }
  return envelope.recruiting_chat ? [envelope.recruiting_chat] : [];
}

/** Open the chat hub, a specific chat, or the create screen. */
export function resolveRecruitingChatDestination(
  envelope: RecruitingChatEnvelope,
  slug: string
): { path: string; action: "open" | "create" } | null {
  const chats = envelopeChats(envelope);
  if (chats.length > 1 || envelope.can_manage) {
    if (chats.length) {
      return { path: recruitingChatPath(slug), action: "open" };
    }
  }
  const chat = chats[0] || envelope.recruiting_chat;
  if (chat?.id) {
    return { path: recruitingChatPath(slug, chat.id), action: "open" };
  }
  if (envelope.can_create) {
    return { path: recruitingChatCreatePath(slug), action: "create" };
  }
  return null;
}

export type RecruitingInviteOpenState =
  | "pending"
  | "responded"
  | "missing"
  | "login"
  | "error";

/** Map API/session outcome to the invitee detail screen. Do not treat every
 * 404 as cancelled — that hid pending invites the inbox could still show. */
export function recruitingInviteOpenState(args: {
  authenticated: boolean;
  error: string | null;
  invitation: RecruitingInvitation | null;
}): RecruitingInviteOpenState {
  if (!args.authenticated) return "login";
  if (args.invitation) {
    return args.invitation.status === "pending" ? "pending" : "responded";
  }
  if (args.error === "unauthorized") return "login";
  if (
    args.error === "not_found" ||
    args.error === "forbidden" ||
    args.error === "invalid_payload"
  ) {
    return "missing";
  }
  if (args.error) return "error";
  return "missing";
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
  if (mode === "approval") return "承認制";
  if (mode === "invite") return "招待制";
  return "自由参加";
}

export function visibilityLabel(visibility: RecruitingVisibility): string {
  return visibility === "private" ? "非公開" : "公開";
}

export function postingModeLabel(mode: RecruitingPostingMode): string {
  return mode === "admins" ? "管理者のみ投稿" : "参加者も投稿";
}

export function listingStatusLabel(status: RecruitingListingStatus): string {
  return status === "closed" ? "募集停止" : "募集中";
}

export function membershipStatusLabel(
  status: RecruitingMembershipStatus
): string {
  if (status === "pending") return "承認待ち";
  if (status === "invited") return "招待されています";
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
      return "この団体の団体チャットはすでに作成されています。";
    case "chat_limit_reached":
      return "作成できる団体チャットの上限に達しています。";
    case "chat_id_required":
      return "対象の団体チャットを選んでください。";
    case "invalid_visibility":
      return "公開範囲が正しくありません。";
    case "invalid_posting_mode":
      return "投稿権限が正しくありません。";
    case "invite_only":
      return "このチャットは招待された人だけ参加できます。";
    case "forbidden":
      return "この操作を行う権限がありません。";
    case "not_found":
      return "団体チャットが見つからないか、表示できません。";
    case "unauthorized":
      return "ログインが必要です。";
    case "not_joinable":
      return "現在は参加できません。";
    case "already_member":
      return "すでに参加しています。";
    case "already_pending":
      return "すでに参加を申請しています。";
    case "not_pending":
      return "有効な申請または招待がありません。";
    case "not_member":
      return "このチャットの参加者ではありません。";
    case "confirm_auto_approve_required":
      return "承認待ちの申請があるため、自由参加への切り替えには確認が必要です。";
    case "rate_limited":
      return "短時間に操作が集中しています。少し待ってからもう一度お試しください。";
    case "busy":
      return "混み合っています。少し待ってからもう一度お試しください。";
    case "too_many_invites":
      return `一度に招待できるのは${MAX_RECRUITING_INVITEES}人までです。`;
    case "no_invitees":
      return "招待する学生を選んでください。";
    case "listing_closed":
      return "募集停止中のため、新しい招待は送れません。";
    case "organization_suspended":
      return "この団体は現在利用停止中です。";
    case "blocked":
      return "このユーザーは招待できません。";
    case "inactive":
      return "この団体チャットは現在利用できません。";
    default:
      return fallback;
  }
}

export function recruitingInviteSkipLabel(reason: string): string {
  switch (reason) {
    case "already_member":
      return "すでに参加しています";
    case "already_pending":
      return "招待済みです";
    case "blocked":
      return "ブロック関係のため招待できません";
    case "cooldown":
      return "辞退後しばらくは再招待できません";
    case "private":
      return "非公開アカウントのため招待できません";
    case "self":
      return "自分自身は招待できません";
    case "inactive":
      return "このアカウントは招待できません";
    default:
      return "招待できませんでした";
  }
}

export function parseRecruitingInviteAuthor(
  raw: unknown
): RecruitingInviteAuthor | null {
  if (!raw || typeof raw !== "object") return null;
  const data = raw as Record<string, unknown>;
  const id = asFiniteNumber(data.id);
  const displayName = asString(data.display_name);
  const username = asString(data.username);
  return {
    id,
    username,
    display_name: displayName,
    avatar_url: asString(data.avatar_url),
    initial:
      asString(data.initial) ||
      (displayName || username || "?").slice(0, 1),
  };
}

export function parseRecruitingInvitation(
  raw: unknown
): RecruitingInvitation | null {
  if (!raw || typeof raw !== "object") return null;
  const data = raw as Record<string, unknown>;
  const id = asFiniteNumber(data.id);
  if (id == null) return null;
  return {
    id,
    status: asString(data.status) || "pending",
    created_at: asString(data.created_at),
    responded_at:
      data.responded_at == null || data.responded_at === ""
        ? null
        : asString(data.responded_at),
    organization_id: asFiniteNumber(data.organization_id),
    organization_slug: asString(data.organization_slug),
    organization_name: asString(data.organization_name),
    organization_avatar_url: asString(data.organization_avatar_url),
    chat_name: asString(data.chat_name),
    inviter: parseRecruitingInviteAuthor(data.inviter),
    invitee: parseRecruitingInviteAuthor(data.invitee) || undefined,
  };
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
    visibility: parseVisibility(data.visibility),
    posting_mode: parsePostingMode(data.posting_mode),
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
    visibility: summary.visibility || "public",
    posting_mode: summary.posting_mode || "all",
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
    can_invite: asBool(data.can_invite),
    can_pin: asBool(data.can_pin),
    pinned_message_id:
      data.pinned_message_id == null
        ? null
        : asFiniteNumber(data.pinned_message_id),
    room_id: summary.room_id,
  };
  if ("pending_count" in data) {
    chat.pending_count = asFiniteNumber(data.pending_count) ?? 0;
  }
  if ("would_auto_approve_on_open" in data) {
    chat.would_auto_approve_on_open = asBool(data.would_auto_approve_on_open);
  }
  if ("invitation" in data) {
    chat.invitation = parseRecruitingInvitation(data.invitation);
  }
  return chat;
}

export function parseRecruitingChatEnvelope(
  data: Record<string, unknown>
): RecruitingChatEnvelope | null {
  if (data.ok === false) return null;
  const raw = data.recruiting_chat;
  const listed = Array.isArray(data.recruiting_chats)
    ? data.recruiting_chats
        .map(parseRecruitingChat)
        .filter((row): row is RecruitingChat => row != null)
    : [];
  if (raw == null) {
    return {
      ok: true,
      recruiting_chat: listed[0] ?? null,
      recruiting_chats: listed,
      can_create: asBool(data.can_create),
      can_manage: asBool(data.can_manage),
      chat_count: asFiniteNumber(data.chat_count) ?? listed.length,
      chat_max: asFiniteNumber(data.chat_max) ?? undefined,
    };
  }
  const chat = parseRecruitingChat(raw);
  if (!chat) return null;
  const chats = listed.length ? listed : [chat];
  return {
    ok: true,
    recruiting_chat: chat,
    recruiting_chats: chats,
    can_create: asBool(data.can_create),
    can_manage: asBool(data.can_manage) || chat.can_manage,
    chat_count: asFiniteNumber(data.chat_count) ?? chats.length,
    chat_max: asFiniteNumber(data.chat_max) ?? undefined,
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
  const visibility = chat?.visibility === "private" ? "private" : "public";
  const joinMode =
    visibility === "private" || chat?.join_mode === "invite"
      ? "invite"
      : chat?.join_mode === "approval"
        ? "approval"
        : "open";
  return {
    name: chat?.name || "",
    description: chat?.description || "",
    join_mode: joinMode,
    listing_status:
      visibility === "private" || chat?.listing_status === "closed"
        ? "closed"
        : "open",
    visibility,
    posting_mode: chat?.posting_mode === "admins" ? "admins" : "all",
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
  if (
    form.join_mode !== "open" &&
    form.join_mode !== "approval" &&
    form.join_mode !== "invite"
  ) {
    errors.join_mode = "参加方式を選択してください。";
  }
  if (form.visibility !== "public" && form.visibility !== "private") {
    errors.visibility = "公開範囲を選択してください。";
  }
  if (form.posting_mode !== "all" && form.posting_mode !== "admins") {
    errors.posting_mode = "投稿権限を選択してください。";
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
  return envelopeChats(envelope).length > 0 || envelope.recruiting_chat != null;
}

/** Admin chrome stays hidden until the server confirms manage/create. */
export function canShowRecruitingManageNav(input: {
  hydrated: boolean;
  canManage: boolean;
  canCreate?: boolean;
}): boolean {
  if (!input.hydrated) return false;
  return input.canManage || Boolean(input.canCreate);
}
