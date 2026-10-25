import assert from "node:assert/strict";
import test from "node:test";
import {
  tokyoDateKey,
  tokyoTimetableDayIndex,
  tokyoWeekdayJs,
  tokyoYearMonth,
} from "./tokyoTime.ts";

test("Tokyo Monday is timetable column 0 even when the device is still Sunday", () => {
  // 2026-10-25 15:30 UTC = 2026-10-26 00:30 JST (Monday).
  const justAfterTokyoMidnight = new Date("2026-10-25T15:30:00.000Z");
  assert.equal(tokyoDateKey(justAfterTokyoMidnight), "2026-10-26");
  assert.equal(tokyoWeekdayJs(justAfterTokyoMidnight), 1);
  assert.equal(tokyoTimetableDayIndex(justAfterTokyoMidnight), 0);
  assert.deepEqual(tokyoYearMonth(justAfterTokyoMidnight), {
    year: 2026,
    month: 10,
  });
});

test("Tokyo Sunday has no timetable column to highlight", () => {
  // 2026-10-25 12:00 UTC = 2026-10-25 21:00 JST (Sunday).
  const tokyoSunday = new Date("2026-10-25T12:00:00.000Z");
  assert.equal(tokyoDateKey(tokyoSunday), "2026-10-25");
  assert.equal(tokyoWeekdayJs(tokyoSunday), 0);
  assert.equal(tokyoTimetableDayIndex(tokyoSunday), null);
});

test("Tokyo Saturday highlights the last timetable column", () => {
  // 2026-10-24 12:00 UTC = 2026-10-24 21:00 JST (Saturday).
  const tokyoSaturday = new Date("2026-10-24T12:00:00.000Z");
  assert.equal(tokyoDateKey(tokyoSaturday), "2026-10-24");
  assert.equal(tokyoWeekdayJs(tokyoSaturday), 6);
  assert.equal(tokyoTimetableDayIndex(tokyoSaturday), 5);
});
