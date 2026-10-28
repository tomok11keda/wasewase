import { apiGetJson, apiPatchJson, apiPostJson, mutationErrorMessage } from "../../lib/http";
import { OrganizationRequestError } from "./api";
import { organizationEventErrorMessage } from "./orgEvents";
import {
  parseOrganizationChatEvent,
  type OrganizationChatEvent,
  type OrganizationChatEventForm,
  type ChatEventAnswer,
} from "./orgChatEvents";
import { tokyoInputToIso } from "./orgEvents";

function chatEventUrl(slug: string, suffix = "", chatId?: number | null): string {
  const base = `/api/v1/organizations/${encodeURIComponent(slug)}/recruiting-chat/events/${suffix}`;
  return chatId ? `${base}${base.includes("?") ? "&" : "?"}chat=${chatId}` : base;
}

function throwChatEventError(
  status: number,
  error: string | undefined,
  data: Record<string, unknown>,
  fallback: string
): never {
  throw new OrganizationRequestError(
    error || `http_${status}`,
    status,
    organizationEventErrorMessage(
      error,
      mutationErrorMessage(error || "", fallback)
    ),
    {},
    data
  );
}

function eventFromResult(
  status: number,
  error: string | undefined,
  data: Record<string, unknown>,
  fallback: string
): OrganizationChatEvent {
  if (status === 401 || error === "unauthorized") {
    throwChatEventError(status, "unauthorized", data, fallback);
  }
  if (!data.ok || error) {
    throwChatEventError(status, error, data, fallback);
  }
  const event = parseOrganizationChatEvent(data.event);
  if (!event) {
    throwChatEventError(status, "invalid_payload", data, fallback);
  }
  return event;
}

export async function fetchOrganizationChatEvents(
  slug: string,
  chatId: number
): Promise<{
  events: OrganizationChatEvent[];
  can_manage: boolean;
  chat_is_active: boolean;
}> {
  const result = await apiGetJson(chatEventUrl(slug, "", chatId));
  if (!result.data.ok || result.error) {
    throwChatEventError(
      result.status,
      result.error,
      result.data,
      "チャット内イベントを読み込めませんでした。"
    );
  }
  const events: OrganizationChatEvent[] = [];
  const rows = Array.isArray(result.data.events) ? result.data.events : [];
  for (const row of rows) {
    const parsed = parseOrganizationChatEvent(row);
    if (parsed) events.push(parsed);
  }
  return {
    events,
    can_manage: result.data.can_manage === true,
    chat_is_active: result.data.chat_is_active !== false,
  };
}

export async function fetchOrganizationChatEvent(
  slug: string,
  eventId: number,
  chatId: number
): Promise<OrganizationChatEvent> {
  const result = await apiGetJson(chatEventUrl(slug, `${eventId}/`, chatId));
  return eventFromResult(
    result.status,
    result.error,
    result.data,
    "イベントを読み込めませんでした。"
  );
}

function formPayload(form: OrganizationChatEventForm): Record<string, unknown> {
  return {
    title: form.title.trim(),
    description: form.description.trim(),
    starts_at: tokyoInputToIso(form.starts_at),
    ends_at: form.ends_at.trim() ? tokyoInputToIso(form.ends_at) : null,
    venue_name: form.venue_name.trim(),
    rsvp_deadline: form.rsvp_deadline.trim()
      ? tokyoInputToIso(form.rsvp_deadline)
      : null,
  };
}

export async function createOrganizationChatEvent(
  slug: string,
  chatId: number,
  form: OrganizationChatEventForm
): Promise<OrganizationChatEvent> {
  const result = await apiPostJson(chatEventUrl(slug, "", chatId), formPayload(form));
  return eventFromResult(
    result.status,
    result.error,
    result.data,
    "イベントを作成できませんでした。"
  );
}

export async function updateOrganizationChatEvent(
  slug: string,
  eventId: number,
  chatId: number,
  form: OrganizationChatEventForm
): Promise<OrganizationChatEvent> {
  const result = await apiPatchJson(
    chatEventUrl(slug, `${eventId}/`, chatId),
    formPayload(form)
  );
  return eventFromResult(
    result.status,
    result.error,
    result.data,
    "イベントを更新できませんでした。"
  );
}

export async function rsvpOrganizationChatEvent(
  slug: string,
  eventId: number,
  chatId: number,
  answer: ChatEventAnswer
): Promise<OrganizationChatEvent> {
  const result = await apiPostJson(chatEventUrl(slug, `${eventId}/rsvp/`, chatId), {
    answer,
  });
  return eventFromResult(
    result.status,
    result.error,
    result.data,
    "出欠を保存できませんでした。"
  );
}

export async function cancelOrganizationChatEvent(
  slug: string,
  eventId: number,
  chatId: number
): Promise<OrganizationChatEvent> {
  const result = await apiPostJson(
    chatEventUrl(slug, `${eventId}/cancel/`, chatId),
    {}
  );
  return eventFromResult(
    result.status,
    result.error,
    result.data,
    "イベントを中止できませんでした。"
  );
}
