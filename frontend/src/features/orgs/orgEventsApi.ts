import { apiGetJson, apiPatchJson, apiPostJson, mutationErrorMessage } from "../../lib/http";
import { OrganizationRequestError } from "./api";
import {
  organizationEventErrorMessage,
  parseOrganizationEvent,
  parseOrganizationEventListPayload,
  parseOrganizationEventLottery,
  parseOrganizationEventRegistrant,
  type OrganizationEvent,
  type OrganizationEventForm,
  type OrganizationEventListPayload,
  type OrganizationEventLottery,
  type OrganizationEventRegistrant,
  eventFormToPayload,
} from "./orgEvents";

function eventUrl(slug: string, suffix = ""): string {
  return `/api/v1/organizations/${encodeURIComponent(slug)}/events/${suffix}`;
}

function throwEventError(
  status: number,
  error: string | undefined,
  data: Record<string, unknown>,
  fallback: string
): never {
  const code = error || `http_${status}`;
  const fieldErrors =
    data.errors && typeof data.errors === "object" && !Array.isArray(data.errors)
      ? Object.fromEntries(
          Object.entries(data.errors as Record<string, unknown>).map(([key, value]) => [
            key,
            typeof value === "string" ? value : "",
          ])
        )
      : {};
  throw new OrganizationRequestError(
    code,
    status,
    organizationEventErrorMessage(code, mutationErrorMessage(code, fallback)),
    fieldErrors,
    data
  );
}

function eventFromResult(
  status: number,
  error: string | undefined,
  data: Record<string, unknown>,
  fallback: string
): OrganizationEvent {
  if (status === 401 || error === "unauthorized") {
    throwEventError(status, "unauthorized", data, fallback);
  }
  if (!data.ok || error) {
    throwEventError(status, error, data, fallback);
  }
  const event = parseOrganizationEvent(data.event);
  if (!event) {
    throwEventError(status, "invalid_payload", data, fallback);
  }
  return event;
}

export async function fetchOrganizationEvents(
  slug: string,
  options: { manage?: boolean; offset?: number } = {}
): Promise<OrganizationEventListPayload> {
  const params = new URLSearchParams();
  if (options.manage) params.set("manage", "1");
  if (options.offset) params.set("offset", String(options.offset));
  const qs = params.toString();
  const result = await apiGetJson(`${eventUrl(slug)}${qs ? `?${qs}` : ""}`);
  if (!result.data.ok || result.error) {
    throwEventError(
      result.status,
      result.error,
      result.data,
      "イベントを読み込めませんでした。"
    );
  }
  const payload = parseOrganizationEventListPayload(result.data);
  if (!payload) {
    throwEventError(
      result.status,
      "invalid_payload",
      result.data,
      "イベントを読み込めませんでした。"
    );
  }
  return payload;
}

export async function fetchOrganizationEvent(
  slug: string,
  eventId: number
): Promise<OrganizationEvent> {
  const result = await apiGetJson(eventUrl(slug, `${eventId}/`));
  return eventFromResult(
    result.status,
    result.error,
    result.data,
    "イベントを読み込めませんでした。"
  );
}

export async function createOrganizationEvent(
  slug: string,
  form: OrganizationEventForm
): Promise<OrganizationEvent> {
  const result = await apiPostJson(eventUrl(slug), eventFormToPayload(form));
  return eventFromResult(
    result.status,
    result.error,
    result.data,
    "イベントを作成できませんでした。"
  );
}

export async function updateOrganizationEvent(
  slug: string,
  eventId: number,
  form: OrganizationEventForm
): Promise<OrganizationEvent> {
  const result = await apiPatchJson(
    eventUrl(slug, `${eventId}/`),
    eventFormToPayload(form)
  );
  return eventFromResult(
    result.status,
    result.error,
    result.data,
    "イベントを保存できませんでした。"
  );
}

export async function publishOrganizationEvent(
  slug: string,
  eventId: number
): Promise<OrganizationEvent> {
  const result = await apiPostJson(eventUrl(slug, `${eventId}/publish/`));
  return eventFromResult(result.status, result.error, result.data, "公開できませんでした。");
}

