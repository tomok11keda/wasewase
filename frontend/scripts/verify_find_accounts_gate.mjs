/**
 * Find-hub「学生団体・アカウント」gate + sibling shortcuts.
 * Usage: SESSION_ID=... node scripts/verify_find_accounts_gate.mjs [baseUrl]
 * Or omit SESSION_ID to POST /api/v1/auth/browse/ first.
 */
import { chromium } from "playwright";
import { mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const baseUrl = (process.argv[2] || "http://127.0.0.1:8000").replace(/\/$/, "");
const __dirname = dirname(fileURLToPath(import.meta.url));
const shotDir = join(__dirname, "../../artifacts/find-accounts-gate");
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

async function runViewport(width, height, label) {
  const context = await browser.newContext({ viewport: { width, height } });
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
  page.on("pageerror", (e) => console.log(`[${label}] PAGEERROR`, e.message));

  if (!process.env.SESSION_ID) {
    const browse = await page.request.post(`${baseUrl}/api/v1/auth/browse/`, {
      data: {},
      headers: { Accept: "application/json" },
    });
    if (!browse.ok()) fail(`[${label}] browse failed ${browse.status()}`);
  }

  await page.goto(`${baseUrl}/app/search`, { waitUntil: "networkidle" });
  if (page.url().includes("/login")) {
    fail(`[${label}] redirected to login — set SESSION_ID`);
  }
  await page.waitForSelector('[data-spa-page="見つける"]', { timeout: 20000 });
  await page.waitForSelector(".discover-gates", { timeout: 20000 });

  // Regression: old dead link must not be used
  const accountsHref = await page
    .locator('[data-discover-gate="accounts"]')
    .getAttribute("href");
  if (!accountsHref || accountsHref.includes("q=")) {
    fail(`[${label}] accounts href still has empty q: ${accountsHref}`);
  }
  if (!/tab=users/.test(accountsHref)) {
    fail(`[${label}] accounts href missing tab=users: ${accountsHref}`);
  }

  // Click accounts gate → leave discover, show users tab + prompt
  await page.locator('[data-discover-gate="accounts"]').click();
  await page.waitForURL(/\/app\/search\?.*tab=users/, { timeout: 10000 });
  await page.waitForSelector(".search-tabs", { timeout: 10000 });
  const usersTab = page.locator(".search-tab", { hasText: "アカウント" });
  await usersTab.waitFor({ timeout: 5000 });
  if (!(await usersTab.evaluate((el) => el.classList.contains("is-active")))) {
    fail(`[${label}] アカウント tab not active after gate click`);
  }
  if ((await page.locator(".discover-gates").count()) > 0) {
    fail(`[${label}] discover gates still visible after accounts entry`);
  }
  await page.waitForSelector("text=団体名・ユーザー名", { timeout: 5000 });
  const focused = await page.evaluate(
    () => document.activeElement?.getAttribute("name") === "q"
  );
  if (!focused) {
    console.log(`[${label}] note: search input not focused (ok on some WebViews)`);
  }
  console.log(`[${label}] accounts gate -> ${page.url()}`);
  await page.screenshot({
    path: join(shotDir, `${label}-accounts-entry.png`),
  });

  // Reset to discover hub (desktop hides bottom-nav; use direct URL)
  await page.goto(`${baseUrl}/app/search`, { waitUntil: "networkidle" });
  await page.waitForSelector(".discover-gates", { timeout: 15000 });

  // Sibling gates
  await page.locator('[data-discover-gate="communities"]').click();
  await page.waitForURL(/\/app\/communities/, { timeout: 10000 });
  await page.waitForSelector('[data-spa-page="コミュニティ"]', { timeout: 10000 });
  console.log(`[${label}] communities gate OK`);
  await page.goto(`${baseUrl}/app/search`, { waitUntil: "networkidle" });
  await page.waitForSelector(".discover-gates", { timeout: 15000 });

  await page.locator('[data-discover-gate="courses"]').click();
  await page.waitForURL(/\/app\/courses\/?$/, { timeout: 10000 });
  await page.waitForSelector('[data-spa-page="授業"]', { timeout: 10000 });
  console.log(`[${label}] courses gate OK`);
  await page.goto(`${baseUrl}/app/search`, { waitUntil: "networkidle" });
  await page.waitForSelector(".discover-gates", { timeout: 15000 });

  await page.locator('[data-discover-gate="flea"]').click();
  await page.waitForURL(/\/app\/flea\/?$/, { timeout: 10000 });
  await page.waitForSelector('[data-spa-page="フリマ"]', { timeout: 10000 });
  console.log(`[${label}] flea gate OK`);

  await context.close();
}

await runViewport(390, 844, "iphone");
await runViewport(1280, 800, "desktop");
await browser.close();
console.log(`OK find accounts gate. shots -> ${shotDir}`);
