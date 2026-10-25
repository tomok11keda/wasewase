import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

test("group invite copy does not claim unread history is visible", () => {
  const src = readFileSync(
    join(dirname(fileURLToPath(import.meta.url)), "GroupRoomPage.tsx"),
    "utf8"
  );
  assert.equal(src.includes("内容は確認できます"), false);
  assert.equal(
    src.includes("グループに招待されています。参加するとメッセージを確認できます。"),
    true
  );
});
