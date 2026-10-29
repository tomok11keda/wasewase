import assert from "node:assert/strict";
import test from "node:test";
import {
  HOME_TIMELINE_SORT,
  isHomeTimelinePath,
  stripHomeTimelineLeftoverParams,
} from "./homeFeed.ts";

test("home timeline is latest-only", () => {
  assert.equal(HOME_TIMELINE_SORT, "latest");
});

test("only the home timeline path is treated as home", () => {
  assert.equal(isHomeTimelinePath("/"), true);
  assert.equal(isHomeTimelinePath(""), true);
  assert.equal(isHomeTimelinePath("/search"), false);
  assert.equal(isHomeTimelinePath("/search/"), false);
  assert.equal(isHomeTimelinePath("/flea"), false);
});

test("keep-alive home does not strip q from the search tab URL", () => {
  const search = new URLSearchParams("q=わせわせ&tab=all");
  assert.equal(stripHomeTimelineLeftoverParams("/search", search), null);
  assert.equal(search.get("q"), "わせわせ");
  const home = stripHomeTimelineLeftoverParams("/", search);
  assert.ok(home);
  assert.equal(home.get("q"), null);
  assert.equal(home.get("tab"), "all");
});
