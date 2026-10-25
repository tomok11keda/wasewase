import assert from "node:assert/strict";
import test from "node:test";
import {
  DETAIL_NETWORK_ERROR,
  detailContentPhase,
  detailItemMatches,
  isTransientDetailError,
  isUnavailableDetailError,
  shouldKeepDetailPreview,
} from "./detailContentPhase.ts";
import {
  isLatestRequest,
  isSameUserScope,
  nextRequestId,
} from "./userScopedResult.ts";

const idle = {
  browsePreview: false,
  loading: false,
  error: null as string | null,
  hasItem: false,
  hydrated: false,
};

test("deep link without a snapshot uses a skeleton", () => {
  assert.equal(
    detailContentPhase({ ...idle, loading: true }),
    "skeleton"
  );
});

test("a matching preview shows immediately instead of a skeleton", () => {
  assert.equal(
    detailContentPhase({ ...idle, hasItem: true, loading: true }),
    "preview"
  );
  assert.equal(
    detailContentPhase({
      ...idle,
      hasItem: true,
      hydrated: true,
    }),
    "ready"
  );
});

test("browse preview never shows a logged-in detail skeleton", () => {
  assert.equal(
    detailContentPhase({ ...idle, browsePreview: true, loading: true }),
    "browse"
  );
});

test("403/404 without an item are errors, not skeletons", () => {
  assert.equal(
    detailContentPhase({ ...idle, error: "not_found" }),
    "error"
  );
  assert.equal(
    detailContentPhase({ ...idle, error: "forbidden", hasItem: false }),
    "error"
  );
});

test("unavailable errors discard previews; network errors are transient", () => {
  assert.equal(isUnavailableDetailError(new Error("not_found")), true);
  assert.equal(isUnavailableDetailError(new Error("forbidden")), true);
  assert.equal(
    isUnavailableDetailError(new Error("この投稿は表示できません")),
    true
  );
  assert.equal(isTransientDetailError(new TypeError("Failed to fetch")), true);
  assert.equal(
    isUnavailableDetailError(new TypeError("Failed to fetch")),
    false
  );
  assert.equal(
    shouldKeepDetailPreview(true, new TypeError("Failed to fetch")),
    true
  );
  assert.equal(shouldKeepDetailPreview(true, new Error("not_found")), false);
  assert.equal(shouldKeepDetailPreview(true, new Error("forbidden")), false);
  assert.equal(
    shouldKeepDetailPreview(true, new Error("この投稿は表示できません")),
    false
  );
  assert.equal(
    shouldKeepDetailPreview(false, new TypeError("Failed to fetch")),
    false
  );
});

test("a kept preview after a network error stays preview, not ready", () => {
  assert.equal(
    detailContentPhase({
      ...idle,
      hasItem: true,
      hydrated: false,
      error: DETAIL_NETWORK_ERROR,
    }),
    "preview"
  );
  assert.notEqual(
    detailContentPhase({
      ...idle,
      hasItem: true,
      hydrated: false,
      error: DETAIL_NETWORK_ERROR,
    }),
    "ready"
  );
});

test("a stale item from another route id is not treated as the current item", () => {
  assert.equal(detailItemMatches({ id: 1 }, 1), true);
  assert.equal(detailItemMatches({ id: 1 }, 2), false);
  assert.equal(detailItemMatches(null, 1), false);
  assert.equal(
    detailContentPhase({
      ...idle,
      loading: true,
      hasItem: detailItemMatches({ id: 1 }, 2),
    }),
    "skeleton"
  );
});

test("later detail requests win and user switches drop in-flight rows", () => {
  const ref = { current: 0 };
  const first = nextRequestId(ref);
  const second = nextRequestId(ref);
  assert.equal(isLatestRequest(ref, first), false);
  assert.equal(isLatestRequest(ref, second), true);
  assert.equal(isSameUserScope(11, 22), false);
  assert.equal(isSameUserScope(11, 11), true);
});
