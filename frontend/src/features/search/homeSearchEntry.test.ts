import assert from "node:assert/strict";
import test from "node:test";
import {
  HOME_POST_SEARCH_HREF,
  HOME_POST_SEARCH_PLACEHOLDER,
} from "./homeSearchEntry.ts";

test("home search bar uses the existing latest post-search tab", () => {
  const url = new URL(HOME_POST_SEARCH_HREF, "https://wasewase.local");
  assert.equal(url.pathname, "/search");
  assert.equal(url.searchParams.get("tab"), "latest");
  assert.equal(url.searchParams.has("q"), false);
});

test("home search placeholder describes posts and topics without inviting in-place typing", () => {
  assert.equal(HOME_POST_SEARCH_PLACEHOLDER, "投稿や話題を検索");
});
