import assert from "node:assert/strict";
import test from "node:test";
import { isConversationPath, TAB_ROUTES, visibleTabRoutes } from "./tabs.ts";

test("org mode hides timetable from the main tabs and keeps the other surfaces", () => {
  const personal = visibleTabRoutes(false);
  assert.equal(personal, TAB_ROUTES);
  assert.deepEqual(
    personal.map((tab) => tab.id),
    ["home", "communities", "search", "flea", "timetable"]
  );

  const org = visibleTabRoutes(true);
  assert.deepEqual(
    org.map((tab) => tab.id),
    ["home", "communities", "search", "flea"]
  );
  assert.equal(
    org.some((tab) => tab.path === "/timetable"),
    false
  );
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
