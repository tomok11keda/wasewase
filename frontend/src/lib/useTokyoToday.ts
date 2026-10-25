import { useEffect, useState } from "react";
import {
  tokyoDateKey,
  tokyoTimetableDayIndex,
  tokyoYearMonth,
} from "./tokyoTime";

export type TokyoToday = {
  dateKey: string;
  timetableDayIndex: number | null;
  year: number;
  month: number;
};

function readTokyoToday(now: Date = new Date()): TokyoToday {
  const { year, month } = tokyoYearMonth(now);
  return {
    dateKey: tokyoDateKey(now),
    timetableDayIndex: tokyoTimetableDayIndex(now),
    year,
    month,
  };
}

function sameTokyoToday(a: TokyoToday, b: TokyoToday): boolean {
  return (
    a.dateKey === b.dateKey &&
    a.timetableDayIndex === b.timetableDayIndex &&
    a.year === b.year &&
    a.month === b.month
  );
}

/** Recomputes the Tokyo calendar day on focus, resume, and midnight. */
export function useTokyoToday(): TokyoToday {
  const [today, setToday] = useState(readTokyoToday);

  useEffect(() => {
    const refresh = () => {
      const next = readTokyoToday();
      setToday((prev) => (sameTokyoToday(prev, next) ? prev : next));
    };
    const onVisibility = () => {
      if (!document.hidden) refresh();
    };
    document.addEventListener("visibilitychange", onVisibility);
    window.addEventListener("focus", refresh);
    window.addEventListener("pageshow", refresh);
    const timer = window.setInterval(refresh, 60_000);
    return () => {
      document.removeEventListener("visibilitychange", onVisibility);
      window.removeEventListener("focus", refresh);
      window.removeEventListener("pageshow", refresh);
      window.clearInterval(timer);
    };
  }, []);

  return today;
}
