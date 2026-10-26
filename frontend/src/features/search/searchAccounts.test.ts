import assert from "node:assert/strict";
import test from "node:test";
import {
  SEARCH_USERS_TAB_LABEL,
  isHandledSearchResultKind,
  organizationSearchHref,
} from "./searchAccounts.ts";

test("users tab stays internally users but is labeled アカウント", () => {
  assert.equal(SEARCH_USERS_TAB_LABEL, "アカウント");
});

test("organization search cards go to the org profile path", () => {
  assert.equal(organizationSearchHref("wase-circle"), "/orgs/wase-circle");
  assert.equal(organizationSearchHref(""), "");
});

test("unknown search result kinds are not treated as handled", () => {
  assert.equal(isHandledSearchResultKind("organization"), true);
  assert.equal(isHandledSearchResultKind("user"), true);
  assert.equal(isHandledSearchResultKind("product"), true);
  assert.equal(isHandledSearchResultKind("mystery"), false);
  assert.equal(isHandledSearchResultKind(""), false);
});
