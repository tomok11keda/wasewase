import assert from "node:assert/strict";
import test from "node:test";
import {
  addTokyoHours,
  isoToTokyoInput,
  joinTokyoDateTime,
  splitTokyoDateTime,
  suggestedEndFromStart,
  tokyoDateTimeOrderError,
  tokyoInputToIso,
  tokyoTimeInputStep,
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
