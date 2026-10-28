export const CHAT_EVENT_TITLE_MAX = 120;
export const CHAT_EVENT_DESCRIPTION_MAX = 2000;
export const CHAT_EVENT_VENUE_MAX = 120;

export type ChatEventStatus = "scheduled" | "cancelled";
export type ChatEventAnswer = "going" | "not_going" | "maybe";

export type ChatEventUser = {
  id: number | null;
  username: string;
  display_name: string;
  avatar_url: string;
  initial: string;
};

export type ChatEventRespondent = {
  user: ChatEventUser;
  answer: ChatEventAnswer | null;
};

export type OrganizationChatEvent = {
  id: number;
  organization_id: number;
  organization_slug: string;
  chat_id: number;
  title: string;
  description: string;
  starts_at: string;
  ends_at: string | null;
  venue_name: string;
  rsvp_deadline: string | null;
  status: ChatEventStatus;
  is_cancelled: boolean;
  is_ended: boolean;
  is_deadline_passed: boolean;
  viewer_answer: ChatEventAnswer | null;
  can_rsvp: boolean;
  can_manage: boolean;
  chat_is_active: boolean;
  path: string;
  going_count: number;
  not_going_count: number;
  maybe_count: number;
  unanswered_count: number;
  member_count: number;
  respondents?: {
    going: ChatEventRespondent[];
    not_going: ChatEventRespondent[];
    maybe: ChatEventRespondent[];
    unanswered: ChatEventRespondent[];
  };
};

export type OrganizationChatEventForm = {
  title: string;
  description: string;
  starts_at: string;
  ends_at: string;
  venue_name: string;
  rsvp_deadline: string;
};

