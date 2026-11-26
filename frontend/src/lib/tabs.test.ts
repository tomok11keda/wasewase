import assert from "node:assert/strict";
import test from "node:test";
import {
  isConversationPath,
  matchMainTab,
  TAB_ROUTES,
  visibleTabRoutes,
} from "./tabs.ts";

test("Phase A five tabs: home → find → timetable → courses → flea", () => {
  const personal = visibleTabRoutes(false);
  assert.equal(personal, TAB_ROUTES);
  assert.deepEqual(
    personal.map((tab) => tab.id),
    ["home", "search", "timetable", "courses", "flea"]
  );
  assert.deepEqual(
    personal.map((tab) => tab.label),
    ["ホーム", "見つける", "時間割", "授業", "フリマ"]
  );
  assert.deepEqual(
    personal.map((tab) => tab.path),
    ["/", "/search", "/timetable", "/courses", "/flea"]
  );
});

test("org mode hides personal timetable and courses tabs", () => {
  const org = visibleTabRoutes(true);
  assert.deepEqual(
    org.map((tab) => tab.id),
    ["home", "search", "flea"]
  );
  assert.equal(
    org.some((tab) => tab.path === "/timetable" || tab.path === "/courses"),
    false
  );
});

test("matchMainTab is exact for keep-alive tabs; nested routes stay off-tab", () => {
  assert.equal(matchMainTab("/"), "home");
  assert.equal(matchMainTab("/search"), "search");
  assert.equal(matchMainTab("/timetable"), "timetable");
  assert.equal(matchMainTab("/courses"), "courses");
  assert.equal(matchMainTab("/flea"), "flea");
  assert.equal(matchMainTab("/courses/12"), null);
  assert.equal(matchMainTab("/courses/12/talk"), null);
  assert.equal(matchMainTab("/communities"), null);
  assert.equal(matchMainTab("/communities/foo/threads/1"), null);
  assert.equal(matchMainTab("/flea/products/3"), null);
  assert.equal(matchMainTab("/dm"), null);
});

test("compose pickers keep the bottom nav so they are not treated as rooms", () => {
  assert.equal(isConversationPath("/dm/new"), false);
  assert.equal(isConversationPath("/dm/new/direct"), false);
  assert.equal(isConversationPath("/dm/new/org-chat"), false);
  assert.equal(isConversationPath("/dm/groups/new"), false);
  assert.equal(isConversationPath("/dm"), false);
  assert.equal(isConversationPath("/dm/4"), true);
  assert.equal(isConversationPath("/dm/groups/12"), true);
});
