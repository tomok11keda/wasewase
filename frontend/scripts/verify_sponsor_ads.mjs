/**
 * Sponsor ads MVP (home + discover) — phone viewport.
 * Uses mock SPA with fictional inventory; does not hit production.
 * Usage: node scripts/verify_sponsor_ads.mjs [baseUrl]
 */
import { chromium } from "playwright";
import { mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const baseUrl = (process.argv[2] || "http://127.0.0.1:8767").replace(/\/$/, "");
const __dirname = dirname(fileURLToPath(import.meta.url));
const shotDir = join(__dirname, "../../artifacts/sponsor-ads-mvp");
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
const page = await context.newPage();

await page.goto(`${baseUrl}/app/`, { waitUntil: "domcontentloaded" });
await page.waitForSelector("[data-sponsor-ad]", { timeout: 20000 });

// Home: sponsor after 2 posts
const homeCards = page.locator("[data-sponsor-ad]");
const homeCount = await homeCards.count();
if (homeCount < 1) fail("home sponsor card missing");
const homePlacement = await homeCards.first().getAttribute("data-sponsor-placement");
if (homePlacement !== "home_feed") fail(`home placement ${homePlacement}`);
const badge = (await homeCards.first().locator(".sponsor-ad-card__badge").innerText()).trim();
if (!/スポンサー|公式/.test(badge)) fail(`unexpected badge ${badge}`);
await page.screenshot({ path: join(shotDir, "01-home-sponsor.png"), fullPage: true });
console.log("home sponsor OK");

// Discover
await page.goto(`${baseUrl}/app/search`, { waitUntil: "domcontentloaded" });
await page.waitForSelector("[data-discover-sponsor]", { timeout: 20000 });
const rail = page.locator("[data-discover-sponsor]");
if ((await rail.count()) < 1) fail("discover sponsor rail missing");
const discoverCards = rail.locator("[data-sponsor-ad]");
if ((await discoverCards.count()) < 1) fail("discover sponsor card missing");
await page.screenshot({
  path: join(shotDir, "02-discover-sponsor.png"),
  fullPage: true,
});
console.log("discover sponsor OK");

// Flag-off regression path via mock cookie (API serves empty sponsor)
await context.addCookies([
  {
    name: "mock_sponsor_off",
    value: "1",
    domain: "127.0.0.1",
    path: "/",
  },
]);
await page.goto(`${baseUrl}/app/`, { waitUntil: "domcontentloaded" });
await page.waitForSelector(".timeline-list, .home-feed, [data-spa-page]", {
  timeout: 20000,
});
await page.waitForTimeout(800);
if ((await page.locator("[data-sponsor-ad]").count()) > 0) {
  fail("sponsor still visible when mock flag off");
}
console.log("flag-off mock OK");

await browser.close();
console.log(`OK sponsor ads. shots -> ${shotDir}`);
