const fs = require("fs");
const path = require("path");

const root = path.join(__dirname, "..");
const source = path.join(root, "ios", "App", "patches", "AdMobPlugin.no-att.swift");
const destination = path.join(
  root,
  "node_modules",
  "@capacitor-community",
  "admob",
  "ios",
  "Sources",
  "AdMobPlugin",
  "AdMobPlugin.swift"
);

if (!fs.existsSync(source)) {
  console.warn("[WASE] AdMob patch source missing:", source);
  process.exit(0);
}

if (!fs.existsSync(path.dirname(destination))) {
  console.warn("[WASE] AdMob plugin not installed; skip ATT patch");
  process.exit(0);
}

fs.copyFileSync(source, destination);
console.log("[WASE] Applied AdMob ATT removal patch");
