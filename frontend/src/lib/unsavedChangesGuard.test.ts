import assert from "node:assert/strict";
import test from "node:test";
import {
  allowUnsavedNavigation,
  confirmDiscardUnsavedChanges,
  setUnsavedChangesGuard,
  shouldPromptUnsavedChanges,
  spaPathLeavesCurrent,
  UNSAVED_DISCARD_MESSAGE,
} from "./unsavedChangesGuard.ts";

test("unsaved prompt is skipped when clean or after a successful save", () => {
  assert.equal(shouldPromptUnsavedChanges({ dirty: false, bypass: false }), false);
  assert.equal(shouldPromptUnsavedChanges({ dirty: true, bypass: true }), false);
  assert.equal(shouldPromptUnsavedChanges({ dirty: true, bypass: false }), true);
});

test("discard confirm keeps the draft unless the user accepts", () => {
  assert.equal(
    confirmDiscardUnsavedChanges({ dirty: false, bypass: false }, () => false),
    true
  );
  assert.equal(
    confirmDiscardUnsavedChanges({ dirty: true, bypass: true }, () => false),
    true
  );
  let asked = "";
  assert.equal(
    confirmDiscardUnsavedChanges({ dirty: true, bypass: false }, (message) => {
      asked = message;
      return false;
    }),
    false
  );
  assert.equal(asked, UNSAVED_DISCARD_MESSAGE);
  assert.equal(
    confirmDiscardUnsavedChanges({ dirty: true, bypass: false }, () => true),
    true
  );
});

test("registered leave guard can cancel navigation and is cleared on unmount", () => {
  setUnsavedChangesGuard(() => false);
  assert.equal(allowUnsavedNavigation(), false);
  setUnsavedChangesGuard(null);
  assert.equal(allowUnsavedNavigation(), true);
});

test("same settings path is not a leave; profile and query changes are", () => {
  assert.equal(
    spaPathLeavesCurrent("/app/settings/profile", "/settings/profile"),
    false
  );
  assert.equal(
    spaPathLeavesCurrent("/app/users/7/posts", "/settings/profile"),
    true
  );
  assert.equal(
    spaPathLeavesCurrent("/settings/profile", "/settings/profile", "?x=1", ""),
    true
  );
});
