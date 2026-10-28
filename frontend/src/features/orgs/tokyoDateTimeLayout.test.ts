import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

const css = readFileSync(
  join(dirname(fileURLToPath(import.meta.url)), "../../styles/org.css"),
  "utf8"
);

test("datetime picker keeps five Japanese wheel columns on a narrow sheet", () => {
  assert.equal(css.includes(".tokyo-datetime__trigger"), true);
  assert.equal(css.includes(".tokyo-wheel"), true);
  assert.equal(css.includes("overscroll-behavior: contain"), true);
  assert.match(
    css,
    /\.tokyo-wheel\s*\{[^}]*grid-template-columns: minmax\(0, 1\.3fr\) repeat\(4, minmax\(0, 1fr\)\)/
  );
  assert.equal(css.includes('input[type="date"]'), false);
  assert.equal(css.includes('input[type="time"]'), false);
});

test("selected wheel values stay above the highlight band", () => {
  const highlight = css.split(".tokyo-wheel-col__highlight")[1] || "";
  const scroller = css.split(".tokyo-wheel-col__scroller")[1] || "";
  const selected = css.split(".tokyo-wheel-col__item.is-selected")[1] || "";
  assert.equal(highlight.includes("z-index: 0"), true);
  assert.equal(scroller.includes("z-index: 1"), true);
  assert.equal(scroller.includes("background: transparent"), true);
  assert.equal(selected.includes("-webkit-text-fill-color: #0f1419"), true);
  assert.equal(css.includes("mask-image:"), false);
});
