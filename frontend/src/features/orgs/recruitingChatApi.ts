import {
  apiGetJson,
  apiPatchJson,
  apiPostJson,
  mutationErrorMessage,
} from "../../lib/http";
import type { ChatMessage } from "../dm/api";
import { OrganizationRequestError } from "./api";
import {
  parseRecruitingApplication,
  parseRecruitingChat,
  parseRecruitingChatEnvelope,
  parseRecruitingInvitation,
  parseRecruitingInviteAuthor,
  parseRecruitingMember,
  parseRecruitingRoom,
  recruitingChatErrorMessage,
  type RecruitingChat,
  type RecruitingChatEnvelope,
  type RecruitingChatForm,
  type RecruitingApplication,
  type RecruitingInvitation,
  type RecruitingInviteCandidate,
  type RecruitingInviteSkip,
  type RecruitingMember,
  type RecruitingRoom,
} from "./recruitingChat";

function orgChatUrl(
  slug: string,
  suffix = "",
  chatId?: number | null
): string {
  const base = `/api/v1/organizations/${encodeURIComponent(slug)}/recruiting-chat/${suffix}`;
  const id = Number(chatId);
  if (!Number.isInteger(id) || id <= 0) return base;
  return `${base}${base.includes("?") ? "&" : "?"}chat=${id}`;
}

function roomUrl(roomPk: number, suffix = ""): string {
  return `/api/v1/recruiting-chats/${roomPk}/${suffix}`;
}

function throwRecruitingError(
  status: number,
  error: string | undefined,
  data: Record<string, unknown>,
  fallback: string
): never {
  const code = error || `http_${status}`;
  throw new OrganizationRequestError(
    code,
    status,
    recruitingChatErrorMessage(
      code,
      mutationErrorMessage(code, fallback)
    ),
    {},
    data
  );
}

function chatFromResult(
  status: number,
  error: string | undefined,
  data: Record<string, unknown>,
  fallback: string
): RecruitingChat {
  if (status === 401 || error === "unauthorized") {
    throwRecruitingError(status, "unauthorized", data, fallback);
  }
  if (!data.ok || error) {
    throwRecruitingError(status, error, data, fallback);
  }
  const chat = parseRecruitingChat(data.recruiting_chat);
  if (!chat) {
    throwRecruitingError(status, "invalid_payload", data, fallback);
  }
  return chat;
}

export async function fetchRecruitingChat(
  slug: string,
  signal?: AbortSignal,
  chatId?: number | null
): Promise<RecruitingChatEnvelope> {
  const result = signal
    ? await fetch(orgChatUrl(slug, "", chatId), {
        credentials: "same-origin",
        headers: { Accept: "application/json" },
        signal,
      }).then(async (res) => {
        const data = (await res.json().catch(() => ({}))) as Record<
          string,
          unknown
        >;
        return {
          ok: Boolean(res.ok && data.ok !== false),
          status: res.status,
          data,
          error:
            typeof data.error === "string"
              ? data.error
              : res.ok
                ? undefined
                : `http_${res.status}`,
        };
      })
    : await apiGetJson(orgChatUrl(slug, "", chatId));
  if (result.status === 401 || result.error === "unauthorized") {
    throwRecruitingError(
      result.status,
      "unauthorized",
      result.data,
      "ログインが必要です。"
    );
  }
  if (result.status === 404 || result.error === "not_found") {
    throwRecruitingError(
      result.status,
      "not_found",
      result.data,
      "団体チャットが見つからないか、表示できません。"
    );
  }
  if (!result.ok) {
    throwRecruitingError(
      result.status,
      result.error,
      result.data,
      "団体チャットを読み込めませんでした。"
    );
  }
  const envelope = parseRecruitingChatEnvelope(result.data);
  if (!envelope) {
    throwRecruitingError(
      result.status,
      "invalid_payload",
      result.data,
      "団体チャットを読み込めませんでした。"
    );
  }
  return envelope;
}

