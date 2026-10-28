import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

const css = readFileSync(
  join(dirname(fileURLToPath(import.meta.url)), "../../styles/org.css"),
  "utf8"
);

test("date and time fields share the event form width rules", () => {
  assert.equal(css.includes('.org-event-form input[type="date"]'), true);
  assert.equal(css.includes('.org-event-form input[type="time"]'), true);
  assert.equal(css.includes(".tokyo-datetime__fields"), true);
  assert.match(
    css,
    /\.tokyo-datetime__fields\s*\{[^}]*grid-template-columns: minmax\(0, 1\.25fr\) minmax\(0, 1fr\)/
  );
});
