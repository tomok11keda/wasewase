import assert from "node:assert/strict";
import test from "node:test";
import {
  normalizePushPermissionUx,
  shouldOfferPushEnableCta,
  shouldOpenSystemSettingsForPush,
  shouldShowPushPrePermission,
  shouldShowSettingsPushControls,
} from "./pushPrePermission.ts";

test("normalizePushPermissionUx maps Capacitor receive strings", () => {
  assert.equal(normalizePushPermissionUx("prompt"), "prompt");
  assert.equal(normalizePushPermissionUx("granted"), "granted");
  assert.equal(normalizePushPermissionUx("denied"), "denied");
  assert.equal(normalizePushPermissionUx("notDetermined"), "prompt");
  assert.equal(normalizePushPermissionUx(""), "unknown");
});

test("settings push controls require native + plugin", () => {
  assert.equal(
    shouldShowSettingsPushControls({
      isNativeApp: true,
      pluginAvailable: true,
    }),
    true
  );
  assert.equal(
    shouldShowSettingsPushControls({
      isNativeApp: false,
      pluginAvailable: true,
    }),
    false
  );
});

test("denied opens system settings; prompt offers in-app enable", () => {
  assert.equal(shouldOpenSystemSettingsForPush("denied"), true);
  assert.equal(shouldOfferPushEnableCta("prompt"), true);
  assert.equal(shouldOfferPushEnableCta("granted"), false);
  assert.equal(shouldOpenSystemSettingsForPush("prompt"), false);
});

test("pre-permission still waits until onboarding finishes", () => {
  assert.equal(
    shouldShowPushPrePermission({
      pluginAvailable: true,
      permission: "prompt",
      dismissedThisSession: false,
      authenticated: true,
      onboardingRequired: true,
      pathname: "/",
    }),
    false
  );
  assert.equal(
    shouldShowPushPrePermission({
      pluginAvailable: true,
      permission: "prompt",
      dismissedThisSession: false,
      authenticated: true,
      onboardingRequired: false,
      pathname: "/",
    }),
    true
  );
});
