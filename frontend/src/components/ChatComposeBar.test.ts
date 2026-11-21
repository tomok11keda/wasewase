import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = dirname(fileURLToPath(import.meta.url));
const source = readFileSync(join(root, "ChatComposeBar.tsx"), "utf8");
const css = readFileSync(join(root, "../styles/dm.css"), "utf8");

test("send button prevents pointer default so iOS keeps compose focus", () => {
  assert.match(source, /shouldPreventSendPointerDefault/);
  assert.match(source, /onPointerDown=\{onSendPointerDown\}/);
  assert.match(source, /event\.preventDefault\(\)/);
  assert.match(source, /chatComposeSendGesture/);
});

test("send path guards against double submit and refocuses after send", () => {
  assert.match(source, /sendGuardRef/);
  assert.match(source, /shouldRefocusComposeAfterSend/);
  assert.match(source, /inputRef\.current\?\.focus/);
});

test("compose icon buttons use touch-action manipulation", () => {
  assert.match(
    css,
    /\.chat-compose-bar__icon-btn\s*\{[^}]*touch-action:\s*manipulation/s
  );
});
