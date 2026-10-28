const TOKYO_OFFSET = "+09:00";

const DATE_RE = /^(\d{4}-\d{2}-\d{2})$/;
const TIME_RE = /^(\d{2}):(\d{2})(?::(\d{2}))?$/;
const COMBINED_RE =
  /^(\d{4}-\d{2}-\d{2})(?:T(\d{2}):(\d{2})(?::(\d{2}))?)?$/;

export type TokyoDateTimeParts = {
  date: string;
  time: string;
};

export function isoToTokyoInput(iso: string): string {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Tokyo",
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
  const { date, time } = splitTokyoDateTime(raw);
  if (!date || !time) return "";
  const parsed = new Date(`${date}T${time}:00${TOKYO_OFFSET}`);
  if (Number.isNaN(parsed.getTime())) return "";
  return parsed.toISOString();
}

export function normalizeTokyoTime(raw: string): string {
  const match = raw.trim().match(TIME_RE);
  if (!match) return "";
  return `${match[1]}:${match[2]}`;
}

export function splitTokyoDateTime(value: string): TokyoDateTimeParts {
  const raw = value.trim();
  if (!raw) return { date: "", time: "" };
  const combined = raw.match(COMBINED_RE);
  if (combined) {
    return {
      date: combined[1],
      time: combined[2] && combined[3] ? `${combined[2]}:${combined[3]}` : "",
    };
  }
  if (DATE_RE.test(raw)) return { date: raw, time: "" };
  return { date: "", time: "" };
}

export function joinTokyoDateTime(date: string, time: string): string {
  const nextDate = date.trim();
  const nextTime = normalizeTokyoTime(time);
  if (nextDate && nextTime) return `${nextDate}T${nextTime}`;
  if (nextDate) return nextDate;
  return "";
}

export function isCompleteTokyoDateTime(value: string): boolean {
  const { date, time } = splitTokyoDateTime(value);
  return Boolean(date && time && tokyoInputToIso(`${date}T${time}`));
}

export function tokyoTimeInputStep(time: string): number {
  const normalized = normalizeTokyoTime(time);
  if (!normalized) return 300;
  const minute = Number(normalized.slice(3, 5));
  return Number.isInteger(minute) && minute % 5 === 0 ? 300 : 60;
}

export function addTokyoHours(local: string, hours: number): string {
  const iso = tokyoInputToIso(local);
  if (!iso) return "";
  const date = new Date(iso);
  date.setTime(date.getTime() + hours * 60 * 60 * 1000);
  return isoToTokyoInput(date.toISOString());
}

/** Fill an empty end time with start+2h. Never overwrite a filled or user-edited value. */
export function suggestedEndFromStart(args: {
  start: string;
  end: string;
  endTouched: boolean;
}): string {
  if (args.endTouched || args.end.trim()) return args.end;
  if (!isCompleteTokyoDateTime(args.start)) return args.end;
  return addTokyoHours(args.start, 2) || args.end;
}

export type TokyoDateTimeWheels = {
  year: number;
  month: number;
  day: number;
  hour: number;
  minute: number;
};

export function pad2(value: number): string {
  return String(value).padStart(2, "0");
}

export function daysInMonth(year: number, month: number): number {
  if (!Number.isInteger(year) || !Number.isInteger(month) || month < 1 || month > 12) {
    return 0;
  }
  return new Date(Date.UTC(year, month, 0)).getUTCDate();
}

export function clampDay(year: number, month: number, day: number): number {
  const max = daysInMonth(year, month);
  if (!max) return 1;
  if (!Number.isInteger(day) || day < 1) return 1;
  return Math.min(day, max);
}

export function formatTokyoDateTimeLabel(value: string): string {
  const { date, time } = splitTokyoDateTime(value);
  if (!date || !time) return "";
  const [year, month, day] = date.split("-").map(Number);
  if (!year || !month || !day) return "";
  return `${year}年${month}月${day}日 ${time}`;
}

export function wheelsToTokyoInput(wheels: TokyoDateTimeWheels): string {
  const day = clampDay(wheels.year, wheels.month, wheels.day);
  return joinTokyoDateTime(
    `${wheels.year}-${pad2(wheels.month)}-${pad2(day)}`,
    `${pad2(wheels.hour)}:${pad2(wheels.minute)}`
  );
}

export function tokyoDateTimeToWheels(
  value: string,
  now: Date = new Date()
): TokyoDateTimeWheels {
  const source = isCompleteTokyoDateTime(value)
    ? value
    : isoToTokyoInput(now.toISOString());
  const { date, time } = splitTokyoDateTime(source);
  const [year, month, day] = date.split("-").map(Number);
  const [hour, minute] = time.split(":").map(Number);
  return {
    year: year || 2026,
    month: month || 1,
    day: clampDay(year || 2026, month || 1, day || 1),
    hour: Number.isInteger(hour) ? hour : 0,
    minute: Number.isInteger(minute) ? minute : 0,
  };
}

export function tokyoYearOptions(
  selectedYear: number,
  now: Date = new Date()
): number[] {
  const current = tokyoDateTimeToWheels("", now).year;
  const min = Math.min(selectedYear, current - 1);
  const max = Math.max(selectedYear, current + 3);
  const years: number[] = [];
  for (let year = min; year <= max; year += 1) years.push(year);
  return years;
}

export function tokyoDateTimeOrderError(
  start: string,
  end: string,
  options: { endRequired: boolean }
): string | undefined {
  const startIso = isCompleteTokyoDateTime(start) ? tokyoInputToIso(start) : "";
  const endComplete = isCompleteTokyoDateTime(end);
  const endIso = endComplete ? tokyoInputToIso(end) : "";
  if (!startIso) return undefined;
  if (options.endRequired && !end.trim()) return undefined;
  if (!end.trim()) return undefined;
  if (!endComplete || !endIso) return "終了の日付と時刻を入力してください。";
  if (new Date(endIso).getTime() <= new Date(startIso).getTime()) {
    return "終了日時は開始日時より後にしてください。";
  }
  return undefined;
}
