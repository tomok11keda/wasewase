import { getCsrfToken } from "../timeline/api";

export type CalendarCategory =
  | "class"
  | "assignment"
  | "exam"
  | "seminar"
  | "club"
  | "other";

export type CalendarEvent = {
  id: number;
  title: string;
  date: string;
  start_time: string;
  end_time: string;
  memo: string;
  category: CalendarCategory | string;
  category_label: string;
  updated_at?: string;
};

export type CalendarDot = {
  count: number;
  titles: string[];
  extra: number;
};

export type CalendarMonthPayload = {
  ok: boolean;
  year: number;
  month: number;
  events: CalendarEvent[];
  by_date: Record<string, CalendarEvent[]>;
  dots: Record<string, CalendarDot>;
  categories: Array<{ value: string; label: string }>;
};

export type CalendarEventInput = {
  title: string;
  date: string;
  start_time?: string;
  end_time?: string;
  memo?: string;
  category?: string;
};

const DEFAULT_CATEGORIES = [
  { value: "class", label: "授業" },
  { value: "assignment", label: "課題" },
  { value: "exam", label: "テスト" },
  { value: "seminar", label: "ゼミ" },
  { value: "club", label: "サークル" },
  { value: "other", label: "その他" },
];

export function defaultCalendarCategories() {
  return DEFAULT_CATEGORIES;
}

export async function fetchCalendarMonth(
  year: number,
  month: number,
  signal?: AbortSignal
): Promise<CalendarMonthPayload> {
  const qs = new URLSearchParams({
    year: String(year),
    month: String(month),
  });
  const res = await fetch(`/api/v1/calendar/events/?${qs}`, {
    credentials: "same-origin",
    headers: { Accept: "application/json" },
    signal,
  });
  const data = await res.json();
  if (!res.ok || !data.ok) throw new Error(data.error || `calendar_${res.status}`);
  return {
    ...data,
    events: Array.isArray(data.events) ? data.events : [],
    by_date: data.by_date || {},
    dots: data.dots || {},
    categories: Array.isArray(data.categories)
      ? data.categories
      : DEFAULT_CATEGORIES,
  } as CalendarMonthPayload;
}

export async function createCalendarEvent(
  input: CalendarEventInput
): Promise<CalendarEvent> {
  const res = await fetch("/api/v1/calendar/events/create/", {
    method: "POST",
    credentials: "same-origin",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      "X-CSRFToken": getCsrfToken(),
    },
    body: JSON.stringify(input),
  });
  const data = await res.json();
  if (!res.ok || !data.ok) throw new Error(data.error || "create_failed");
  return data.event as CalendarEvent;
}

export async function updateCalendarEvent(
  id: number,
  input: CalendarEventInput
): Promise<CalendarEvent> {
  const res = await fetch(`/api/v1/calendar/events/${id}/`, {
    method: "POST",
    credentials: "same-origin",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      "X-CSRFToken": getCsrfToken(),
    },
    body: JSON.stringify(input),
  });
  const data = await res.json();
  if (!res.ok || !data.ok) throw new Error(data.error || "update_failed");
  return data.event as CalendarEvent;
}

export async function deleteCalendarEvent(id: number): Promise<void> {
  const res = await fetch(`/api/v1/calendar/events/${id}/delete/`, {
    method: "POST",
    credentials: "same-origin",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      "X-CSRFToken": getCsrfToken(),
    },
    body: "{}",
  });
  const data = await res.json();
  if (!res.ok || !data.ok) throw new Error(data.error || "delete_failed");
}

/** JS Date.getDay(): Sun=0 … Sat=6 → timetable day_index Mon=0 … Sat=5, or null for Sun. */
export function jsWeekdayToTimetableDayIndex(jsDay: number): number | null {
  if (jsDay === 0) return null;
  return jsDay - 1;
}

export function toDateKey(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

export function parseDateKey(key: string): Date {
  const [y, m, d] = key.split("-").map(Number);
  return new Date(y, (m || 1) - 1, d || 1);
}

export function formatMonthTitle(year: number, month: number): string {
  return `${year}年${month}月`;
}

const WEEKDAY_LABELS = ["日", "月", "火", "水", "木", "金", "土"] as const;

export function formatDayHeading(dateKey: string): string {
  const d = parseDateKey(dateKey);
  const w = WEEKDAY_LABELS[d.getDay()] || "";
  return `${d.getMonth() + 1}月${d.getDate()}日（${w}）`;
}
