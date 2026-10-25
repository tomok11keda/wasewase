import assert from "node:assert/strict";
import test from "node:test";
import { HOME_TIMELINE_SORT } from "./homeFeed.ts";

test("home timeline is latest-only", () => {
  assert.equal(HOME_TIMELINE_SORT, "latest");
});
