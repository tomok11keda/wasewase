import { getCsrfToken } from "../timeline/api";

export type Author = {
  id: number | null;
  username: string;
  display_name: string;
  avatar_url: string;
  initial: string;
};

export type InboxItem = {
  kind: "dm" | "group" | "group_invite" | "trade" | "course";
  room_id: number;
  display_name: string;
  subtitle: string;
  status_label: string;
  thumbnail_url: string;
  unread_count: number;
  is_blocked: boolean;
  updated_at: string;
  latest_body: string;
  latest_sender_name: string;
  partner: Author | null;
  product_id: number | null;
  offering_id?: number | null;
  spa_path: string;
};

export type ChatReplyPreview = {
  id: number;
  sender_name: string;
  text_preview: string;
  is_unavailable?: boolean;
};

export type ChatMessage = {
  id: number;
  sender_id: number | null;
  sender_name: string;
  sender_initial?: string;
  avatar_url?: string;
  body: string;
  created_at: string;
  is_mine: boolean;
  is_read?: boolean;
  is_system?: boolean;
  is_deleted?: boolean;
  reply_to?: ChatReplyPreview | null;
  enrollment_role?: string | null;
  enrollment_label?: string | null;
};

export type DmRoomDetail = {
  id: number;
  kind: "dm";
  partner: Author | null;
  is_blocked: boolean;
  can_send: boolean;
  request_status?: "active" | "pending_request" | string;
  message_request?: {
    id: number;
    status: string;
    from_user: Author | null;
  } | null;
  latest_id: number;
};

export type MessageRequestItem = {
  id: number;
  room_id: number;
  status: string;
  from_user: Author & { department?: string; grade?: string };
  preview: string;
  updated_at: string;
  spa_path: string;
};

export type GroupInvitation = {
  id: number;
  status: "pending" | "accepted" | "declined" | string;
  inviter: Author | null;
  created_at?: string;
};

export type GroupRoomDetail = {
  id: number;
  kind: "group";
  name: string;
  members: Author[];
  member_count: number;
  can_send: boolean;
  membership_status: "member" | "pending_invite" | "none" | string;
  invitation: GroupInvitation | null;
  pending_invites: Array<{
    id: number;
    invitee: Author | null;
    inviter: Author | null;
    status: string;
  }>;
  latest_id: number;
};

async function parseJsonResponse(res: Response): Promise<Record<string, unknown>> {
  const text = await res.text();
  if (!text) return {};
  try {
    return JSON.parse(text) as Record<string, unknown>;
  } catch {
    // Safari/WebKit: res.json() on HTML 500 → "The string did not match the expected pattern"
    throw new Error(`inbox_bad_json_${res.status}`);
  }
}

export async function fetchDmInbox(
  tab: string = "all",
  signal?: AbortSignal
): Promise<{
  tab: string;
  tab_counts: Record<string, number>;
  message_request_count: number;
  conversations: InboxItem[];
}> {
  const res = await fetch(`/api/v1/dm/inbox/?tab=${encodeURIComponent(tab)}`, {
    credentials: "same-origin",
    headers: { Accept: "application/json" },
    signal,
  });
  const data = await parseJsonResponse(res);
  if (!res.ok || !data.ok) {
    throw new Error(
      typeof data.error === "string" ? data.error : `inbox_failed_${res.status}`
    );
  }
  return {
    tab: String(data.tab || tab),
    tab_counts: (data.tab_counts || {}) as Record<string, number>,
    message_request_count: Number(data.message_request_count || 0),
    conversations: Array.isArray(data.conversations)
      ? (data.conversations as InboxItem[])
      : [],
  };
}

export async function startDm(userId: number): Promise<number> {
  const res = await fetch("/api/v1/dm/start/", {
    method: "POST",
    credentials: "same-origin",
    headers: {
      "X-CSRFToken": getCsrfToken(),
      Accept: "application/json",
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ user_id: userId }),
  });
  const data = await res.json();
  if (!res.ok || !data.ok) throw new Error(data.error || "start_failed");
  return data.room_id as number;
}