export async function createRecruitingChat(
  slug: string,
  form: RecruitingChatForm
): Promise<RecruitingChat> {
  const result = await apiPostJson(orgChatUrl(slug), {
    name: form.name.trim(),
    description: form.description.trim(),
    join_mode: form.join_mode,
    listing_status: form.listing_status,
    visibility: form.visibility,
    posting_mode: form.posting_mode,
  });
  if (result.status === 201 || result.ok) {
    return chatFromResult(
      result.status,
      result.error,
      result.data,
      "団体チャットを作成できませんでした。"
    );
  }
  throwRecruitingError(
    result.status,
    result.error,
    result.data,
    "団体チャットを作成できませんでした。"
  );
}

export async function updateRecruitingChat(
  slug: string,
  patch: Partial<RecruitingChatForm> & {
    confirm_auto_approve?: boolean;
    is_active?: boolean;
    pinned_message_id?: number | null;
  },
  chatId?: number | null
): Promise<RecruitingChat> {
  const body: Record<string, unknown> = {};
  if (patch.name != null) body.name = patch.name.trim();
  if (patch.description != null) body.description = patch.description.trim();
  if (patch.join_mode != null) body.join_mode = patch.join_mode;
  if (patch.listing_status != null) body.listing_status = patch.listing_status;
  if (patch.visibility != null) body.visibility = patch.visibility;
  if (patch.posting_mode != null) body.posting_mode = patch.posting_mode;
  if (patch.confirm_auto_approve) body.confirm_auto_approve = true;
  if (patch.is_active === false) body.is_active = false;
  if (patch.pinned_message_id !== undefined) {
    body.pinned_message_id = patch.pinned_message_id;
  }
  const result = await apiPatchJson(orgChatUrl(slug, "", chatId), body);
  return chatFromResult(
    result.status,
    result.error,
    result.data,
    "設定を保存できませんでした。"
  );
}

export async function joinRecruitingChat(
  slug: string,
  chatId?: number | null
): Promise<RecruitingChat> {
  const result = await apiPostJson(orgChatUrl(slug, "join/", chatId));
  return chatFromResult(
    result.status,
    result.error,
    result.data,
    "参加できませんでした。"
  );
}

export async function leaveRecruitingChat(
  slug: string,
  chatId?: number | null
): Promise<RecruitingChat> {
  const result = await apiPostJson(orgChatUrl(slug, "leave/", chatId));
  return chatFromResult(
    result.status,
    result.error,
    result.data,
    "退出できませんでした。"
  );
}

export async function withdrawRecruitingChat(
  slug: string,
  chatId?: number | null
): Promise<RecruitingChat> {
  const result = await apiPostJson(orgChatUrl(slug, "withdraw/", chatId));
  return chatFromResult(
    result.status,
    result.error,
    result.data,
    "申請を取り下げられませんでした。"
  );
}

export async function fetchRecruitingApplications(
  slug: string,
  status = "pending",
  chatId?: number | null
): Promise<{ applications: RecruitingApplication[]; pending_count: number }> {
  const qs = status ? `?status=${encodeURIComponent(status)}` : "";
  const result = await apiGetJson(orgChatUrl(slug, `applications/${qs}`, chatId));
  if (!result.ok) {
    throwRecruitingError(
      result.status,
      result.error,
      result.data,
      "申請一覧を読み込めませんでした。"
    );
  }
  const rows = Array.isArray(result.data.applications)
    ? result.data.applications
    : [];
  return {
    applications: rows
      .map(parseRecruitingApplication)
      .filter((row): row is RecruitingApplication => row != null),
    pending_count: Number(result.data.pending_count || 0),
  };
}

export async function approveRecruitingApplication(
  slug: string,
  applicationId: number,
  chatId?: number | null
): Promise<RecruitingChat> {
  const result = await apiPostJson(
    orgChatUrl(slug, `applications/${applicationId}/approve/`, chatId)
  );
  return chatFromResult(
    result.status,
    result.error,
    result.data,
    "承認できませんでした。"
  );
}

export async function rejectRecruitingApplication(
  slug: string,
  applicationId: number,
  chatId?: number | null
): Promise<RecruitingChat> {
  const result = await apiPostJson(
    orgChatUrl(slug, `applications/${applicationId}/reject/`, chatId)
  );
  return chatFromResult(
    result.status,
    result.error,
    result.data,
    "拒否できませんでした。"
  );
}

