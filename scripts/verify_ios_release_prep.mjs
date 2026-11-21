#!/usr/bin/env node
/**
 * Read-only checks for the next App Store iOS archive.
 * Run on any machine; does not upload to Apple.
 *
 * Usage: node scripts/verify_ios_release_prep.mjs
 */
import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const failures = [];

function check(name, fn) {
  try {
    fn();
    console.log(`PASS  ${name}`);
  } catch (error) {
    failures.push(name);
    console.error(`FAIL  ${name}: ${error.message || error}`);
  }
}

const pkg = JSON.parse(readFileSync(join(root, "package.json"), "utf8"));
const cap = JSON.parse(readFileSync(join(root, "capacitor.config.json"), "utf8"));
const podfile = readFileSync(join(root, "ios/App/Podfile"), "utf8");
const podlock = readFileSync(join(root, "ios/App/Podfile.lock"), "utf8");
const pbx = readFileSync(join(root, "ios/App/App.xcodeproj/project.pbxproj"), "utf8");
const info = readFileSync(join(root, "ios/App/App/Info.plist"), "utf8");
const releaseEnt = readFileSync(
  join(root, "ios/App/App/App.Release.entitlements"),
  "utf8"
);
const appDelegate = readFileSync(join(root, "ios/App/App/AppDelegate.swift"), "utf8");
const nativeJs = readFileSync(join(root, "static/js/capacitor_native.js"), "utf8");

check("@capacitor/keyboard in package.json", () => {
  assert.ok(pkg.dependencies?.["@capacitor/keyboard"]);
});

check("capacitor.config.json registers Keyboard plugin", () => {
  assert.ok(cap.plugins?.Keyboard);
});

check("Podfile includes CapacitorKeyboard", () => {
  assert.match(podfile, /pod 'CapacitorKeyboard'/);
});

check("Podfile.lock resolves CapacitorKeyboard", () => {
  assert.match(podlock, /CapacitorKeyboard/);
});

check("MARKETING_VERSION is 1.0.2+", () => {
  assert.match(pbx, /MARKETING_VERSION = 1\.0\.2;/);
});

check("CURRENT_PROJECT_VERSION >= 36", () => {
  const m = [...pbx.matchAll(/CURRENT_PROJECT_VERSION = (\d+);/g)].map((x) =>
    Number(x[1])
  );
  assert.ok(m.length >= 2);
  assert.ok(m.every((n) => n >= 36), `got ${m.join(",")}`);
});

check("swipe-back enabled in AppDelegate", () => {
  assert.match(appDelegate, /allowsBackForwardNavigationGestures\s*=\s*true/);
});

check("Release entitlements use production aps-environment", () => {
  assert.match(releaseEnt, /<string>production<\/string>/);
});

check("Info.plist has remote-notification background mode", () => {
  assert.match(info, /remote-notification/);
});

check("Info.plist has camera/photo usage strings", () => {
  assert.match(info, /NSCameraUsageDescription/);
  assert.match(info, /NSPhotoLibraryUsageDescription/);
});

check("capacitor server.url points at production SPA", () => {
  assert.equal(cap.server?.url, "https://wasewase.onrender.com/app/");
});

check("native bridge exposes openSystemSettings", () => {
  assert.match(nativeJs, /openSystemSettings\s*:/);
});

check("native bridge refreshes push permission on foreground", () => {
  assert.match(nativeJs, /refreshPushPermissionOnForeground/);
  assert.match(nativeJs, /visibilitychange/);
});

check("FirebaseMessaging dependency present", () => {
  assert.ok(pkg.dependencies?.["@capacitor-firebase/messaging"]);
  assert.match(podlock, /CapacitorFirebaseMessaging/);
});

const google = join(root, "ios/App/App/GoogleService-Info.plist");
const googleRoot = join(root, "GoogleService-Info.plist");
if (existsSync(google) || existsSync(googleRoot)) {
  console.log("PASS  GoogleService-Info.plist is present locally");
} else {
  console.warn(
    "WARN  GoogleService-Info.plist missing here (gitignored). Place it before Archive on the Mac."
  );
}

console.log("");
if (failures.length) {
  console.error(`verify_ios_release_prep: ${failures.length} failure(s)`);
  process.exit(1);
}
console.log("verify_ios_release_prep: all required checks passed");
console.log("Next (on Mac, not in this agent): npm ci && npm run cap:sync && pod install && Archive");
console.log("Do not upload to App Store Connect until explicitly approved.");
