import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = dirname(fileURLToPath(import.meta.url));
const source = readFileSync(join(root, "ImageLightbox.tsx"), "utf8");
const css = readFileSync(
  join(root, "../../styles/timeline.css"),
  "utf8"
);

test("lightbox sits above the mobile site-header stacking level", () => {
  assert.match(css, /\.image-lightbox\s*\{[^}]*z-index:\s*2300/s);
  assert.match(css, /body\.image-lightbox-open\s+\.site-header/);
  assert.match(css, /pointer-events:\s*none\s*!important/);
});

test("close control keeps a 44px hit target and aria-label", () => {
  assert.match(css, /min-width:\s*44px/);
  assert.match(css, /min-height:\s*44px/);
  assert.match(source, /aria-label="閉じる"/);
  assert.match(source, /role="dialog"/);
  assert.match(source, /aria-modal="true"/);
});

test("all intended dismiss paths are wired", () => {
  assert.match(source, /requestClose/);
  assert.match(source, /Escape/);
  assert.match(source, /onPointerCancel/);
  assert.match(source, /shouldDismissSwipe/);
  assert.match(source, /suppressClickUntilRef/);
  assert.match(source, /image-lightbox-open/);
  assert.match(source, /restore\.focus/);
  // Image and backdrop both dismiss on click.
  assert.equal((source.match(/onClick=\{onDismissClick\}/g) || []).length >= 2, true);
});

test("does not reintroduce stopPropagation that blocked image tap-close", () => {
  assert.equal(source.includes("event.stopPropagation()\n        />"), false);
  assert.equal(/onClick=\{\(event\) => event\.stopPropagation\(\)\}/.test(source), false);
});
