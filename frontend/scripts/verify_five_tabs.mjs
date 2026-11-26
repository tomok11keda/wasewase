/**
 * Phase A five-tab smoke (iPhone viewport).
 * Requires: Django with WASE_REACT_SPA=True (browse mode OK for chrome checks).
 * Usage: node scripts/verify_five_tabs.mjs [baseUrl]
 */
import { chromium } from "playwright";
import { mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const baseUrl = (process.argv[2] || "http://127.0.0.1:8000").replace(/\/$/, "");
const spaUrl = `${baseUrl}/app/`;
const __dirname = dirname(fileURLToPath(import.meta.url));
const shotDir = join(__dirname, "../../artifacts/five-tab-redesign");
mkdirSync(shotDir, { recursive: true });

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

function fail(msg) {
  console.error(`FAIL: ${msg}`);
  process.exit(1);
}

const browser = await launchBrowser();
const page = await browser.newPage();
await page.setViewportSize({ width: 390, height: 844 });

await page.goto(spaUrl, { waitUntil: "networkidle" });
await page.waitForSelector("nav.bottom-nav", { timeout: 20000 });

const labels = await page
  .locator("nav.bottom-nav a.nav-item span")
  .evaluateAll((els) =>
    els
      .map((el) => el.textContent?.trim() || "")
      .filter((t) => t && !t.includes("現在"))
  );

const expected = ["ホーム", "見つける", "時間割", "授業", "フリマ"];
if (JSON.stringify(labels) !== JSON.stringify(expected)) {
  fail(`bottom nav labels ${JSON.stringify(labels)} != ${JSON.stringify(expected)}`);
}
console.log(`bottom nav OK: ${labels.join(" → ")}`);

const tabs = [
  { label: "ホーム", page: "タイムライン", path: /\/app\/?$/ },
  { label: "見つける", page: "見つける", path: /\/app\/search\/?$/ },
  { label: "時間割", page: "時間割", path: /\/app\/timetable\/?$/ },
  { label: "授業", page: "授業", path: /\/app\/courses\/?$/ },
  { label: "フリマ", page: "フリマ", path: /\/app\/flea\/?$/ },
];

for (const tab of tabs) {
  await page.locator("nav.bottom-nav a.nav-item", { hasText: tab.label }).click();
  await page.waitForURL(tab.path, { timeout: 10000 });
  await page.waitForSelector(`[data-spa-page="${tab.page}"]`, { timeout: 10000 });
  const active = await page
    .locator("nav.bottom-nav a.nav-item.is-active")
    .innerText();
  if (!active.includes(tab.label)) {
    fail(`active tab "${active}" after clicking ${tab.label}`);
  }
  console.log(`tab ${tab.label} -> ${page.url()}`);
}

await page.locator("nav.bottom-nav a.nav-item", { hasText: "授業" }).click();
await page.waitForSelector('[data-spa-page="授業"]', { timeout: 10000 });
await page.waitForTimeout(400);
await page.screenshot({
  path: join(shotDir, "01-courses-tab-iphone.png"),
});

await page.locator("nav.bottom-nav a.nav-item", { hasText: "見つける" }).click();
await page.waitForSelector('[data-spa-page="見つける"]', { timeout: 10000 });
await page.waitForSelector(".discover-gates, .search-form", { timeout: 10000 });
if ((await page.locator(".discover-gate--soon").count()) > 0) {
  fail("Phase B soon gate must not be student-visible");
}
if ((await page.locator("text=Phase B").count()) > 0) {
  fail("Phase B label must not be student-visible");
}
await page.waitForTimeout(400);
await page.screenshot({
  path: join(shotDir, "02-find-tab-iphone.png"),
});

// Legacy hub=courses → /courses
await page.goto(`${baseUrl}/app/communities?hub=courses`, {
  waitUntil: "networkidle",
});
await page.waitForURL(/\/app\/courses/, { timeout: 15000 });
await page.waitForSelector('[data-spa-page="授業"]', { timeout: 10000 });
console.log(`hub=courses redirect -> ${page.url()}`);

// Communities remains reachable (detail chrome)
await page.goto(`${baseUrl}/app/communities`, { waitUntil: "networkidle" });
await page.waitForSelector('[data-spa-page="コミュニティ"]', { timeout: 15000 });
const onCommunities = page.url();
if (!/\/app\/communities\/?$/.test(onCommunities.replace(/\?.*$/, ""))) {
  fail(`expected /communities, got ${onCommunities}`);
}
await page.waitForTimeout(400);
await page.screenshot({
  path: join(shotDir, "03-communities-detail-iphone.png"),
});
console.log(`communities direct -> ${onCommunities}`);

// Keep-alive: visit courses → flea → courses; pane should stay mounted
await page.locator("nav.bottom-nav a.nav-item", { hasText: "授業" }).click();
await page.waitForSelector('[data-spa-page="授業"]', { timeout: 10000 });
await page.locator("nav.bottom-nav a.nav-item", { hasText: "フリマ" }).click();
await page.waitForSelector('[data-spa-page="フリマ"]', { timeout: 10000 });
const coursesPane = page.locator('[data-tab-pane="courses"]');
if ((await coursesPane.count()) === 0) {
  console.log("note: courses keep-alive pane not mounted (diag/no-keepalive?)");
} else {
  console.log("courses keep-alive pane still in DOM after leaving");
}
await page.locator("nav.bottom-nav a.nav-item", { hasText: "ホーム" }).click();
await page.waitForSelector('[data-spa-page="タイムライン"]', { timeout: 10000 });
await page.waitForTimeout(400);
await page.screenshot({
  path: join(shotDir, "04-bottom-nav-iphone.png"),
});

await browser.close();
console.log(`OK five-tab smoke. shots -> ${shotDir}`);
