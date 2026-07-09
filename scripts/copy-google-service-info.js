const fs = require("fs");
const path = require("path");

const root = path.join(__dirname, "..");
const candidates = [
  path.join(root, "GoogleService-Info.plist"),
  path.join(root, "ios", "App", "App", "GoogleService-Info.plist"),
];
const destination = path.join(root, "ios", "App", "App", "GoogleService-Info.plist");

let source = null;
for (const candidate of candidates) {
  if (fs.existsSync(candidate)) {
    source = candidate;
    break;
  }
}

if (!source) {
  console.warn(
    "[WASE] GoogleService-Info.plist not found. Place it in the project root or ios/App/App/."
  );
  process.exit(0);
}

if (path.resolve(source) !== path.resolve(destination)) {
  fs.copyFileSync(source, destination);
  console.log("[WASE] Copied GoogleService-Info.plist to ios/App/App/");
} else {
  console.log("[WASE] GoogleService-Info.plist already in ios/App/App/");
}
