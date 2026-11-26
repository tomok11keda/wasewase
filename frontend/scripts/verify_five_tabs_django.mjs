/**
 * Phase A final verification against a real Django runserver.
 * Usage:
 *   SESSION_ID=<django sessionid> node scripts/verify_five_tabs_django.mjs [baseUrl]
 * Or omit SESSION_ID to enter browse mode via /api/v1/auth/browse/.
 */
import { chromium } from "playwright";
import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const baseUrl = (process.argv[2] || "http://127.0.0.1:8000").replace(/\/$/, "");
const __dirname = dirname(fileURLToPath(import.meta.url));
const shotDir = join(__dirname, "../../artifacts/five-tab-final");
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
page.on("pageerror", (e) => console.log("PAGEERROR", e.message));

if (!process.env.SESSION_ID) {
  // Enter browse mode (requires BROWSE_MODE_GATE_ENABLED=True)
  const browse = await page.request.post(`${baseUrl}/api/v1/auth/browse/`, {
    data: {},
    headers: { Accept: "application/json" },
  });
  if (!browse.ok()) {
    fail(`browse enter failed: ${browse.status()}`);
  }
  console.log("entered browse mode");
}

await page.goto(`${baseUrl}/app/`, { waitUntil: "networkidle" });
if (page.url().includes("/login")) {
  fail(`still on login: ${page.url()} (set SESSION_ID or enable browse)`);
}

await page.waitForSelector("nav.bottom-nav", { timeout: 20000 });

const labels = await page
  .locator("nav.bottom-nav a.nav-item")
  .evaluateAll((els) =>
    els.map((el) => {
      const clone = el.cloneNode(true);
      clone.querySelectorAll(".visually-hidden").forEach((n) => n.remove());
      return (clone.querySelector("span")?.textContent || "").trim();
    })
  );
const expected = ["ホーム", "見つける", "時間割", "授業", "フリマ"];
if (JSON.stringify(labels) !== JSON.stringify(expected)) {
  fail(`labels ${JSON.stringify(labels)} != ${JSON.stringify(expected)}`);
}
console.log(`bottom nav OK: ${labels.join(" → ")}`);

// No Phase B student-facing placeholder
if ((await page.locator(".discover-gate--soon").count()) > 0) {
  fail("Phase B soon gate still visible");
}

const tabs = [
  { label: "ホーム", page: "タイムライン", path: /\/app\/?$/ },
  { label: "見つける", page: "見つける", path: /\/app\/search\/?$/ },
  { label: "時間割", page: "時間割", path: /\/app\/timetable\/?$/ },
  { label: "授業", page: "授業", path: /\/app\/courses\/?$/ },
  { label: "フリマ", page: "フリマ", path: /\/app\/flea\/?$/ },
];
for (const tab of tabs) {
  await page.locator("nav.bottom-nav a.nav-item", { hasText: tab.label }).click();
  await page.waitForURL(tab.path, { timeout: 15000 });
  await page.waitForSelector(`[data-spa-page="${tab.page}"]`, { timeout: 15000 });
  const active = await page.locator("nav.bottom-nav a.nav-item.is-active").innerText();
  if (!active.includes(tab.label)) fail(`active="${active}" after ${tab.label}`);
  console.log(`tab ${tab.label} -> ${page.url()}`);
}

await page.locator("nav.bottom-nav a.nav-item", { hasText: "授業" }).click();
await page.waitForSelector('[data-spa-page="授業"]', { timeout: 15000 });
await page.waitForTimeout(300);
await page.screenshot({ path: join(shotDir, "01-courses-tab.png") });

await page.locator("nav.bottom-nav a.nav-item", { hasText: "見つける" }).click();
await page.waitForSelector('[data-spa-page="見つける"]', { timeout: 15000 });
await page.waitForSelector(".discover-gates", { timeout: 15000 });
if ((await page.locator("text=Phase B").count()) > 0) {
  fail("Phase B text visible to students");
}
if ((await page.locator("text=近日公開").count()) > 0) {
  fail("近日公開 placeholder visible to students");
}
await page.waitForTimeout(300);
await page.screenshot({ path: join(shotDir, "02-find-tab.png") });

