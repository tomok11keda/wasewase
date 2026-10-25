const TOKYO_TIME_ZONE = "Asia/Tokyo";

export const EVENT_TITLE_MAX = 120;
export const EVENT_DESCRIPTION_MAX = 5000;
export const EVENT_VENUE_NAME_MAX = 120;
export const EVENT_VENUE_ADDRESS_MAX = 200;
export const EXCLUSION_NOTE_MAX = 100;

export type OrganizationEventStatus = "draft" | "published" | "cancelled";
export type OrganizationEventRegistrationStatus = "registered" | "cancelled";
export type OrganizationEventLotteryResult =
  | "selected"
  | "not_selected"
  | "excluded";

export type OrganizationEvent = {
  id: number;
  organization_id: number;
  organization_slug: string;
  organization_name: string;
  organization_avatar_url: string;
  title: string;
  description: string;
  starts_at: string;
  ends_at: string;
  venue_name: string;
  venue_address: string;
  registration_deadline: string | null;
  status: OrganizationEventStatus;
  registration_open: boolean;
  registered_count: number;
  is_ended: boolean;
  is_deadline_passed: boolean;
  viewer_status: OrganizationEventRegistrationStatus | null;
  viewer_registered: boolean;
  can_register: boolean;
  can_cancel_registration: boolean;
  can_manage: boolean;
  has_lottery: boolean;
  lottery_executed_at: string | null;
  lottery_applicant_count: number | null;
  lottery_eligible_count: number | null;
  lottery_winner_count: number | null;
  lottery_not_selected_count: number | null;
  lottery_excluded_count: number | null;
  lottery_shared: boolean;
  viewer_lottery_result: OrganizationEventLotteryResult | null;
  can_run_lottery: boolean;
  can_view_lottery: boolean;
  can_share_lottery: boolean;
  can_reopen_registration: boolean;
  created_at: string;
  updated_at: string;
};

export type OrganizationEventLotteryUser = {
  id: number | null;
  username: string;
  display_name: string;
  avatar_url: string;
  initial: string;
};

export type OrganizationEventLotteryEntry = {
  id: number;
  result: OrganizationEventLotteryResult;
  user: OrganizationEventLotteryUser;
  exclusion_note?: string;
};

export type OrganizationEventLottery = {
  id: number;
  event_id: number;
  status: string;
  executed_at: string;
  applicant_count: number;
  eligible_count: number;
  excluded_count: number;
  winner_count: number;
  not_selected_count: number;
  shared: boolean;
  shared_at: string | null;
  can_share: boolean;
  can_manage: boolean;
  can_view: boolean;
  lists_visible: boolean;
  viewer_entry: OrganizationEventLotteryEntry | null;
  selected: OrganizationEventLotteryEntry[];
  not_selected: OrganizationEventLotteryEntry[];
  excluded: OrganizationEventLotteryEntry[];
};

export type OrganizationEventLotteryShareContent = {
  event_id: number;
  organization_slug: string;
  title: string;
  applicant_count: number;
  eligible_count: number;
  winner_count: number;
  not_selected_count: number;
  excluded_count: number;
  path: string;
};

export type OrganizationEventLotteryShareCard = {
  type: "org_event_lottery";
  id: number;
  available: boolean;
  content?: OrganizationEventLotteryShareContent;
};

export type OrganizationEventListPayload = {
  ok: true;
  events: OrganizationEvent[];
  has_more: boolean;
  next_offset: number;
  can_manage: boolean;
};

export type OrganizationEventRegistrant = {
  id: number;
  status: OrganizationEventRegistrationStatus;
  created_at: string;
  user: {
    id: number;
    username: string;
    display_name: string;
    avatar_url: string;
    initial: string;
  };
};

export type OrganizationEventForm = {
  title: string;
  description: string;
  starts_at: string;
  ends_at: string;
  venue_name: string;
  venue_address: string;
  registration_deadline: string;
  registration_open: boolean;
};

const STATUSES = new Set<string>(["draft", "published", "cancelled"]);

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

export function organizationEventPath(slug: string, eventId: number): string {
  return `/organizations/${slug}/events/${eventId}`;
}

export function organizationEventManagePath(slug: string): string {
  return `/organizations/${slug}/events/manage`;
}

export function organizationEventNewPath(slug: string): string {
  return `/organizations/${slug}/events/new`;
}