export async function unpublishOrganizationEvent(
  slug: string,
  eventId: number
): Promise<OrganizationEvent> {
  const result = await apiPostJson(eventUrl(slug, `${eventId}/unpublish/`));
  return eventFromResult(
    result.status,
    result.error,
    result.data,
    "非公開にできませんでした。"
  );
}

export async function cancelOrganizationEvent(
  slug: string,
  eventId: number
): Promise<OrganizationEvent> {
  const result = await apiPostJson(eventUrl(slug, `${eventId}/cancel/`));
  return eventFromResult(result.status, result.error, result.data, "中止できませんでした。");
}

export async function deleteOrganizationEvent(
  slug: string,
  eventId: number
): Promise<void> {
  const result = await apiPostJson(eventUrl(slug, `${eventId}/delete/`));
  if (result.status === 401 || result.error === "unauthorized") {
    throwEventError(result.status, "unauthorized", result.data, "削除できませんでした。");
  }
  if (!result.data.ok || result.error) {
    throwEventError(result.status, result.error, result.data, "削除できませんでした。");
  }
}

export async function registerOrganizationEvent(
  slug: string,
  eventId: number
): Promise<OrganizationEvent> {
  const result = await apiPostJson(eventUrl(slug, `${eventId}/register/`));
  return eventFromResult(
    result.status,
    result.error,
    result.data,
    "申し込みできませんでした。"
  );
}

export async function unregisterOrganizationEvent(
  slug: string,
  eventId: number
): Promise<OrganizationEvent> {
  const result = await apiPostJson(eventUrl(slug, `${eventId}/unregister/`));
  return eventFromResult(
    result.status,
    result.error,
    result.data,
    "申し込みを取り消せませんでした。"
  );
}

export async function fetchOrganizationEventRegistrations(
  slug: string,
  eventId: number,
  offset = 0
): Promise<{
  event: OrganizationEvent;
  registrations: OrganizationEventRegistrant[];
  has_more: boolean;
  next_offset: number;
  total: number;
}> {
  const qs = offset ? `?offset=${offset}` : "";
  const result = await apiGetJson(eventUrl(slug, `${eventId}/registrations/${qs}`));
  if (!result.data.ok || result.error) {
    throwEventError(
      result.status,
      result.error,
      result.data,
      "申込者を読み込めませんでした。"
    );
  }
  const event = parseOrganizationEvent(result.data.event);
  if (!event || !Array.isArray(result.data.registrations)) {
    throwEventError(
      result.status,
      "invalid_payload",
      result.data,
      "申込者を読み込めませんでした。"
    );
  }
  const registrations: OrganizationEventRegistrant[] = [];
  for (const row of result.data.registrations) {
    const parsed = parseOrganizationEventRegistrant(row);
    if (!parsed) {
      throwEventError(
        result.status,
        "invalid_payload",
        result.data,
        "申込者を読み込めませんでした。"
      );
    }
    registrations.push(parsed);
  }
  return {
    event,
    registrations,
    has_more: result.data.has_more === true,
    next_offset:
      typeof result.data.next_offset === "number" ? result.data.next_offset : 0,
    total: typeof result.data.total === "number" ? result.data.total : registrations.length,
  };
}

export async function fetchAllOrganizationEventRegistrations(
  slug: string,
  eventId: number
): Promise<{
  event: OrganizationEvent;
  registrations: OrganizationEventRegistrant[];
  total: number;
}> {
  const registrations: OrganizationEventRegistrant[] = [];
  let offset = 0;
  let event: OrganizationEvent | null = null;
  let total = 0;
  for (;;) {
    const page = await fetchOrganizationEventRegistrations(slug, eventId, offset);
    event = page.event;
    total = page.total;
    registrations.push(...page.registrations);
    if (!page.has_more) break;
    offset = page.next_offset;
  }
  if (!event) {
    throwEventError(404, "not_found", {}, "申込者を読み込めませんでした。");
  }
  return { event, registrations, total };
}