export async function fetchRecruitingMembers(
  slug: string,
  chatId?: number | null
): Promise<RecruitingMember[]> {
  const result = await apiGetJson(orgChatUrl(slug, "members/", chatId));
  if (!result.ok) {
    throwRecruitingError(
      result.status,
      result.error,
      result.data,
      "参加者一覧を読み込めませんでした。"
    );
  }
  const rows = Array.isArray(result.data.members) ? result.data.members : [];
  return rows
    .map(parseRecruitingMember)
    .filter((row): row is RecruitingMember => row != null);
}

export async function searchRecruitingInviteCandidates(
  slug: string,
  query: string,
  signal?: AbortSignal,
  chatId?: number | null
): Promise<RecruitingInviteCandidate[]> {
  const qs = query.trim()
    ? `?q=${encodeURIComponent(query.trim())}`
    : "";
  const result = signal
    ? await fetch(orgChatUrl(slug, `invite-candidates/${qs}`, chatId), {
        credentials: "same-origin",
        headers: { Accept: "application/json" },
        signal,
      }).then(async (res) => {
        const data = (await res.json().catch(() => ({}))) as Record<
          string,
          unknown
        >;
        return {
          ok: Boolean(res.ok && data.ok !== false),
          status: res.status,
          data,
          error:
            typeof data.error === "string"
              ? data.error
              : res.ok
                ? undefined
                : `http_${res.status}`,
        };
      })
    : await apiGetJson(orgChatUrl(slug, `invite-candidates/${qs}`, chatId));
  if (!result.ok) {
    throwRecruitingError(
      result.status,
      result.error,
      result.data,
      "学生を検索できませんでした。"
    );
  }
  const rows = Array.isArray(result.data.users) ? result.data.users : [];
  return rows
    .map(parseRecruitingInviteAuthor)
    .filter((row): row is RecruitingInviteCandidate => row != null && row.id != null);
}

export async function fetchRecruitingInvites(
  slug: string,
  chatId?: number | null
): Promise<RecruitingInvitation[]> {
  const result = await apiGetJson(orgChatUrl(slug, "invites/", chatId));
  if (!result.ok) {
    throwRecruitingError(
      result.status,
      result.error,
      result.data,
      "招待一覧を読み込めませんでした。"
    );
  }
  const rows = Array.isArray(result.data.invites) ? result.data.invites : [];
  return rows
    .map(parseRecruitingInvitation)
    .filter((row): row is RecruitingInvitation => row != null);
}

export async function sendRecruitingInvites(
  slug: string,
  inviteeIds: number[],
  chatId?: number | null
): Promise<{
  invited_count: number;
  invited: RecruitingInvitation[];
  skipped: RecruitingInviteSkip[];
  recruiting_chat: RecruitingChat | null;
}> {
  const result = await apiPostJson(orgChatUrl(slug, "invites/", chatId), {
    invitee_ids: inviteeIds,
  });
  if (!result.ok) {
    throwRecruitingError(
      result.status,
      result.error,
      result.data,
      "招待を送信できませんでした。"
    );
  }
  const invitedRows = Array.isArray(result.data.invited)
    ? result.data.invited
    : [];
  const skippedRows = Array.isArray(result.data.skipped)
    ? result.data.skipped
    : [];
  const invited: RecruitingInvitation[] = [];
  for (const row of invitedRows) {
    if (!row || typeof row !== "object") continue;
    const data = row as Record<string, unknown>;
    const id = Number(data.id);
    if (!Number.isFinite(id)) continue;
    invited.push({
      id,
      status: "pending",
      created_at: "",
      responded_at: null,
      organization_id: null,
      organization_slug: "",
      organization_name: "",
      organization_avatar_url: "",
      chat_name: "",
      inviter: null,
      invitee: parseRecruitingInviteAuthor(data.invitee) || undefined,
    });
  }
  return {
    invited_count: Number(result.data.invited_count || 0),
    invited,
    skipped: skippedRows
      .map((row) => {
        if (!row || typeof row !== "object") return null;
        const data = row as Record<string, unknown>;
        return {
          id: Number.isFinite(Number(data.id)) ? Number(data.id) : null,
          reason: typeof data.reason === "string" ? data.reason : "invalid",
        };
      })
      .filter((row): row is RecruitingInviteSkip => row != null),
    recruiting_chat: parseRecruitingChat(result.data.recruiting_chat),
  };
}

