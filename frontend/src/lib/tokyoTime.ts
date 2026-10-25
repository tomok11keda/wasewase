export const TOKYO_TIME_ZONE = "Asia/Tokyo";

const WEEKDAY_TO_JS: Record<string, number> = {
  Sun: 0,
  Mon: 1,
  Tue: 2,
  Wed: 3,
  Thu: 4,
  Fri: 5,
  Sat: 6,
};

function tokyoParts(now: Date): Record<string, string> {
  const fmt = new Intl.DateTimeFormat("en-US", {
    timeZone: TOKYO_TIME_ZONE,
    weekday: "short",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  });
  const map: Record<string, string> = {};
  for (const part of fmt.formatToParts(now)) {
    if (part.type === "literal") continue;
    map[part.type] = part.value;
  }
  return map;
}

/** JS weekday: 0=Sun … 6=Sat in Asia/Tokyo, independent of the device zone. */
export function tokyoWeekdayJs(now: Date = new Date()): number {
  const weekday = tokyoParts(now).weekday;
  return WEEKDAY_TO_JS[weekday] ?? 0;
}

/** Timetable column index 0=Mon … 5=Sat, or null on Sunday in Tokyo. */
export function tokyoTimetableDayIndex(now: Date = new Date()): number | null {
  const jsDay = tokyoWeekdayJs(now);
  if (jsDay === 0) return null;
  return jsDay - 1;
}

export function tokyoDateKey(now: Date = new Date()): string {
  const parts = tokyoParts(now);
  return `${parts.year}-${parts.month}-${parts.day}`;
}

export function tokyoYearMonth(now: Date = new Date()): {
  year: number;
  month: number;
} {
  const key = tokyoDateKey(now);
  const [year, month] = key.split("-").map(Number);
  return { year, month };
}