export async function fetchOrganizationEventLottery(
  slug: string,
  eventId: number
): Promise<{ event: OrganizationEvent; lottery: OrganizationEventLottery }> {
  const result = await apiGetJson(eventUrl(slug, `${eventId}/lottery/`));
  if (!result.data.ok || result.error) {
    throwEventError(
      result.status,
      result.error,
      result.data,
      "抽選結果を読み込めませんでした。"
    );
  }
  const event = parseOrganizationEvent(result.data.event);
  const lottery = parseOrganizationEventLottery(result.data.lottery);
  if (!event || !lottery) {
    throwEventError(
      result.status,
      "invalid_payload",
      result.data,
      "抽選結果を読み込めませんでした。"
    );
  }
  return { event, lottery };
}

export async function runOrganizationEventLottery(
  slug: string,
  eventId: number,
  payload: {
    winner_count: number;
    excluded: { user_id: number; note: string }[];
    applicant_ids: number[];
  }
): Promise<{ event: OrganizationEvent; lottery: OrganizationEventLottery }> {
  const result = await apiPostJson(eventUrl(slug, `${eventId}/lottery/`), payload);
  if (!result.data.ok || result.error) {
    throwEventError(
      result.status,
      result.error,
      result.data,
      "抽選を実行できませんでした。"
    );
  }
  const event = parseOrganizationEvent(result.data.event);
  const lottery = parseOrganizationEventLottery(result.data.lottery);
  if (!event || !lottery) {
    throwEventError(
      result.status,
      "invalid_payload",
      result.data,
      "抽選を実行できませんでした。"
    );
  }
  return { event, lottery };
}

export async function shareOrganizationEventLottery(
  slug: string,
  eventId: number,
  chatId?: number | null
): Promise<{ event: OrganizationEvent; lottery: OrganizationEventLottery }> {
  const result = await apiPostJson(eventUrl(slug, `${eventId}/lottery/share/`), {
    ...(chatId ? { chat_id: chatId } : {}),
  });
  if (!result.data.ok || result.error) {
    throwEventError(
      result.status,
      result.error,
      result.data,
      "抽選結果を共有できませんでした。"
    );
  }
  const event = parseOrganizationEvent(result.data.event);
  const lottery = parseOrganizationEventLottery(result.data.lottery);
  if (!event || !lottery) {
    throwEventError(
      result.status,
      "invalid_payload",
      result.data,
      "抽選結果を共有できませんでした。"
    );
  }
  return { event, lottery };
}

export async function shareOrganizationEventToChat(
  slug: string,
  eventId: number,
  chatId: number
): Promise<{ chat_id: number; message_id: number; event: OrganizationEvent }> {
  const result = await apiPostJson(eventUrl(slug, `${eventId}/share/`), {
    chat_id: chatId,
  });
  if (!result.data.ok || result.error) {
    throwEventError(
      result.status,
      result.error,
      result.data,
      "イベントを共有できませんでした。"
    );
  }
  const event = parseOrganizationEvent(result.data.event);
  if (!event) {
    throwEventError(
      result.status,
      "invalid_payload",
      result.data,
      "イベントを共有できませんでした。"
    );
  }
  return {
    chat_id: Number(result.data.chat_id || chatId),
    message_id: Number(result.data.message_id || 0),
    event,
  };
}

export async function duplicateOrganizationEvent(
  slug: string,
  eventId: number
): Promise<OrganizationEvent> {
  const result = await apiPostJson(eventUrl(slug, `${eventId}/duplicate/`), {});
  return eventFromResult(
    result.status,
    result.error,
    result.data,
    "イベントを複製できませんでした。"
  );
}

export async function patchEventRegistrationOpen(
  slug: string,
  eventId: number,
  registrationOpen: boolean
): Promise<OrganizationEvent> {
  const result = await apiPatchJson(eventUrl(slug, `${eventId}/`), {
    registration_open: registrationOpen,
  });
  return eventFromResult(
    result.status,
    result.error,
    result.data,
    "受付状態を変更できませんでした。"
  );
}
