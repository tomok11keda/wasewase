import assert from "node:assert/strict";
import test from "node:test";
import { listContentPhase, listQueryKey } from "./listContentPhase.ts";
import {
  isLatestRequest,
  isSameUserScope,
  nextRequestId,
} from "./userScopedResult.ts";

const idle = {
  browsePreview: false,
  loading: false,
  error: null as string | null,
  itemCount: 0,
  matchesCurrentQuery: true,
};

test("first load shows a skeleton instead of an empty list", () => {
  assert.equal(
    listContentPhase({
      ...idle,
      loading: true,
      matchesCurrentQuery: false,
    }),
    "skeleton"
  );
});

test("browse preview never uses a logged-in list skeleton", () => {
  assert.equal(
    listContentPhase({ ...idle, browsePreview: true, loading: true }),
    "browse"
  );
});

test("soft refetch keeps rows for the same query", () => {
  assert.equal(
    listContentPhase({ ...idle, loading: true, itemCount: 4 }),
    "ready"
  );
});

test("an applied empty list stays empty during same-query refetch", () => {
  assert.equal(listContentPhase(idle), "empty");
  assert.equal(
    listContentPhase({ ...idle, loading: true, itemCount: 0 }),
    "empty"
  );
});

test("a changed query skeletons instead of showing the previous rows", () => {
  assert.equal(
    listContentPhase({
      ...idle,
      matchesCurrentQuery: false,
      itemCount: 4,
    }),
    "skeleton"
  );
  assert.equal(
    listContentPhase({
      ...idle,
      loading: true,
      matchesCurrentQuery: false,
      itemCount: 4,
    }),
    "skeleton"
  );
});

test("empty, error, and ready stay distinct", () => {
  assert.equal(listContentPhase(idle), "empty");
  assert.equal(
    listContentPhase({ ...idle, error: "load_failed" }),
    "error"
  );
  assert.equal(
    listContentPhase({ ...idle, itemCount: 2 }),
    "ready"
  );
  assert.equal(
    listContentPhase({
      ...idle,
      loading: false,
      matchesCurrentQuery: false,
      error: "load_failed",
    }),
    "error"
  );
});

test("query keys distinguish search terms, filters, and users", () => {
  assert.notEqual(listQueryKey(["book"]), listQueryKey(["note"]));
  assert.notEqual(
    listQueryKey(["all", "waseda"]),
    listQueryKey(["all", "nishi"])
  );
  assert.equal(listQueryKey(["all", ""]), listQueryKey(["all", ""]));
  assert.notEqual(
    listQueryKey([11, "all", "book"]),
    listQueryKey([22, "all", "book"])
  );
  assert.notEqual(
    listQueryKey(["guest", "discover", ""]),
    listQueryKey([11, "discover", ""])
  );
});

test("a stale in-flight search does not count as the current result", () => {
  const previous = listQueryKey(["guest", "all", "book"]);
  const current = listQueryKey(["guest", "all", "note"]);
  assert.notEqual(previous, current);
  assert.equal(
    listContentPhase({
      browsePreview: false,
      loading: true,
      error: null,
      itemCount: 3,
      matchesCurrentQuery: previous === current,
    }),
    "skeleton"
  );
});

test("later search requests win and user switches drop in-flight rows", () => {
  const ref = { current: 0 };
  const first = nextRequestId(ref);
  const second = nextRequestId(ref);
  assert.equal(isLatestRequest(ref, first), false);
  assert.equal(isLatestRequest(ref, second), true);
  assert.equal(isSameUserScope(11, 22), false);
  assert.equal(isSameUserScope(11, 11), true);
  assert.equal(isSameUserScope(11, null), false);
});
