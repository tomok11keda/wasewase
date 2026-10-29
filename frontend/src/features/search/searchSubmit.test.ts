import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";
import { stripHomeTimelineLeftoverParams } from "../timeline/homeFeed.ts";
import {
  SEARCH_FAILED_MESSAGE,
  SEARCH_NO_RESULTS_MESSAGE,
  buildSearchSubmitParams,
  createSearchTabHarness,
  globalSearchEmptyMessage,
  globalSearchErrorMessage,
  searchFetchQuery,
  submitSearchForm,
} from "./searchSubmit.ts";

const root = dirname(fileURLToPath(import.meta.url));
const searchPage = readFileSync(join(root, "../../pages/SearchPage.tsx"), "utf8");

test("search button and keyboard submit share one form onSubmit path", () => {
  assert.match(searchPage, /<form className="search-form" onSubmit=\{onSearch\}/);
  assert.match(searchPage, /<button[\s\S]*type="submit"/);
  assert.match(searchPage, /type="search"/);
  assert.match(searchPage, /enterKeyHint="search"/);
  assert.equal(searchPage.includes("disabled={"), false);
  assert.match(searchPage, /buildSearchSubmitParams/);
  assert.equal(searchPage.includes("stripHomeTimelineLeftoverParams"), false);
});

test("typing then tapping 検索 sets q and requests the search API", async () => {
  const ui = createSearchTabHarness();
  ui.type("わせわせ");
  const requestId = ui.clickSearchButton();
  const pending = ui.snapshot();
  assert.equal(pending.qParam, "わせわせ");
  assert.equal(pending.loading, true);
  assert.deepEqual(pending.fetches.at(-1), {
    id: requestId,
    q: "わせわせ",
    tab: "all",
  });
  const shown = await ui.finish(requestId, {
    ok: true,
    results: ["post-1", "org-1"],
  });
  assert.equal(shown.loading, false);
  assert.deepEqual(shown.results, ["post-1", "org-1"]);
  assert.equal(shown.error, null);
});

test("iPhone keyboard 検索 key runs the same submit as the button", async () => {
  const ui = createSearchTabHarness();
  ui.type("新歓");
  const fromButton = submitSearchForm({
    pathname: "/search",
    qInput: "新歓",
    activeTab: "all",
  });
  const requestId = ui.submitWithKeyboard();
  const fromKeyboard = ui.snapshot();
  assert.deepEqual(fromButton.fetch, { q: "新歓", tab: "all" });
  assert.deepEqual(fromKeyboard.fetches.at(-1), {
    id: requestId,
    q: "新歓",
    tab: "all",
  });
  const shown = await ui.finish(requestId, { ok: true, results: [] });
  assert.equal(shown.error, null);
  assert.equal(globalSearchEmptyMessage(true), SEARCH_NO_RESULTS_MESSAGE);
  assert.deepEqual(shown.results, []);
});

test("keep-alive HomePage no longer deletes the search tab query", () => {
  const submitted = submitSearchForm({
    pathname: "/search",
    qInput: "チームわせわせ",
    activeTab: "all",
  });
  assert.equal(submitted.q, "チームわせわせ");
  assert.equal(submitted.fetch.q, "チームわせわせ");

  const buggyKeepAlive = stripHomeTimelineLeftoverParams(
    "/",
    submitted.params
  );
  assert.equal(buggyKeepAlive?.get("q") ?? null, null);

  const fixedKeepAlive = stripHomeTimelineLeftoverParams(
    "/search",
    submitted.params
  );
  assert.equal(fixedKeepAlive, null);
});

test("empty submit stays on discover and does not send a q", () => {
  const submitted = submitSearchForm({
    pathname: "/search",
    qInput: "   ",
    activeTab: "users",
  });
  assert.equal(submitted.q, "");
  assert.deepEqual(submitted.fetch, { q: undefined, tab: undefined });
  assert.match(globalSearchEmptyMessage(false), /キーワードを入力/);
});

test("zero results and failures use Japanese copy, not raw API codes", () => {
  assert.equal(globalSearchEmptyMessage(true), SEARCH_NO_RESULTS_MESSAGE);
  assert.equal(
    globalSearchErrorMessage(new Error("search_failed")),
    SEARCH_FAILED_MESSAGE
  );
  assert.equal(
    globalSearchErrorMessage(new Error("Failed to fetch")),
    SEARCH_FAILED_MESSAGE
  );
  assert.equal(
    globalSearchErrorMessage(new Error("同じイベントは見つかりません")),
    "同じイベントは見つかりません"
  );
});

test("a newer search ignores the older response", async () => {
  const ui = createSearchTabHarness();
  ui.type("古い");
  const stale = ui.clickSearchButton();
  ui.type("新しい");
  const latest = ui.submitWithKeyboard();
  await ui.finish(stale, { ok: true, results: ["stale"] });
  assert.deepEqual(ui.snapshot().results, []);
  const shown = await ui.finish(latest, { ok: true, results: ["fresh"] });
  assert.deepEqual(shown.results, ["fresh"]);
  assert.equal(shown.fetches.length, 2);
});

test("API errors keep the button usable and show a Japanese message", async () => {
  const ui = createSearchTabHarness();
  ui.type("ゼミ");
  const first = ui.clickSearchButton();
  const failed = await ui.finish(first, {
    ok: false,
    error: new Error("search_failed"),
  });
  assert.equal(failed.loading, false);
  assert.equal(failed.error, SEARCH_FAILED_MESSAGE);
  const retry = ui.clickSearchButton();
  const recovered = await ui.finish(retry, {
    ok: true,
    results: ["hit"],
  });
  assert.equal(recovered.error, null);
  assert.deepEqual(recovered.results, ["hit"]);
});

test("changing result tabs keeps the submitted query", () => {
  const afterUsers = buildSearchSubmitParams("ミクロ", "users");
  assert.equal(afterUsers.get("q"), "ミクロ");
  assert.equal(afterUsers.get("tab"), "users");
  assert.deepEqual(searchFetchQuery("ミクロ", "users"), {
    q: "ミクロ",
    tab: "users",
  });
});
