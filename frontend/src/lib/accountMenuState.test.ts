import assert from "node:assert/strict";
import test from "node:test";
import {
  ACCOUNT_MENU_STATE_KEY,
  isAccountMenuState,
  shouldReplaceAccountMenu,
  withAccountMenuState,
} from "./accountMenuState.ts";

test("account menu state is opt-in and preserves existing location state", () => {
  assert.equal(isAccountMenuState(undefined), false);
  assert.equal(isAccountMenuState({ fromWaseWase: true }), false);
  const next = withAccountMenuState({ fromWaseWase: true });
  assert.equal(next.fromWaseWase, true);
  assert.equal(next[ACCOUNT_MENU_STATE_KEY], true);
  assert.equal(isAccountMenuState(next), true);
});

test("settings-like overlay pushes keep the menu under the detail page", () => {
  assert.equal(
    shouldReplaceAccountMenu({ overlayNavigation: true, restoreMenu: true }),
    false
  );
  assert.equal(
    shouldReplaceAccountMenu({ overlayNavigation: true, restoreMenu: false }),
    true
  );
  assert.equal(
    shouldReplaceAccountMenu({ overlayNavigation: false, restoreMenu: false }),
    false
  );
});
