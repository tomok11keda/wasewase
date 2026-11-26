/**
 * Category search mode vs Discover hub.
 * Usage: SESSION_ID=... node scripts/verify_find_category_mode.mjs [baseUrl]
 */
import { chromium } from "playwright";
import { mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const baseUrl = (process.argv[2] || "http://127.0.0.1:8000").replace(/\/$/, "");
const __dirname = dirname(fileURLToPath(import.meta.url));
const shotDir = join(__dirname, "../../artifacts/find-category-mode");
mkdirSync(shotDir, { recursive: true });

function fail(msg) {
  console.error(`FAIL: ${msg}`);
  process.exit(1);
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
const context = await browser.newContext({
  viewport: { width: 390, height: 844 },
});
if (process.env.SESSION_ID) {
  await context.addCookies([
    {
      name: "sessionid",
      value: process.env.SESSION_ID,
      domain: "127.0.0.1",
      path: "/",
      httpOnly: true,
    },
  ]);
}
const page = await context.newPage();

if (!process.env.SESSION_ID) {
  const browse = await page.request.post(`${baseUrl}/api/v1/auth/browse/`, {
    data: {},
    headers: { Accept: "application/json" },
  });
  if (!browse.ok()) fail(`browse failed ${browse.status()}`);
}

await page.goto(`${baseUrl}/app/search`, { waitUntil: "networkidle" });
if (page.url().includes("/login")) fail(`login redirect: ${page.url()}`);
await page.waitForSelector(".discover-gates", { timeout: 20000 });

// Enter accounts category
await page.locator('[data-discover-gate="accounts"]').click();
await page.waitForURL(/tab=users/, { timeout: 10000 });
await page.waitForSelector(".search-tabs", { timeout: 10000 });
if ((await page.locator(".discover-gates").count()) > 0) {
  fail("discover still visible after accounts entry");
}

// Empty-query category switches must NOT return to Discover
const emptyHints = {
  all: /横断検索/,
  latest: /最新の投稿/,
  courses: /授業名/,
  products: /商品名|教科書/,
  users: /団体名|ユーザー名/,
};
for (const key of ["all", "latest", "courses", "products", "users"]) {
  await page.locator(`[data-search-category="${key}"]`).click();
  await page.waitForTimeout(200);
  if ((await page.locator(".discover-gates").count()) > 0) {
    fail(`switched to ${key} with empty q but Discover returned`);
  }
  if (!(await page.url()).includes(`tab=${key}`)) {
    fail(`url missing tab=${key}: ${page.url()}`);
  }
  if ((await page.locator("[data-search-discover-back]").count()) < 1) {
    fail(`missing Discover back link on tab=${key}`);
  }
  const empty = (await page.locator(".search-empty").innerText()).trim();
  if (!emptyHints[key].test(empty)) {
    fail(`empty hint mismatch on ${key}: ${empty}`);
  }
  const ph = await page.locator('input[name="q"]').getAttribute("placeholder");
  if (!ph || ph.length < 4) {
    fail(`missing category placeholder on ${key}`);
  }
}
console.log("empty-query category switches stay in category mode");

await page.screenshot({ path: join(shotDir, "01-empty-category-switch.png") });

// Explicit back to Discover
await page.locator("[data-search-discover-back]").click();
await page.waitForSelector(".discover-gates", { timeout: 10000 });
if ((await page.url()).includes("tab=")) {
  fail(`discover back left tab in url: ${page.url()}`);
}
console.log("discover back OK");

// Re-enter accounts, type query, switch categories keeping q
await page.locator('[data-discover-gate="accounts"]').click();
await page.waitForURL(/tab=users/, { timeout: 10000 });
await page.fill('input[name="q"]', "わせ");
await page.locator(".search-form button[type=submit]").click();
await page.waitForURL(/q=/, { timeout: 10000 });
await page.locator('[data-search-category="courses"]').click();
await page.waitForTimeout(300);
const withQ = page.url();
if (!/q=/.test(withQ) || !/tab=courses/.test(withQ)) {
  fail(`query not kept on tab switch: ${withQ}`);
}
if ((await page.locator(".discover-gates").count()) > 0) {
  fail("discover shown while query present");
}
console.log(`query kept on category switch -> ${withQ}`);

await page.screenshot({ path: join(shotDir, "02-query-category-switch.png") });

// Browser back then forward
await page.goBack();
await page.waitForTimeout(400);
const afterBack = page.url();
if (!/tab=users/.test(afterBack) || !/q=/.test(afterBack)) {
  fail(`history back unexpected: ${afterBack}`);
}
await page.goForward();
await page.waitForTimeout(400);
const afterFwd = page.url();
if (!/tab=courses/.test(afterFwd) || !/q=/.test(afterFwd)) {
  fail(`history forward unexpected: ${afterFwd}`);
}
console.log(`history back/forward OK (${afterBack} → ${afterFwd})`);

// Deep link: ?tab=products with empty q stays in category mode
await page.goto(`${baseUrl}/app/search?tab=products`, {
  waitUntil: "networkidle",
});
await page.waitForSelector(".search-tabs", { timeout: 10000 });
if ((await page.locator(".discover-gates").count()) > 0) {
  fail("deep link ?tab=products opened Discover");
}
console.log("deep link ?tab=products OK");

await browser.close();
console.log(`OK find category mode. shots -> ${shotDir}`);