// Legacy hub redirect
await page.goto(`${baseUrl}/app/communities?hub=courses`, {
  waitUntil: "networkidle",
});
await page.waitForURL(/\/app\/courses/, { timeout: 15000 });
await page.waitForSelector('[data-spa-page="授業"]', { timeout: 15000 });
console.log(`hub=courses -> ${page.url()}`);

// Communities direct + detail chrome back target
await page.goto(`${baseUrl}/app/communities`, { waitUntil: "networkidle" });
await page.waitForSelector('[data-spa-page="コミュニティ"]', { timeout: 15000 });
const detailTitle = await page.locator("h1.shell-header-title").innerText();
if (detailTitle !== "コミュニティ") {
  fail(`communities header title="${detailTitle}"`);
}
await page.screenshot({ path: join(shotDir, "03-communities.png") });
console.log(`communities direct -> ${page.url()}`);

// Course detail: no route conflict with /courses tab; chrome title 授業
const offeringId = process.env.OFFERING_ID || "1";
await page.goto(`${baseUrl}/app/courses/${offeringId}`, {
  waitUntil: "networkidle",
});
await page.waitForURL(new RegExp(`/app/courses/${offeringId}/?$`), {
  timeout: 15000,
});
await page.waitForSelector('[data-spa-page="授業"]', { timeout: 15000 });
const courseTitle = await page.locator("h1.shell-header-title").innerText();
if (courseTitle !== "授業") {
  fail(`course detail header title="${courseTitle}" (expected 授業)`);
}
// BottomNav may highlight 授業 via prefix match — OK
const coursesActive = await page
  .locator('nav.bottom-nav a.nav-item[href$="/courses"]')
  .evaluate((el) => el.classList.contains("is-active"));
console.log(`course detail /courses/${offeringId} header=授業 navActive=${coursesActive}`);
await page.screenshot({ path: join(shotDir, "04-course-detail.png") });

// Back from course detail (history-or-fallback)
await page.locator("button.shell-header-back").click();
await page.waitForTimeout(800);
console.log(`after course detail back -> ${page.url()}`);

// Course talk room path (conversation chrome hides bottom nav)
await page.goto(`${baseUrl}/app/courses/${offeringId}/talk`, {
  waitUntil: "networkidle",
});
await page.waitForTimeout(1000);
const talkHidden = await page.evaluate(() =>
  document.body.classList.contains("shell-hide-bottom-nav")
);
console.log(`course talk hideBottomNav=${talkHidden} url=${page.url()}`);

// DM / notifications detail chrome still reachable
await page.goto(`${baseUrl}/app/notifications`, { waitUntil: "networkidle" });
await page.waitForSelector('[data-spa-page="通知"]', { timeout: 15000 });
console.log(`notifications -> ${page.url()}`);
await page.goto(`${baseUrl}/app/dm`, { waitUntil: "networkidle" });
await page.waitForSelector('[data-spa-page="メッセージ"]', { timeout: 15000 });
console.log(`dm -> ${page.url()}`);

// Timetable still navigable; keep-alive courses pane
await page.locator("nav.bottom-nav a.nav-item", { hasText: "時間割" }).click();
await page.waitForSelector('[data-spa-page="時間割"]', { timeout: 15000 });
await page.locator("nav.bottom-nav a.nav-item", { hasText: "授業" }).click();
await page.waitForSelector('[data-spa-page="授業"]', { timeout: 15000 });
await page.locator("nav.bottom-nav a.nav-item", { hasText: "ホーム" }).click();
await page.waitForSelector('[data-spa-page="タイムライン"]', { timeout: 15000 });
const coursesPane = await page.locator('[data-tab-pane="courses"]').count();
console.log(`keepalive courses pane mounted=${coursesPane > 0}`);
await page.screenshot({ path: join(shotDir, "05-home-nav.png") });

const report = {
  baseUrl,
  labels,
  offeringId,
  coursesPaneMounted: coursesPane > 0,
  courseDetailHeader: courseTitle,
  talkHideBottomNav: talkHidden,
};
writeFileSync(join(shotDir, "report.json"), JSON.stringify(report, null, 2));
await browser.close();
console.log(`OK django five-tab final. shots -> ${shotDir}`);
