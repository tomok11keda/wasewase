import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

const source = readFileSync(
  join(dirname(fileURLToPath(import.meta.url)), "TokyoDateTimeFields.tsx"),
  "utf8"
);

test("shared event datetime component uses a Japanese wheel picker", () => {
  assert.equal(source.includes('type="date"'), false);
  assert.equal(source.includes('type="time"'), false);
  assert.equal(source.includes("datetime-local"), false);
  assert.equal(source.includes('unit="年"'), true);
  assert.equal(source.includes('unit="月"'), true);
  assert.equal(source.includes('unit="日"'), true);
  assert.equal(source.includes('unit="時"'), true);
  assert.equal(source.includes('unit="分"'), true);
  assert.equal(source.includes("決定"), true);
  assert.equal(source.includes("キャンセル"), true);
  assert.equal(source.includes("createPortal"), true);
});