export async function cancelRecruitingInvite(
  slug: string,
  invitationId: number,
  chatId?: number | null
): Promise<void> {
  const result = await apiPostJson(
    orgChatUrl(slug, `invites/${invitationId}/cancel/`, chatId)
  );
  if (!result.ok) {
    throwRecruitingError(
      result.status,
      result.error,
      result.data,
      "招待を取り消せませんでした。"
    );
  }
}

export async function fetchViewerRecruitingInvitation(
  slug: string,
  signal?: AbortSignal,
  chatId?: number | null
): Promise<{
  invitation: RecruitingInvitation;
  recruiting_chat: RecruitingChat | null;
}> {
  const result = signal
    ? await fetch(orgChatUrl(slug, "invitation/", chatId), {
        credentials: "same-origin",
        headers: { Accept: "application/json" },
        signal,
      }).then(async (res) => {
        const data = (await res.json().catch(() => ({}))) as Record<
          string,
          unknown
        >;
        return {
          ok: Boolean(res.ok && data.ok !== false),
          status: res.status,
          data,
          error:
            typeof data.error === "string"
              ? data.error
              : res.ok
                ? undefined
                : `http_${res.status}`,
        };
      })
    : await apiGetJson(orgChatUrl(slug, "invitation/", chatId));
  if (!result.ok) {
    throwRecruitingError(
      result.status,
      result.error,
      result.data,
      "招待を読み込めませんでした。"
    );
  }
  const invitation = parseRecruitingInvitation(result.data.invitation);
  if (!invitation) {
    throwRecruitingError(
      result.status,
      "invalid_payload",
      result.data,
      "招待を読み込めませんでした。"
    );
  }
  return {
    invitation,
    recruiting_chat: parseRecruitingChat(result.data.recruiting_chat),
  };
}

export async function acceptRecruitingInvitation(
  invitationId: number
): Promise<RecruitingChat> {
  const result = await apiPostJson(
    `/api/v1/recruiting-invitations/${invitationId}/accept/`
  );
  return chatFromResult(
    result.status,
    result.error,
    result.data,
    "参加できませんでした。"
  );
}

export async function declineRecruitingInvitation(
  invitationId: number
): Promise<void> {
  const result = await apiPostJson(
    `/api/v1/recruiting-invitations/${invitationId}/decline/`
  );
  if (!result.ok) {
    throwRecruitingError(
      result.status,
      result.error,
      result.data,
      "辞退できませんでした。"
    );
  }
}

export async function removeRecruitingMember(
  slug: string,
  userId: number,
  chatId?: number | null
): Promise<void> {
  const result = await apiPostJson(
    orgChatUrl(slug, `members/${userId}/remove/`, chatId)
  );
  if (!result.ok) {
    throwRecruitingError(
      result.status,
      result.error,
      result.data,
      "参加者を除外できませんでした。"
    );
  }
}

function accessDenied(status: number, error?: string): boolean {
  return (
    status === 403 ||
    status === 404 ||
    error === "forbidden" ||
    error === "not_found"
  );
}

async function fetchRoomJson(
  url: string,
  signal?: AbortSignal
): Promise<{
  ok: boolean;
  status: number;
  data: Record<string, unknown>;
  error?: string;
}> {
  const res = await fetch(url, {
    credentials: "same-origin",
    headers: { Accept: "application/json" },
    signal,
  });
  const data = (await res.json().catch(() => ({}))) as Record<string, unknown>;
  const error =
    typeof data.error === "string"
      ? data.error
      : res.ok
        ? undefined
        : `http_${res.status}`;
  return {
    ok: Boolean(res.ok && data.ok !== false),
    status: res.status,
    data,
    error,
  };
}

