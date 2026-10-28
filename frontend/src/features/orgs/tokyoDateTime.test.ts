import assert from "node:assert/strict";
import test from "node:test";
import {
  addTokyoHours,
  clampDay,
  daysInMonth,
  formatTokyoDateTimeLabel,
  isoToTokyoInput,
  joinTokyoDateTime,
  splitTokyoDateTime,
  suggestedEndFromStart,
  tokyoDateTimeOrderError,
  tokyoDateTimeToWheels,
  tokyoInputToIso,
  tokyoTimeInputStep,
  wheelsToTokyoInput,
} from "./tokyoDateTime.ts";

test("ISO values round-trip as Tokyo wall time, not the browser offset", () => {
  const iso = tokyoInputToIso("2026-04-10T18:00");
  assert.equal(iso, "2026-04-10T09:00:00.000Z");
  assert.equal(isoToTokyoInput(iso), "2026-04-10T18:00");
  assert.equal(isoToTokyoInput("2026-11-01T09:00:00.000Z"), "2026-11-01T18:00");
  assert.equal(tokyoInputToIso("2026-03-08T18:00"), "2026-03-08T09:00:00.000Z");
});

test("US DST days still store the same Tokyo instant", () => {
  // America/New_York DST starts 2026-03-08. Tokyo has no DST.
  assert.equal(tokyoInputToIso("2026-03-07T18:00"), "2026-03-07T09:00:00.000Z");
  assert.equal(tokyoInputToIso("2026-03-08T18:00"), "2026-03-08T09:00:00.000Z");
  assert.equal(isoToTokyoInput("2026-03-08T09:00:00.000Z"), "2026-03-08T18:00");
  // DST ends 2026-11-01 in the US.
  assert.equal(tokyoInputToIso("2026-11-01T18:00"), "2026-11-01T09:00:00.000Z");
  assert.equal(isoToTokyoInput("2026-11-01T09:00:00.000Z"), "2026-11-01T18:00");
});

test("date and time split without converting existing values", () => {
  assert.deepEqual(splitTokyoDateTime("2026-04-10T18:07"), {
    date: "2026-04-10",
    time: "18:07",
  });
  assert.equal(joinTokyoDateTime("2026-04-10", "18:07:00"), "2026-04-10T18:07");
  assert.equal(joinTokyoDateTime("2026-04-10", ""), "2026-04-10");
  assert.equal(tokyoInputToIso("2026-04-10"), "");
  assert.equal(isoToTokyoInput("2026-04-10T09:07:00.000Z"), "2026-04-10T18:07");
});

test("odd minutes stay editable and use 1-minute steps", () => {
  assert.equal(tokyoTimeInputStep("18:00"), 300);
  assert.equal(tokyoTimeInputStep("18:05"), 300);
  assert.equal(tokyoTimeInputStep("18:07"), 60);
  assert.equal(tokyoTimeInputStep(""), 300);
  const iso = tokyoInputToIso("2026-04-10T18:07");
  assert.equal(isoToTokyoInput(iso), "2026-04-10T18:07");
});

test("empty end times are filled with start plus two Tokyo hours", () => {
  assert.equal(
    suggestedEndFromStart({
      start: "2026-04-10T18:00",
      end: "",
      endTouched: false,
    }),
    "2026-04-10T20:00"
  );
  assert.equal(
    addTokyoHours("2026-04-10T23:30", 2),
    "2026-04-11T01:30"
  );
  assert.equal(
    suggestedEndFromStart({
      start: "2026-04-10T18:00",
      end: "2026-04-10T19:00",
      endTouched: false,
    }),
    "2026-04-10T19:00"
  );
  assert.equal(
    suggestedEndFromStart({
      start: "2026-04-10T18:00",
      end: "",
      endTouched: true,
    }),
    ""
  );
});

test("labels stay Japanese and preserve odd minutes like 18:07", () => {
  assert.equal(
    formatTokyoDateTimeLabel("2026-10-28T14:30"),
    "2026年10月28日 14:30"
  );
  assert.equal(formatTokyoDateTimeLabel("2026-04-10T18:07"), "2026年4月10日 18:07");
  assert.equal(formatTokyoDateTimeLabel(""), "");
  assert.equal(
    wheelsToTokyoInput({
      year: 2026,
      month: 4,
      day: 10,
      hour: 18,
      minute: 7,
    }),
    "2026-04-10T18:07"
  );
});

test("month length and leap years clamp the day wheel", () => {
  assert.equal(daysInMonth(2024, 2), 29);
  assert.equal(daysInMonth(2025, 2), 28);
  assert.equal(daysInMonth(2026, 4), 30);
  assert.equal(daysInMonth(2026, 1), 31);
  assert.equal(clampDay(2026, 2, 31), 28);
  assert.equal(clampDay(2024, 2, 31), 29);
  assert.equal(
    wheelsToTokyoInput({
      year: 2026,
      month: 2,
      day: 31,
      hour: 10,
      minute: 0,
    }),
    "2026-02-28T10:00"
  );
});

test("empty picker drafts the current Tokyo wall clock without writing it", () => {
  const now = new Date("2026-04-10T09:07:00.000Z");
  assert.deepEqual(tokyoDateTimeToWheels("", now), {
    year: 2026,
    month: 4,
    day: 10,
    hour: 18,
    minute: 7,
  });
  assert.deepEqual(tokyoDateTimeToWheels("2026-10-28T14:30", now), {
    year: 2026,
    month: 10,
    day: 28,
    hour: 14,
    minute: 30,
  });
});

test("end must be after start when both values are complete", () => {
  assert.equal(
    tokyoDateTimeOrderError("2026-04-10T18:00", "2026-04-10T17:00", {
      endRequired: true,
    }),
    "終了日時は開始日時より後にしてください。"
  );
  assert.equal(
    tokyoDateTimeOrderError("2026-04-10T18:00", "", { endRequired: false }),
    undefined
  );
  assert.equal(
    tokyoDateTimeOrderError("2026-04-10T18:00", "2026-04-10T20:00", {
      endRequired: true,
    }),
    undefined
  );
});