export async function fetchDmRoom(roomPk: number, signal?: AbortSignal) {
  const res = await fetch(`/api/v1/dm/rooms/${roomPk}/`, {
    credentials: "same-origin",
    headers: { Accept: "application/json" },
    signal,
  });
  const data = await res.json();
  if (!res.ok || !data.ok) throw new Error(data.error || "room_failed");
  return data as { room: DmRoomDetail; messages: ChatMessage[] };
}

export async function pollDmMessages(
  roomPk: number,
  after: number,
  signal?: AbortSignal
) {
  const qs = after ? `?after=${after}` : "";
  const res = await fetch(`/api/v1/dm/rooms/${roomPk}/messages/${qs}`, {
    credentials: "same-origin",
    headers: { Accept: "application/json" },
    signal,
  });
  if (!res.ok) throw new Error(`poll_${res.status}`);
  return res.json() as Promise<{
    messages: ChatMessage[];
    latest_id: number;
    can_send: boolean;
    is_blocked: boolean;
    read_message_ids?: number[];
  }>;
}

export async function sendDmMessage(
  roomPk: number,
  body: string
): Promise<ChatMessage> {
  const res = await fetch(`/api/v1/dm/rooms/${roomPk}/messages/send/`, {
    method: "POST",
    credentials: "same-origin",
    headers: {
      "X-CSRFToken": getCsrfToken(),
      Accept: "application/json",
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ body }),
  });
  const data = await res.json();
  if (!res.ok || !data.ok) throw new Error(data.error || "send_failed");
  return data.message as ChatMessage;
}

export async function fetchGroupFollowees(query?: string): Promise<Author[]> {
  const qs = query?.trim()
    ? `?q=${encodeURIComponent(query.trim())}`
    : "";
  const res = await fetch(`/api/v1/dm/groups/${qs}`, {
    credentials: "same-origin",
    headers: { Accept: "application/json" },
  });
  const data = await res.json();
  if (!res.ok || !data.ok) throw new Error(data.error || "following_failed");
  return (data.candidates || data.following || []) as Author[];
}

export async function createGroup(
  name: string,
  memberIds: number[]
): Promise<number> {
  const res = await fetch("/api/v1/dm/groups/", {
    method: "POST",
    credentials: "same-origin",
    headers: {
      "X-CSRFToken": getCsrfToken(),
      Accept: "application/json",
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ name, member_ids: memberIds }),
  });
  const data = await res.json();
  if (!res.ok || !data.ok) throw new Error(data.error || "create_failed");
  return data.room_id as number;
}

export async function fetchGroupRoom(roomPk: number, signal?: AbortSignal) {
  const res = await fetch(`/api/v1/dm/groups/${roomPk}/`, {
    credentials: "same-origin",
    headers: { Accept: "application/json" },
    signal,
  });
  const data = await res.json();
  if (!res.ok || !data.ok) throw new Error(data.error || "group_failed");
  const room = data.room as GroupRoomDetail;
  return {
    room: {
      ...room,
      membership_status: room.membership_status || "member",
      invitation: room.invitation || null,
      pending_invites: Array.isArray(room.pending_invites)
        ? room.pending_invites
        : [],
    },
    messages: (data.messages || []) as ChatMessage[],
  };
}

export async function pollGroupMessages(
  roomPk: number,
  after: number,
  signal?: AbortSignal
) {
  const qs = after ? `?after=${after}` : "";
  const res = await fetch(`/api/v1/dm/groups/${roomPk}/messages/${qs}`, {
    credentials: "same-origin",
    headers: { Accept: "application/json" },
    signal,
  });
  if (!res.ok) throw new Error(`poll_${res.status}`);
  return res.json() as Promise<{
    messages: ChatMessage[];
    latest_id: number;
    can_send?: boolean;
  }>;
}

