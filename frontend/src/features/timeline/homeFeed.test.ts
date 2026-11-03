import assert from "node:assert/strict";
import test from "node:test";
import {
  HOME_TIMELINE_SORT,
  isHomeTimelinePath,
  parseHomeTimelineSort,
  stripHomeTimelineLeftoverParams,
} from "./homeFeed.ts";

test("home timeline defaults to latest", () => {
  assert.equal(HOME_TIMELINE_SORT, "latest");
  assert.equal(parseHomeTimelineSort(null), "latest");
  assert.equal(parseHomeTimelineSort(""), "latest");
  assert.equal(parseHomeTimelineSort("latest"), "latest");
  assert.equal(parseHomeTimelineSort("recommended"), "recommended");
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

test("home leftover strip keeps sort so recommended can be selected", () => {
  const params = new URLSearchParams(
    "sort=recommended&faculty=政治経済学部&q=x"
  );
  const next = stripHomeTimelineLeftoverParams("/", params);
  assert.ok(next);
  assert.equal(next.get("sort"), "recommended");
  assert.equal(next.get("faculty"), null);
  assert.equal(next.get("q"), null);
});
