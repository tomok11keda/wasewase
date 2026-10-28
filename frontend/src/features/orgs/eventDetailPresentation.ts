import { isoToTokyoInput } from "./tokyoDateTime.ts";
import type { OrganizationEvent } from "./orgEvents.ts";

const WEEKDAYS = ["日", "月", "火", "水", "木", "金", "土"] as const;

export type EventPublicationStatus = "draft" | "published" | "cancelled";

export type EventDetailAdminAction =
  | "publish"
  | "unpublish"
  | "registration_toggle"
  | "edit"
  | "registrations"
  | "run_lottery"
  | "lottery_results"
  | "manage"
  | "duplicate"
  | "timeline_share"
  | "chat_share"
  | "cancel"
  | "delete";

export type TokyoEventSchedule = {
  sameDay: boolean;
  startDateLine: string;
  startTime: string;
  endDateLine: string;
  endTime: string;
  timeRange: string;
};

export type EventDetailAdminLayout = {
  visible: EventDetailAdminAction[];
  primary: EventDetailAdminAction | null;
  secondary: EventDetailAdminAction[];
  manage: EventDetailAdminAction[];
  more: EventDetailAdminAction[];
  danger: EventDetailAdminAction[];
  shareChat: boolean;
};

type TokyoWallParts = {
  year: number;
  month: number;
  day: number;
  hour: number;
  minute: number;
};

function tokyoWallParts(iso: string): TokyoWallParts | null {
  const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})$/.exec(
    isoToTokyoInput(iso)
  );
  if (!match) return null;
  return {
    year: Number(match[1]),
    month: Number(match[2]),
    day: Number(match[3]),
    hour: Number(match[4]),
    minute: Number(match[5]),
  };
}

function weekdayJa(year: number, month: number, day: number): string {
  return WEEKDAYS[new Date(Date.UTC(year, month - 1, day)).getUTCDay()];
}

function dateLine(parts: TokyoWallParts): string {
  return `${parts.year}年${parts.month}月${parts.day}日（${weekdayJa(
    parts.year,
    parts.month,
    parts.day
  )}）`;
}

function timeLine(parts: TokyoWallParts): string {
  return `${String(parts.hour).padStart(2, "0")}:${String(parts.minute).padStart(2, "0")}`;
}

export function formatTokyoEventSchedule(
  startsAt: string,
  endsAt: string
): TokyoEventSchedule {
  const start = tokyoWallParts(startsAt);
  const end = tokyoWallParts(endsAt);
  if (!start || !end) {
    return {
      sameDay: false,
      startDateLine: "",
      startTime: "",
      endDateLine: "",
      endTime: "",
      timeRange: "",
    };
  }
  return {
    sameDay:
      start.year === end.year &&
      start.month === end.month &&
      start.day === end.day,
    startDateLine: dateLine(start),
    startTime: timeLine(start),
    endDateLine: dateLine(end),
    endTime: timeLine(end),
    timeRange: `${timeLine(start)}〜${timeLine(end)}`,
  };
}

export function eventPublicationStatusLabel(
  status: EventPublicationStatus | string
): string {
  if (status === "draft") return "下書き";
  if (status === "cancelled") return "中止";
  return "公開";
}

export function eventSignupModeLabel(
  signupMode: OrganizationEvent["signup_mode"] | string
): string {
  return signupMode === "announcement" ? "告知のみ" : "申込あり";
}

export function eventVenueText(event: Pick<OrganizationEvent, "venue_name" | "venue_address">): string {
  const name = event.venue_name.trim();
  const address = event.venue_address.trim();
  if (name && address) return `${name}（${address}）`;
  return name || address;
}

export function visibleEventDetailAdminActions(
  event: OrganizationEvent
): EventDetailAdminAction[] {
  const actions: EventDetailAdminAction[] = [];
  if (event.status === "draft") actions.push("publish");
  if (event.status === "published") actions.push("unpublish");
  if (
    event.signup_mode === "registration" &&
    event.status !== "cancelled" &&
    (event.registration_open || event.can_reopen_registration)
  ) {
    actions.push("registration_toggle");
  }
  actions.push("edit");
  if (event.signup_mode === "registration") actions.push("registrations");
  if (event.can_run_lottery) actions.push("run_lottery");
  if (event.has_lottery) actions.push("lottery_results");
  actions.push("manage");
  actions.push("duplicate");
  if (event.can_share_to_timeline) actions.push("timeline_share");
  if (event.status === "published") actions.push("chat_share");
  if (event.status !== "cancelled") {
    actions.push("cancel");
    actions.push("delete");
  }
  return actions;
}

export function eventDetailAdminLayout(
  event: OrganizationEvent
): EventDetailAdminLayout {
  const visible = visibleEventDetailAdminActions(event);
  const has = (action: EventDetailAdminAction) => visible.includes(action);
  const primary =
    event.status === "draft" && has("publish")
      ? "publish"
      : event.status === "published" && has("timeline_share")
        ? "timeline_share"
        : null;
  const secondary: EventDetailAdminAction[] = [];
  if (has("edit")) secondary.push("edit");
  if (event.status === "draft" && has("duplicate")) secondary.push("duplicate");
  const manage: EventDetailAdminAction[] = [];
  if (has("registrations")) manage.push("registrations");
  if (has("run_lottery")) manage.push("run_lottery");
  if (has("lottery_results")) manage.push("lottery_results");
  const more: EventDetailAdminAction[] = [];
  if (has("unpublish")) more.push("unpublish");
  if (has("registration_toggle")) more.push("registration_toggle");
  if (event.status !== "draft" && has("duplicate")) more.push("duplicate");
  if (has("manage")) more.push("manage");
  const danger: EventDetailAdminAction[] = [];
  if (has("cancel")) danger.push("cancel");
  if (has("delete")) danger.push("delete");
  return {
    visible,
    primary,
    secondary,
    manage,
    more,
    danger,
    shareChat: has("chat_share"),
  };
}

export function eventDetailAdminActionLabel(
  action: EventDetailAdminAction,
  event: OrganizationEvent
): string {
  switch (action) {
    case "publish":
      return "イベントを公開する";
    case "unpublish":
      return "非公開にする";
    case "registration_toggle":
      return event.registration_open ? "申込を停止" : "申込を再開";
    case "edit":
      return "編集する";
    case "registrations":
      return "申込者管理";
    case "run_lottery":
      return "抽選する";
    case "lottery_results":
      return "抽選結果";
    case "manage":
      return "イベント管理";
    case "duplicate":
      return "複製";
    case "timeline_share":
      return "タイムラインにシェア";
    case "chat_share":
      return "団体チャットに共有";
    case "cancel":
      return "イベントを中止";
    case "delete":
      return "イベントを削除";
  }
}