export function organizationEventEditPath(slug: string, eventId: number): string {
  return `/organizations/${slug}/events/${eventId}/edit`;
}

export function organizationEventRegistrationsPath(
  slug: string,
  eventId: number
): string {
  return `/organizations/${slug}/events/${eventId}/registrations`;
}

export function organizationEventLotteryPath(
  slug: string,
  eventId: number
): string {
  return `/organizations/${slug}/events/${eventId}/lottery`;
}

export function formatTokyoDateTime(value: string): string {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("ja-JP", {
    timeZone: TOKYO_TIME_ZONE,
    year: "numeric",
    month: "numeric",
    day: "numeric",
    weekday: "short",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

export function isoToTokyoInput(iso: string): string {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: TOKYO_TIME_ZONE,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    hourCycle: "h23",
  }).formatToParts(date);
  const get = (type: string) => parts.find((part) => part.type === type)?.value || "";
  const hour = get("hour") === "24" ? "00" : get("hour");
  return `${get("year")}-${get("month")}-${get("day")}T${hour}:${get("minute")}`;
}

export function tokyoInputToIso(local: string): string {
  const raw = local.trim();
  if (!raw) return "";
  const date = new Date(`${raw}:00+09:00`);
  if (Number.isNaN(date.getTime())) return "";
  return date.toISOString();
}

export function parseOrganizationEvent(raw: unknown): OrganizationEvent | null {
  const data = asRecord(raw);
  if (!data) return null;
  const id = asNumber(data.id);
  const organizationId = asNumber(data.organization_id);
  const slug = asString(data.organization_slug).trim();
  const title = asString(data.title).trim();
  const starts = asString(data.starts_at);
  const ends = asString(data.ends_at);
  const status = asString(data.status);
  if (
    id == null ||
    id <= 0 ||
    organizationId == null ||
    !slug ||
    !title ||
    !starts ||
    !ends ||
    !STATUSES.has(status)
  ) {
    return null;
  }
  const viewerStatus = asString(data.viewer_status);
  return {
    id,
    organization_id: organizationId,
    organization_slug: slug,
    organization_name: asString(data.organization_name),
    organization_avatar_url: asString(data.organization_avatar_url),
    title,
    description: asString(data.description),
    starts_at: starts,
    ends_at: ends,
    venue_name: asString(data.venue_name),
    venue_address: asString(data.venue_address),
    registration_deadline: asString(data.registration_deadline) || null,
    status: status as OrganizationEventStatus,
    registration_open: asBool(data.registration_open),
    registered_count: asNumber(data.registered_count) || 0,
    is_ended: asBool(data.is_ended),
    is_deadline_passed: asBool(data.is_deadline_passed),
    viewer_status:
      viewerStatus === "registered" || viewerStatus === "cancelled"
        ? viewerStatus
        : null,
    viewer_registered: asBool(data.viewer_registered),
    can_register: asBool(data.can_register),
    can_cancel_registration: asBool(data.can_cancel_registration),
    can_manage: asBool(data.can_manage),
    has_lottery: asBool(data.has_lottery),
    lottery_executed_at: asString(data.lottery_executed_at) || null,
    lottery_applicant_count: asNumber(data.lottery_applicant_count),
    lottery_eligible_count: asNumber(data.lottery_eligible_count),
    lottery_winner_count: asNumber(data.lottery_winner_count),
    lottery_not_selected_count: asNumber(data.lottery_not_selected_count),
    lottery_excluded_count: asNumber(data.lottery_excluded_count),
    lottery_shared: asBool(data.lottery_shared),
    viewer_lottery_result: parseLotteryResult(data.viewer_lottery_result),
    can_run_lottery: asBool(data.can_run_lottery),
    can_view_lottery: asBool(data.can_view_lottery),
    can_share_lottery: asBool(data.can_share_lottery),
    can_reopen_registration: asBool(data.can_reopen_registration),
    created_at: asString(data.created_at),
    updated_at: asString(data.updated_at),
  };
}

function parseLotteryResult(value: unknown): OrganizationEventLotteryResult | null {
  const raw = asString(value);
  if (raw === "selected" || raw === "not_selected" || raw === "excluded") {
    return raw;
  }
  return null;
}

function parseLotteryUser(raw: unknown): OrganizationEventLotteryUser | null {
  const data = asRecord(raw);
  if (!data) return null;
  if ("email" in data) return null;
  const id = asNumber(data.id);
  return {
    id: id != null && id > 0 ? id : null,
    username: asString(data.username),
    display_name: asString(data.display_name) || "ユーザー",
    avatar_url: asString(data.avatar_url),
    initial: asString(data.initial) || "?",
  };
}

function parseLotteryEntry(raw: unknown): OrganizationEventLotteryEntry | null {
  const data = asRecord(raw);
  if (!data) return null;
  const id = asNumber(data.id);
  const result = parseLotteryResult(data.result);
  const user = parseLotteryUser(data.user);
  if (id == null || !result || !user) return null;
  return {
    id,
    result,
    user,
    exclusion_note:
      result === "excluded" ? asString(data.exclusion_note) : undefined,
  };
}

function parseLotteryEntries(raw: unknown): OrganizationEventLotteryEntry[] | null {
  if (!Array.isArray(raw)) return null;
  const entries: OrganizationEventLotteryEntry[] = [];
  for (const row of raw) {
    const parsed = parseLotteryEntry(row);
    if (!parsed) return null;
    entries.push(parsed);
  }
  return entries;
}

export function parseOrganizationEventLottery(
  raw: unknown
): OrganizationEventLottery | null {
  const data = asRecord(raw);
  if (!data) return null;
  const id = asNumber(data.id);
  const eventId = asNumber(data.event_id);
  const executedAt = asString(data.executed_at);
  if (id == null || id <= 0 || eventId == null || !executedAt) return null;
  const listsVisible = asBool(data.lists_visible) || asBool(data.can_view);
  let selected: OrganizationEventLotteryEntry[] = [];
  let notSelected: OrganizationEventLotteryEntry[] = [];
  let excluded: OrganizationEventLotteryEntry[] = [];
  if (listsVisible) {
    const parsedSelected = parseLotteryEntries(data.selected);
    const parsedNotSelected = parseLotteryEntries(data.not_selected);
    const parsedExcluded = parseLotteryEntries(data.excluded);
    if (
      parsedSelected == null ||
      parsedNotSelected == null ||
      parsedExcluded == null
    ) {
      return null;
    }
    selected = parsedSelected;
    notSelected = parsedNotSelected;
    excluded = parsedExcluded;
  }
  const viewerEntry = data.viewer_entry
    ? parseLotteryEntry(data.viewer_entry)
    : null;
  if (data.viewer_entry && !viewerEntry) return null;
  return {
    id,
    event_id: eventId,
    status: asString(data.status) || "completed",
    executed_at: executedAt,
    applicant_count: asNumber(data.applicant_count) || 0,
    eligible_count: asNumber(data.eligible_count) || 0,
    excluded_count: asNumber(data.excluded_count) || 0,
    winner_count: asNumber(data.winner_count) || 0,
    not_selected_count: asNumber(data.not_selected_count) || 0,
    shared: asBool(data.shared),
    shared_at: asString(data.shared_at) || null,
    can_share: asBool(data.can_share),
    can_manage: asBool(data.can_manage),
    can_view: asBool(data.can_view),
    lists_visible: listsVisible,
    viewer_entry: viewerEntry,
    selected,
    not_selected: notSelected,
    excluded,
  };
}

export function parseOrganizationEventLotteryShareCard(
  raw: unknown
): OrganizationEventLotteryShareCard | null {
  const data = asRecord(raw);
  if (!data || asString(data.type) !== "org_event_lottery") return null;
  const id = asNumber(data.id);
  if (id == null || id <= 0) return null;
  const contentRaw = asRecord(data.content);
  const content = contentRaw
    ? {
        event_id: asNumber(contentRaw.event_id) || 0,
        organization_slug: asString(contentRaw.organization_slug),
        title: asString(contentRaw.title),
        applicant_count: asNumber(contentRaw.applicant_count) || 0,
        eligible_count: asNumber(contentRaw.eligible_count) || 0,
        winner_count: asNumber(contentRaw.winner_count) || 0,
        not_selected_count: asNumber(contentRaw.not_selected_count) || 0,
        excluded_count: asNumber(contentRaw.excluded_count) || 0,
        path: asString(contentRaw.path),
      }
    : undefined;
  return {
    type: "org_event_lottery",
    id,
    available: data.available !== false,
    content,
  };
}

export function parseOrganizationEventListPayload(
  raw: unknown
): OrganizationEventListPayload | null {
  const data = asRecord(raw);
  if (!data || data.ok !== true || !Array.isArray(data.events)) return null;
  const events: OrganizationEvent[] = [];
  for (const row of data.events) {
    const parsed = parseOrganizationEvent(row);
    if (!parsed) return null;
    events.push(parsed);
  }
  return {
    ok: true,
    events,
    has_more: asBool(data.has_more),
    next_offset: asNumber(data.next_offset) || 0,
    can_manage: asBool(data.can_manage),
  };
}

export function parseOrganizationEventRegistrant(
  raw: unknown
): OrganizationEventRegistrant | null {
  const data = asRecord(raw);
  if (!data) return null;
  const user = asRecord(data.user);
  const id = asNumber(data.id);
  const userId = user ? asNumber(user.id) : null;
  if (id == null || userId == null) return null;
  if ("email" in (user || {})) return null;
  return {
    id,
    status: asString(data.status) === "cancelled" ? "cancelled" : "registered",
    created_at: asString(data.created_at),
    user: {
      id: userId,
      username: asString(user?.username),
      display_name: asString(user?.display_name),
      avatar_url: asString(user?.avatar_url),
      initial: asString(user?.initial) || "?",
    },
  };
}

export function emptyEventForm(): OrganizationEventForm {
  return {
    title: "",
    description: "",
    starts_at: "",
    ends_at: "",
    venue_name: "",
    venue_address: "",
    registration_deadline: "",
    registration_open: true,
  };
}

export function formFromOrganizationEvent(
  event: OrganizationEvent | null
): OrganizationEventForm {
  if (!event) return emptyEventForm();
  return {
    title: event.title,
    description: event.description,
    starts_at: isoToTokyoInput(event.starts_at),
    ends_at: isoToTokyoInput(event.ends_at),
    venue_name: event.venue_name,
    venue_address: event.venue_address,
    registration_deadline: event.registration_deadline
      ? isoToTokyoInput(event.registration_deadline)
      : "",
    registration_open: event.registration_open,
  };
}

export function eventFormToPayload(form: OrganizationEventForm): Record<string, unknown> {
  return {
    title: form.title.trim(),
    description: form.description.trim(),
    starts_at: tokyoInputToIso(form.starts_at),
    ends_at: tokyoInputToIso(form.ends_at),
    venue_name: form.venue_name.trim(),
    venue_address: form.venue_address.trim(),
    registration_deadline: form.registration_deadline.trim()
      ? tokyoInputToIso(form.registration_deadline)
      : null,
    registration_open: form.registration_open,
  };
}

export function validateEventForm(
  form: OrganizationEventForm
): Record<string, string> {
  const errors: Record<string, string> = {};
  if (!form.title.trim()) errors.title = "イベント名を入力してください。";
  else if (form.title.trim().length > EVENT_TITLE_MAX) {
    errors.title = `${EVENT_TITLE_MAX}文字以内で入力してください。`;
  }
  if (form.description.length > EVENT_DESCRIPTION_MAX) {
    errors.description = `${EVENT_DESCRIPTION_MAX}文字以内で入力してください。`;
  }
  if (!form.venue_name.trim()) errors.venue_name = "会場を入力してください。";
  else if (form.venue_name.trim().length > EVENT_VENUE_NAME_MAX) {
    errors.venue_name = `${EVENT_VENUE_NAME_MAX}文字以内で入力してください。`;
  }
  if (form.venue_address.trim().length > EVENT_VENUE_ADDRESS_MAX) {
    errors.venue_address = `${EVENT_VENUE_ADDRESS_MAX}文字以内で入力してください。`;
  }
  const starts = tokyoInputToIso(form.starts_at);
  const ends = tokyoInputToIso(form.ends_at);
  if (!form.starts_at.trim() || !starts) {
    errors.starts_at = "開始日時を入力してください。";
  }
  if (!form.ends_at.trim() || !ends) {
    errors.ends_at = "終了日時を入力してください。";
  }
  if (starts && ends && new Date(ends).getTime() <= new Date(starts).getTime()) {
    errors.ends_at = "終了日時は開始日時より後にしてください。";
  }
  if (form.registration_deadline.trim()) {
    const deadline = tokyoInputToIso(form.registration_deadline);
    if (!deadline) {
      errors.registration_deadline = "申込締切の形式が正しくありません。";
    } else if (starts && new Date(deadline).getTime() > new Date(starts).getTime()) {
      errors.registration_deadline = "申込締切は開始日時以前にしてください。";
    }
  }
  return errors;
}

export function eventStatusLabel(event: OrganizationEvent): string {
  if (event.status === "cancelled") return "中止";
  if (event.status === "draft") return "下書き";
  if (event.is_ended) return "終了";
  if (event.viewer_lottery_result === "selected") return "当選";
  if (event.viewer_lottery_result === "not_selected") return "落選";
  if (event.viewer_lottery_result === "excluded") return "対象外";
  if (event.has_lottery) return "抽選済み";
  if (event.is_deadline_passed) return "締切";
  if (!event.registration_open) return "受付停止";
  if (event.viewer_registered) return "申込済み";
  return "募集中";
}

export function eventCapacityLabel(event: OrganizationEvent): string {
  return `申込 ${event.registered_count}人`;
}

export function lotteryResultLabel(
  result: OrganizationEventLotteryResult | null
): string {
  if (result === "selected") return "当選";
  if (result === "not_selected") return "落選";
  if (result === "excluded") return "対象外";
  return "";
}

export function viewerLotteryRegistrationLabel(
  event: OrganizationEvent
): string {
  if (event.viewer_status === "cancelled" && event.viewer_lottery_result) {
    return "参加辞退";
  }
  if (event.viewer_registered) return "申し込み済み";
  return "";
}

export function defaultLotteryEligibleIds(
  registrations: OrganizationEventRegistrant[]
): number[] {
  return registrations
    .filter((row) => row.status === "registered")
    .map((row) => row.user.id);
}

export function validateLotterySetup(input: {
  winnerCount: string;
  eligibleCount: number;
  notes: Record<number, string>;
}): Record<string, string> {
  const errors: Record<string, string> = {};
  const parsed = Number(input.winnerCount.trim());
  if (!Number.isInteger(parsed) || parsed < 0) {
    errors.winner_count = "当選人数は0以上の整数で入力してください。";
  } else if (parsed > input.eligibleCount) {
    errors.winner_count = "当選人数は抽選対象者数以下にしてください。";
  }
  for (const note of Object.values(input.notes)) {
    if (note.length > EXCLUSION_NOTE_MAX) {
      errors.exclusion_note = `備考は${EXCLUSION_NOTE_MAX}文字以内で入力してください。`;
      break;
    }
  }
  return errors;
}

export function canShowEventManage(input: {
  hydrated: boolean;
  canManage: boolean;
}): boolean {
  return input.hydrated && input.canManage;
}

export function eventPageView(args: {
  loading: boolean;
  error: string | null;
  event: OrganizationEvent | null;
}): "loading" | "missing" | "error" | "ready" {
  if (args.loading && !args.event) return "loading";
  if (args.event) return "ready";
  if (args.error === "not_found" || args.error === "forbidden") return "missing";
  if (args.error) return "error";
  return "missing";
}

export function organizationEventErrorMessage(
  code: string | undefined,
  fallback: string
): string {
  switch (code) {
    case "unauthorized":
      return "ログインが必要です。";
    case "forbidden":
      return "この操作はできません。";
    case "not_found":
      return "イベントが見つからないか、表示できません。";
    case "no_lottery":
      return "抽選結果はまだありません。";
    case "already_drawn":
      return "このイベントの抽選はすでに確定しています。";
    case "already_shared":
      return "抽選結果はすでに団体チャットへ共有されています。";
    case "winner_count_exceeds_eligible":
      return "当選人数は抽選対象者数以下にしてください。";
    case "invalid_excluded":
      return "除外者の指定が正しくありません。";
    case "no_eligible":
      return "抽選対象者を1人以上選択してください。";
    case "not_published":
      return "公開中のイベントだけ抽選できます。";
    case "no_recruiting_chat":
      return "団体チャットがないため共有できません。";
    case "lottery_closed":
      return "抽選が確定しているため、この操作はできません。";
    case "registrants_changed":
      return "申込者が変わったため、最新の一覧を確認してから抽選してください。";
    case "cancelled":
      return "このイベントは中止されました。";
    case "ended":
      return "このイベントは終了しています。";
    case "deadline_passed":
      return "申込締切を過ぎています。";
    case "registration_closed":
      return "現在申し込みを受け付けていません。";
    case "not_registered":
      return "申し込みが見つかりません。";
    case "rate_limited":
      return "短時間に操作が集中しています。少し待ってからもう一度お試しください。";
    case "organization_suspended":
      return "この団体は現在利用できません。";
    default:
      return fallback;
  }
}