export async function fetchRecruitingRoom(
  roomPk: number,
  signal?: AbortSignal
): Promise<{
  room: RecruitingRoom;
  recruiting_chat: RecruitingChat | null;
  messages: ChatMessage[];
  has_more: boolean;
  next_before: number | null;
}> {
  const result = await fetchRoomJson(roomUrl(roomPk), signal);
  if (accessDenied(result.status, result.error)) {
    throwRecruitingError(
      result.status,
      result.error === "http_403" ? "forbidden" : result.error,
      result.data,
      "このチャットを表示する権限がありません。"
    );
  }
  if (!result.ok) {
    throwRecruitingError(
      result.status,
      result.error,
      result.data,
      "メッセージを読み込めませんでした。"
    );
  }
  const room = parseRecruitingRoom(result.data.room);
  if (!room) {
    throwRecruitingError(
      result.status,
      "invalid_payload",
      result.data,
      "メッセージを読み込めませんでした。"
    );
  }
  return {
    room,
    recruiting_chat: parseRecruitingChat(result.data.recruiting_chat),
    messages: Array.isArray(result.data.messages)
      ? (result.data.messages as ChatMessage[])
      : [],
    has_more: Boolean(result.data.has_more),
    next_before:
      result.data.next_before != null ? Number(result.data.next_before) : null,
  };
}

export async function pollRecruitingMessages(
  roomPk: number,
  after: number,
  signal?: AbortSignal
): Promise<{
  messages: ChatMessage[];
  latest_id: number;
  can_send?: boolean;
  has_more?: boolean;
  next_before?: number | null;
}> {
  const qs = after ? `?after=${after}` : "";
  const result = await fetchRoomJson(roomUrl(roomPk, `messages/${qs}`), signal);
  if (accessDenied(result.status, result.error)) {
    throwRecruitingError(
      result.status,
      result.error === "http_403" ? "forbidden" : result.error,
      result.data,
      "このチャットを表示する権限がありません。"
    );
  }
  if (!result.ok) {
    throw new Error(result.error || `poll_${result.status}`);
  }
  return {
    messages: Array.isArray(result.data.messages)
      ? (result.data.messages as ChatMessage[])
      : [],
    latest_id: Number(result.data.latest_id || 0),
    can_send: result.data.can_send === true,
    has_more: Boolean(result.data.has_more),
    next_before:
      result.data.next_before != null ? Number(result.data.next_before) : null,
  };
}

export async function fetchOlderRecruitingMessages(
  roomPk: number,
  before: number,
  signal?: AbortSignal
): Promise<{
  messages: ChatMessage[];
  has_more?: boolean;
  next_before?: number | null;
}> {
  const result = await fetchRoomJson(
    roomUrl(roomPk, `messages/?before=${before}`),
    signal
  );
  if (accessDenied(result.status, result.error)) {
    throwRecruitingError(
      result.status,
      result.error === "http_403" ? "forbidden" : result.error,
      result.data,
      "このチャットを表示する権限がありません。"
    );
  }
  if (!result.ok) {
    throw new Error(result.error || `history_${result.status}`);
  }
  return {
    messages: Array.isArray(result.data.messages)
      ? (result.data.messages as ChatMessage[])
      : [],
    has_more: Boolean(result.data.has_more),
    next_before:
      result.data.next_before != null ? Number(result.data.next_before) : null,
  };
}

export async function sendRecruitingMessage(
  roomPk: number,
  body: string,
  replyToId?: number | null
): Promise<ChatMessage> {
  const result = await apiPostJson(roomUrl(roomPk, "messages/send/"), {
    body,
    ...(replyToId ? { reply_to_id: replyToId } : {}),
  });
  if (!result.ok) {
    throwRecruitingError(
      result.status,
      result.error,
      result.data,
      "送信に失敗しました。"
    );
  }
  const message = result.data.message as ChatMessage | undefined;
  if (!message || typeof message.id !== "number") {
    throwRecruitingError(
      result.status,
      "invalid_payload",
      result.data,
      "送信に失敗しました。"
    );
  }
  return message;
}

export async function deleteRecruitingMessage(
  roomPk: number,
  messagePk: number
): Promise<ChatMessage> {
  const result = await apiPostJson(
    roomUrl(roomPk, `messages/${messagePk}/delete/`)
  );
  if (!result.ok) {
    throwRecruitingError(
      result.status,
      result.error,
      result.data,
      "削除に失敗しました。"
    );
  }
  return result.data.message as ChatMessage;
}
