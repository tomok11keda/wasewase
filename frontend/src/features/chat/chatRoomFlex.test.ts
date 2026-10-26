import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

const css = readFileSync(
  join(dirname(fileURLToPath(import.meta.url)), "../../styles/dm.css"),
  "utf8"
);

function conversationMobileBlock(source: string): string {
  const media = source.split("@media (max-width: 1023px)")[1] || "";
  const end = media.indexOf("@media");
  return end === -1 ? media : media.slice(0, end);
}

test("mobile conversation frame can shrink below layout-viewport 100%", () => {
  const block = conversationMobileBlock(css);
  assert.equal(block.includes("html.chrome-conversation .dm-room-page"), true);
  const pageRule = block.split("html.chrome-conversation .dm-room-page")[1] || "";
  assert.equal(pageRule.includes("min-height: 0"), true);
  assert.equal(pageRule.includes("height: var(--chat-visible-h, 100dvh)"), true);
});

test("mobile conversation inner column uses flex-basis 0 instead of height 100%", () => {
  const block = conversationMobileBlock(css);
  assert.equal(block.includes("flex: 1 1 0%"), true);
  assert.equal(
    block.includes("html.chrome-conversation .dm-room-page .dm-room-main"),
    true
  );
  const inner = block.split(
    "html.chrome-conversation .dm-room-page .dm-room-main"
  )[1];
  assert.equal(inner.includes("height: auto"), true);
  assert.equal(inner.includes("min-height: 0"), true);
  assert.equal(
    inner.includes("html.chrome-conversation .dm-room-page .chat-panel"),
    true
  );
  assert.equal(inner.includes(".dm-thread"), true);
  assert.equal(inner.includes(".dm-message-area"), true);
});

test("compose bar stays a non-shrinking flex sibling of the thread", () => {
  const compose = css.split(".chat-compose-bar {")[1]?.split("}")[0] || "";
  assert.equal(compose.includes("flex: 0 0 auto"), true);
  assert.equal(compose.includes("flex-shrink: 0"), true);
  assert.equal(compose.includes("position: relative"), true);
  assert.equal(compose.includes("position: fixed"), false);
});
