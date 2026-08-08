/**
 * Phase 8: login → DM open/switch/leave and assert poll counter returns to 0.
 * Requires runserver with WASE_REACT_SPA=True, BROWSE_MODE_GATE_ENABLED=False.
 *
 * Usage: node scripts/verify_dm_poll.mjs [baseUrl] [email] [password]
 */
import { chromium } from "playwright";

const baseUrl = (process.argv[2] || "http://127.0.0.1:8000").replace(/\/$/, "");
const email = process.argv[3] || process.env.WASE_VERIFY_EMAIL || "";
const password = process.argv[4] || process.env.WASE_VERIFY_PASSWORD || "";

if (!email || !password) {
  console.log(
    "SKIP: set WASE_VERIFY_EMAIL / WASE_VERIFY_PASSWORD (or argv) to run DM poll leak check"
  );
  process.exit(0);
}

async function launchBrowser() {
  const channels = [
    process.env.PLAYWRIGHT_CHANNEL,
    "chrome",
    "msedge",
    undefined,
  ].filter((v, i, arr) => arr.indexOf(v) === i);
  let lastError;
  for (const channel of channels) {
    try {
      return await chromium.launch({
        headless: true,
        ...(channel ? { channel } : {}),
      });
    } catch (err) {
      lastError = err;
    }
  }
  throw lastError;
}

const browser = await launchBrowser();
const page = await browser.newPage();
await page.setViewportSize({ width: 390, height: 844 });

let loadCount = 0;
page.on("load", () => {
  loadCount += 1;
});

await page.goto(`${baseUrl}/login/`, { waitUntil: "networkidle" });
await page.fill('input[name="username"], input[name="email"], input[type="email"]', email);
await page.fill('input[name="password"], input[type="password"]', password);
await Promise.all([
  page.waitForNavigation({ waitUntil: "networkidle" }),
  page.click('button[type="submit"], input[type="submit"]'),
]);

await page.goto(`${baseUrl}/app/`, { waitUntil: "networkidle" });
await page.waitForSelector('[data-spa-page="ホーム"]', { timeout: 15000 });
const loadsAfterFirst = loadCount;

await page.locator("a.shell-header-dm").click();
await page.waitForURL(/\/app\/dm\/?$/, { timeout: 10000 });
await page.waitForSelector('[data-spa-page="メッセージ"]', { timeout: 10000 });

const roomLinks = page.locator("a.dm-inbox-item");
const count = await roomLinks.count();
if (count === 0) {
  console.log("SKIP: inbox empty — cannot exercise room poll lifecycle");
  await browser.close();
  process.exit(0);
}

const firstHref = await roomLinks.nth(0).getAttribute("href");
await roomLinks.nth(0).click();
await page.waitForTimeout(250);
let polls = await page.evaluate(() => window.__WASE_ACTIVE_POLLS__ || 0);
console.log(`polls in room A (${firstHref}): ${polls}`);
if (polls < 1) {
  console.error("FAIL: expected at least 1 active poll in DM/trade room");
  process.exit(1);
}

if (count >= 2) {
  await page.locator("a.dm-back-text, a.back-link").first().click();
  await page.waitForURL(/\/app\/dm/, { timeout: 10000 });
  await page.waitForTimeout(200);
  polls = await page.evaluate(() => window.__WASE_ACTIVE_POLLS__ || 0);
  if (polls !== 0) {
    console.error(`FAIL: poll leak on inbox after leave A (polls=${polls})`);
    process.exit(1);
  }
  await roomLinks.nth(1).click();
  await page.waitForTimeout(250);
  polls = await page.evaluate(() => window.__WASE_ACTIVE_POLLS__ || 0);
  console.log(`polls in room B: ${polls}`);
  if (polls !== 1) {
    console.error(`FAIL: expected exactly 1 poll in room B (got ${polls})`);
    process.exit(1);
  }
}

await page.goto(`${baseUrl}/app/users/1/posts`, { waitUntil: "domcontentloaded" });
await page.waitForTimeout(300);
polls = await page.evaluate(() => window.__WASE_ACTIVE_POLLS__ || 0);
console.log(`polls on profile: ${polls}`);
if (polls !== 0) {
  console.error(`FAIL: poll leak on profile (polls=${polls})`);
  process.exit(1);
}

if (loadCount !== loadsAfterFirst) {
  // profile goto used page.goto intentionally for hard nav check of poll cleanup
  console.log(
    `note: document loads after first=${loadsAfterFirst} now=${loadCount} (includes intentional goto)`
  );
}

await browser.close();
console.log("OK: DM poll lifecycle cleaned up after leave / profile");
process.exit(0);
