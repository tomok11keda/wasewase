import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

const source = readFileSync(
  join(dirname(fileURLToPath(import.meta.url)), "TokyoDateTimeFields.tsx"),
  "utf8"
);

test("shared event datetime component uses native date and time inputs", () => {
  assert.equal(source.includes('type="date"'), true);
  assert.equal(source.includes('type="time"'), true);
  assert.equal(source.includes("datetime-local"), false);
  assert.equal(source.includes("tokyoTimeInputStep"), true);
});