export type OrganizationChatEventShareCard = {
  type: "org_chat_event";
  id: number;
  available: boolean;
  content?: {
    event_id: number;
    organization_slug: string;
    chat_id: number;
    title: string;
    starts_at: string;
    ends_at: string;
    venue_name: string;
    status: string;
    status_label: string;
    path: string;
  };
};

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function asString(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function asNumber(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function asBool(value: unknown): boolean {
  return value === true;
}

function parseAnswer(value: unknown): ChatEventAnswer | null {
  const raw = asString(value);
  if (raw === "going" || raw === "not_going" || raw === "maybe") return raw;
  return null;
}

function parseUser(raw: unknown): ChatEventUser | null {
  const data = asRecord(raw);
  if (!data || "email" in data) return null;
  const id = asNumber(data.id);
  return {
    id: id != null && id > 0 ? id : null,
    username: asString(data.username),
    display_name: asString(data.display_name) || "ユーザー",
    avatar_url: asString(data.avatar_url),
    initial: asString(data.initial) || "?",
  };
}

function parseRespondents(raw: unknown): ChatEventRespondent[] {
  if (!Array.isArray(raw)) return [];
  const rows: ChatEventRespondent[] = [];
  for (const item of raw) {
    const data = asRecord(item);
    const user = data ? parseUser(data.user) : null;
    if (!user) continue;
    rows.push({ user, answer: parseAnswer(data?.answer) });
  }
  return rows;
}

export function parseOrganizationChatEvent(
  raw: unknown
): OrganizationChatEvent | null {
  const data = asRecord(raw);
  if (!data) return null;
  const id = asNumber(data.id);
  const chatId = asNumber(data.chat_id);
  const title = asString(data.title).trim();
  const starts = asString(data.starts_at);
  if (id == null || id <= 0 || chatId == null || !title || !starts) return null;
  const respondentsRaw = asRecord(data.respondents);
  return {
    id,
    organization_id: asNumber(data.organization_id) || 0,
    organization_slug: asString(data.organization_slug),
    chat_id: chatId,
    title,
    description: asString(data.description),
    starts_at: starts,
    ends_at: asString(data.ends_at) || null,
    venue_name: asString(data.venue_name),
    rsvp_deadline: asString(data.rsvp_deadline) || null,
    status: asString(data.status) === "cancelled" ? "cancelled" : "scheduled",
    is_cancelled: asBool(data.is_cancelled) || asString(data.status) === "cancelled",
    is_ended: asBool(data.is_ended),
    is_deadline_passed: asBool(data.is_deadline_passed),
    viewer_answer: parseAnswer(data.viewer_answer),
    can_rsvp: asBool(data.can_rsvp),
    can_manage: asBool(data.can_manage),
    chat_is_active: data.chat_is_active !== false,
    path: asString(data.path),
    going_count: asNumber(data.going_count) || 0,
    not_going_count: asNumber(data.not_going_count) || 0,
    maybe_count: asNumber(data.maybe_count) || 0,
    unanswered_count: asNumber(data.unanswered_count) || 0,
    member_count: asNumber(data.member_count) || 0,
    respondents: respondentsRaw
      ? {
          going: parseRespondents(respondentsRaw.going),
          not_going: parseRespondents(respondentsRaw.not_going),
          maybe: parseRespondents(respondentsRaw.maybe),
          unanswered: parseRespondents(respondentsRaw.unanswered),
        }
      : undefined,
  };
}

export function parseOrganizationChatEventShareCard(
  raw: unknown
): OrganizationChatEventShareCard | null {
  const data = asRecord(raw);
  if (!data || asString(data.type) !== "org_chat_event") return null;
  const id = asNumber(data.id);
  if (id == null || id <= 0) return null;
  const contentRaw = asRecord(data.content);
  const content = contentRaw
    ? {
        event_id: asNumber(contentRaw.event_id) || 0,
        organization_slug: asString(contentRaw.organization_slug),
        chat_id: asNumber(contentRaw.chat_id) || 0,
        title: asString(contentRaw.title),
        starts_at: asString(contentRaw.starts_at),
        ends_at: asString(contentRaw.ends_at),
        venue_name: asString(contentRaw.venue_name),
        status: asString(contentRaw.status),
        status_label: asString(contentRaw.status_label) || "チャット内",
        path: asString(contentRaw.path),
      }
    : undefined;
  return {
    type: "org_chat_event",
    id,
    available: data.available !== false,
    content,
  };
}

export function emptyChatEventForm(): OrganizationChatEventForm {
  return {
    title: "",
    description: "",
    starts_at: "",
    ends_at: "",
    venue_name: "",
    rsvp_deadline: "",
  };
}

export function recruitingChatEventsPath(
  slug: string,
  chatId?: number | null
): string {
  const base = `/organizations/${slug}/recruiting-chat/events`;
  return chatId ? `${base}?chat=${chatId}` : base;
}

export function recruitingChatEventNewPath(
  slug: string,
  chatId?: number | null
): string {
  const base = `/organizations/${slug}/recruiting-chat/events/new`;
  return chatId ? `${base}?chat=${chatId}` : base;
}

export function recruitingChatEventPath(
  slug: string,
  eventId: number,
  chatId?: number | null
): string {
  const base = `/organizations/${slug}/recruiting-chat/events/${eventId}`;
  return chatId ? `${base}?chat=${chatId}` : base;
}

export function recruitingChatEventEditPath(
  slug: string,
  eventId: number,
  chatId?: number | null
): string {
  const base = `/organizations/${slug}/recruiting-chat/events/${eventId}/edit`;
  return chatId ? `${base}?chat=${chatId}` : base;
}

export function chatEventBackPath(slug: string, chatId?: number | null): string {
  const base = `/organizations/${slug}/recruiting-chat`;
  return chatId ? `${base}?chat=${chatId}` : base;
}

/** Invalid or unauthorized chat-event URLs must not guess another chat. */
export function chatEventSafeFallbackPath(slug: string): string {
  return `/orgs/${slug}`;
}

export function chatEventAnswerLabel(answer: ChatEventAnswer | null): string {
  if (answer === "going") return "参加";
  if (answer === "not_going") return "不参加";
  if (answer === "maybe") return "未定";
  return "未回答";
}

export function chatEventStatusLabel(event: OrganizationChatEvent): string {
  if (event.is_cancelled) return "中止";
  if (event.is_ended) return "終了";
  if (event.is_deadline_passed) return "回答締切";
  return "チャット内";
}
