import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

const root = join(dirname(fileURLToPath(import.meta.url)), "..", "..");

function shouldShow({
  pluginAvailable,
  permission,
  dismissedThisSession,
  authenticated,
  onboardingRequired,
  pathname,
}) {
  if (!pluginAvailable) return false;
  if (dismissedThisSession) return false;
  if (!authenticated) return false;
  if (onboardingRequired) return false;
  const prefixes = [
    "/login",
    "/signup",
    "/verify",
    "/onboarding",
    "/password-reset",
    "/internal/push-diag",
  ];
  if (prefixes.some((p) => pathname === p || pathname.startsWith(`${p}/`))) {
    return false;
  }
  return permission === "prompt";
}

function shouldRequestOnCta({
  pluginAvailable,
  permission,
  userTappedEnable,
  requestInFlight,
}) {
  return (
    pluginAvailable &&
    userTappedEnable &&
    permission === "prompt" &&
    !requestInFlight
  );
}

test("plugin unavailable → no prompt", () => {
  assert.equal(
    shouldShow({
      pluginAvailable: false,
      permission: "prompt",
      dismissedThisSession: false,
      authenticated: true,
      onboardingRequired: false,
      pathname: "/",
    }),
    false
  );
});

test("granted → no pre-permission UI", () => {
  assert.equal(
    shouldShow({
      pluginAvailable: true,
      permission: "granted",
      dismissedThisSession: false,
      authenticated: true,
      onboardingRequired: false,
      pathname: "/",
    }),
    false
  );
});

test("notDetermined / prompt → pre-permission UI on home", () => {
  assert.equal(
    shouldShow({
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

test("positive CTA is the only requestPermissions trigger", () => {
  assert.equal(
    shouldRequestOnCta({
      pluginAvailable: true,
      permission: "prompt",
      userTappedEnable: false,
      requestInFlight: false,
    }),
    false
  );
  assert.equal(
    shouldRequestOnCta({
      pluginAvailable: true,
      permission: "prompt",
      userTappedEnable: true,
      requestInFlight: false,
    }),
    true
  );
});

test("あとで → requestPermissions not called", () => {
  assert.equal(
    shouldRequestOnCta({
      pluginAvailable: true,
      permission: "prompt",
      userTappedEnable: false,
      requestInFlight: false,
    }),
    false
  );
  assert.equal(
    shouldShow({
      pluginAvailable: true,
      permission: "prompt",
      dismissedThisSession: true,
      authenticated: true,
      onboardingRequired: false,
      pathname: "/",
    }),
    false
  );
});

test("denied → no automatic request / no UI", () => {
  assert.equal(
    shouldShow({
      pluginAvailable: true,
      permission: "denied",
      dismissedThisSession: false,
      authenticated: true,
      onboardingRequired: false,
      pathname: "/",
    }),
    false
  );
  assert.equal(
    shouldRequestOnCta({
      pluginAvailable: true,
      permission: "denied",
      userTappedEnable: true,
      requestInFlight: false,
    }),
    false
  );
});

test("native bootstrap source never auto-requests", () => {
  const js = readFileSync(
    join(root, "static/js/capacitor_native.js"),
    "utf8"
  );
  const start = js.indexOf("async function initializePushNotifications");
  const end = js.indexOf("async function requestPushPermissionFromUser");
  const init = js.slice(start, end);
  assert.equal(init.includes("requestPermissions"), false);
  assert.equal(init.includes("readReceivePermission"), true);
  assert.equal(js.includes("wase:push-open"), true);
});