export async function sendGroupMessage(
  roomPk: number,
  body: string,
  replyToId?: number | null
): Promise<ChatMessage> {
  const res = await fetch(`/api/v1/dm/groups/${roomPk}/messages/send/`, {
    method: "POST",
    credentials: "same-origin",
    headers: {
      "X-CSRFToken": getCsrfToken(),
      Accept: "application/json",
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      body,
      ...(replyToId ? { reply_to_id: replyToId } : {}),
    }),
  });
  const data = await res.json();
  if (!res.ok || !data.ok) throw new Error(data.error || "send_failed");
  return data.message as ChatMessage;
}

export async function deleteGroupMessage(
  roomPk: number,
  messagePk: number
): Promise<ChatMessage> {
  const res = await fetch(
    `/api/v1/dm/groups/${roomPk}/messages/${messagePk}/delete/`,
    {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "X-CSRFToken": getCsrfToken(),
        Accept: "application/json",
        "Content-Type": "application/json",
      },
      body: "{}",
    }
  );
  const data = await res.json();
  if (!res.ok || !data.ok) throw new Error(data.error || "delete_failed");
  return data.message as ChatMessage;
}

export async function inviteToGroup(
  roomPk: number,
  memberIds: number[]
): Promise<number> {
  const res = await fetch(`/api/v1/dm/groups/${roomPk}/invite/`, {
    method: "POST",
    credentials: "same-origin",
    headers: {
      "X-CSRFToken": getCsrfToken(),
      Accept: "application/json",
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ member_ids: memberIds }),
  });
  const data = await res.json();
  if (!res.ok || !data.ok) throw new Error(data.error || "invite_failed");
  return Number(data.invited_count || 0);
}

export async function acceptGroupInvitation(roomPk: number) {
  const res = await fetch(
    `/api/v1/dm/groups/${roomPk}/invitations/accept/`,
    {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "X-CSRFToken": getCsrfToken(),
        Accept: "application/json",
        "Content-Type": "application/json",
      },
      body: "{}",
    }
  );
  const data = await res.json();
  if (!res.ok || !data.ok) throw new Error(data.error || "accept_failed");
  return data as { room: GroupRoomDetail; messages: ChatMessage[] };
}

export async function declineGroupInvitation(roomPk: number) {
  const res = await fetch(
    `/api/v1/dm/groups/${roomPk}/invitations/decline/`,
    {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "X-CSRFToken": getCsrfToken(),
        Accept: "application/json",
        "Content-Type": "application/json",
      },
      body: "{}",
    }
  );
  const data = await res.json();
  if (!res.ok || !data.ok) throw new Error(data.error || "decline_failed");
  return data as { ok: boolean; spa_path?: string };
}

export async function fetchMessageRequests(signal?: AbortSignal) {
  const res = await fetch("/api/v1/dm/message-requests/", {
    credentials: "same-origin",
    headers: { Accept: "application/json" },
    signal,
  });
  const data = await res.json();
  if (!res.ok || !data.ok) throw new Error(data.error || "requests_failed");
  return {
    count: Number(data.count || 0),
    requests: (data.requests || []) as MessageRequestItem[],
  };
}

export async function acceptMessageRequest(roomPk: number) {
  const res = await fetch(`/api/v1/dm/rooms/${roomPk}/requests/accept/`, {
    method: "POST",
    credentials: "same-origin",
    headers: {
      "X-CSRFToken": getCsrfToken(),
      Accept: "application/json",
      "Content-Type": "application/json",
    },
    body: "{}",
  });
  const data = await res.json();
  if (!res.ok || !data.ok) throw new Error(data.error || "accept_failed");
  return data as { room: DmRoomDetail; messages: ChatMessage[] };
}

export async function declineMessageRequest(roomPk: number) {
  const res = await fetch(`/api/v1/dm/rooms/${roomPk}/requests/decline/`, {
    method: "POST",
    credentials: "same-origin",
    headers: {
      "X-CSRFToken": getCsrfToken(),
      Accept: "application/json",
      "Content-Type": "application/json",
    },
    body: "{}",
  });
  const data = await res.json();
  if (!res.ok || !data.ok) throw new Error(data.error || "decline_failed");
  return data as { ok: boolean; spa_path?: string };
}
