import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

const css = readFileSync(
  join(dirname(fileURLToPath(import.meta.url)), "../../styles/org.css"),
  "utf8"
);

test("event form text inputs no longer stretch radios to 100% width", () => {
  assert.equal(
    css.includes(
      '.org-edit-page .form-group input:not([type="checkbox"]):not([type="radio"])'
    ),
    true
  );
  assert.equal(
    css.includes(".org-edit-page .form-group input,\n.org-edit-page .form-group select"),
    false
  );
});

test("signup mode uses stacked choice cards that keep radio controls compact", () => {
  assert.equal(css.includes(".org-event-signup-mode__options"), true);
  assert.equal(css.includes(".org-event-choice"), true);
  assert.equal(css.includes(".org-event-choice__text"), true);
  assert.equal(
    css.includes('.org-event-form .org-event-choice input[type="radio"]'),
    true
  );
  assert.match(
    css,
    /\.org-event-form \.org-event-choice input\[type="radio"\][\s\S]*?flex: 0 0 20px/
  );
  assert.match(
    css,
    /\.org-event-choice__text strong\s*\{[^}]*overflow-wrap: break-word/
  );
  assert.doesNotMatch(
    css,
    /\.org-event-choice__text[\s\S]{0,400}overflow-wrap: anywhere/
  );
});
