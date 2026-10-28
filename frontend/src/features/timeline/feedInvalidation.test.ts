import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";
import {
  invalidateTimelineFeed,
  subscribeTimelineFeedInvalidation,
} from "./feedInvalidation.ts";

test("timeline feed listeners run once per invalidation", () => {
  const seen: number[] = [];
  const stop = subscribeTimelineFeedInvalidation(() => {
    seen.push(1);
  });
  invalidateTimelineFeed();
  stop();
  invalidateTimelineFeed();
  assert.deepEqual(seen, [1]);
});

test("home timeline fetch does not keep a stale HTTP cache", () => {
  const api = readFileSync(
    join(dirname(fileURLToPath(import.meta.url)), "api.ts"),
    "utf8"
  );
  assert.equal(api.includes('cache: "no-store"'), true);
});
