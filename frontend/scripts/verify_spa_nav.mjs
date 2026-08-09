/**
 * Verify React Router tab switches do not trigger full document reloads.
 * Requires: Django runserver with WASE_REACT_SPA=True, BROWSE_MODE_GATE_ENABLED=False
 * Usage (from frontend/): node scripts/verify_spa_nav.mjs [baseUrl]
 */
import { chromium } from "playwright";

const baseUrl = (process.argv[2] || "http://127.0.0.1:8000").replace(/\/$/, "");
const spaUrl = `${baseUrl}/app/`;

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

await page.goto(spaUrl, { waitUntil: "networkidle" });
await page.waitForSelector('[data-spa-page="タイムライン"]', { timeout: 15000 });
let loadsAfterFirst = loadCount;

const tabs = [
  { label: "コミュニティ", heading: "コミュニティ" },
  { label: "フリマ", heading: "フリマ" },
  { label: "時間割", heading: "時間割" },
  { label: "タイムライン", heading: "タイムライン" },
];

for (const tab of tabs) {
  await page.locator("nav.bottom-nav a.nav-item", { hasText: tab.label }).click();
  await page.waitForSelector(`[data-spa-page="${tab.heading}"]`, {
    timeout: 10000,
  });
  console.log(`navigated -> ${page.url()}`);
}

await page.locator("nav.bottom-nav a.nav-item", { hasText: "時間割" }).click();
await page.waitForSelector(".timetable-page .timetable-grid", { timeout: 10000 });
console.log(`timetable grid -> ${page.url()}`);

await page.locator("nav.bottom-nav a.nav-item", { hasText: "フリマ" }).click();
await page.waitForSelector('[data-spa-page="フリマ"]', { timeout: 10000 });
const productLink = page.locator("a.product-card").first();
if ((await productLink.count()) > 0) {
  await productLink.click();
  await page.waitForURL(/\/app\/flea\/products\/\d+/, { timeout: 10000 });
  await page.waitForSelector(".product-detail-page", { timeout: 10000 });
  console.log(`navigated flea detail -> ${page.url()}`);
  await page.locator("a.back-link", { hasText: "フリマへ戻る" }).click();
  await page.waitForSelector(".flea-page", { timeout: 10000 });
  console.log(`navigated flea list back -> ${page.url()}`);
} else {
  console.log("skip flea detail: no products in list");
}

await page.locator("nav.bottom-nav a.nav-item", { hasText: "タイムライン" }).click();
await page.waitForSelector('[data-spa-page="タイムライン"]', { timeout: 10000 });
const authorLink = page.locator("a.tweet-author").first();
if ((await authorLink.count()) > 0) {
  await authorLink.click();
  await page.waitForURL(/\/app\/users\/\d+/, { timeout: 10000 });
  await page.waitForSelector('[data-spa-page="プロフィール"]', { timeout: 10000 });
  console.log(`navigated profile -> ${page.url()}`);
  await page.locator("a.profile-tab", { hasText: "フリマ" }).click();
  await page.waitForURL(/\/app\/users\/\d+\/flea/, { timeout: 10000 });
  console.log(`profile flea tab -> ${page.url()}`);
  await page.locator("a.profile-tab", { hasText: "投稿" }).click();
  await page.waitForURL(/\/app\/users\/\d+\/posts/, { timeout: 10000 });
  console.log(`profile posts tab -> ${page.url()}`);
  await page.locator("a.profile-back").click();
  await page.waitForSelector('[data-spa-page="タイムライン"]', { timeout: 10000 });
  console.log(`back home -> ${page.url()}`);
} else {
  console.log("skip profile hop: no timeline authors");
}

// Desktop sidebar search NavLink (no full reload)
await page.setViewportSize({ width: 1200, height: 800 });
await page.locator('a.sidebar-nav__item', { hasText: "検索" }).click();
await page.waitForSelector('[data-spa-page="検索"]', { timeout: 10000 });
console.log(`search -> ${page.url()}`);
await page.locator('a.sidebar-nav__item', { hasText: "タイムライン" }).click();
await page.waitForSelector('[data-spa-page="タイムライン"]', { timeout: 10000 });
console.log(`search back home -> ${page.url()}`);

// P1-1 / P1-3: Sidebar compose must stay in SPA (no full reload)
const composeCtl = page.locator(".sidebar-nav__compose").first();
if ((await composeCtl.count()) > 0) {
  await composeCtl.click();
  await page.waitForTimeout(500);
  const afterCompose = page.url();
  if (!afterCompose.includes("/app/")) {
    console.error(`FAIL: left /app/ after compose click (${afterCompose})`);
    process.exit(1);
  }
  console.log(`sidebar compose -> ${afterCompose}`);
  if (afterCompose.includes("/app/login")) {
    console.log("compose redirected to SPA login (unauthenticated) — OK");
    await page.goto(spaUrl, { waitUntil: "networkidle" });
    await page.waitForSelector('[data-spa-page="タイムライン"]', { timeout: 15000 });
    // Returning to /app via goto counts as an expected load; reset baseline.
    loadsAfterFirst = loadCount;
  } else {
    await page.locator('a.sidebar-nav__item', { hasText: "検索" }).click();
    await page.waitForSelector('[data-spa-page="検索"]', { timeout: 10000 });
    console.log(`compose hop search -> ${page.url()}`);
  }
}

// Phase 9: notifications + login SPA links (no full reload when already in SPA)
await page.setViewportSize({ width: 1200, height: 800 });
await page.locator('a.sidebar-nav__item', { hasText: "通知" }).click();
// May redirect to login if unauthenticated — still SPA route under /app/
await page.waitForTimeout(800);
const afterNotify = page.url();
console.log(`notifications/login hop -> ${afterNotify}`);
if (!afterNotify.includes("/app/")) {
  console.error(`FAIL: left /app/ after notifications click (${afterNotify})`);
  process.exit(1);
}

if (afterNotify.includes("/app/login")) {
  console.log("on SPA login (unauthenticated) — OK");
  await page.locator('a', { hasText: "新規登録" }).first().click();
  await page.waitForURL(/\/app\/signup/, { timeout: 10000 });
  console.log(`signup -> ${page.url()}`);
  await page.locator('a', { hasText: "ログイン" }).first().click();
  await page.waitForURL(/\/app\/login/, { timeout: 10000 });
  console.log(`login back -> ${page.url()}`);
} else {
  await page.waitForSelector('[data-spa-page="通知"]', { timeout: 10000 });
  console.log(`notifications page -> ${page.url()}`);
}

// Phase 8: header DM link is SPA (no full reload) when authenticated.
await page.setViewportSize({ width: 390, height: 844 });
const meRes = await page.evaluate(async () => {
  const res = await fetch("/api/v1/me/", {
    credentials: "same-origin",
    headers: { Accept: "application/json" },
  });
  return res.json();
});
if (meRes?.authenticated) {
  await page.locator("a.shell-header-dm").click();
  await page.waitForURL(/\/app\/dm\/?$/, { timeout: 10000 });
  await page.waitForSelector('[data-spa-page="メッセージ"]', { timeout: 10000 });
  console.log(`dm inbox -> ${page.url()}`);

  const roomLink = page.locator("a.dm-inbox-item").first();
  if ((await roomLink.count()) > 0) {
    await roomLink.click();
    await page.waitForURL(/\/app\/(dm\/\d+|dm\/groups\/\d+|flea\/chats\/\d+)/, {
      timeout: 10000,
    });
    console.log(`dm/group/trade room -> ${page.url()}`);
    await page.waitForTimeout(200);
    const pollsWhileOpen = await page.evaluate(
      () => window.__WASE_ACTIVE_POLLS__ || 0
    );
    console.log(`active polls while in room: ${pollsWhileOpen}`);
    await page.locator("a.dm-back-text, a.back-link").first().click();
    await page.waitForTimeout(300);
    const pollsAfterLeave = await page.evaluate(
      () => window.__WASE_ACTIVE_POLLS__ || 0
    );
    console.log(`active polls after leave: ${pollsAfterLeave}`);
    if (pollsAfterLeave > 0) {
      console.error(
        `FAIL: poll leak after leaving chat (polls=${pollsAfterLeave})`
      );
      process.exit(1);
    }
  } else {
    console.log("skip dm room hop: inbox empty");
    const pollsIdle = await page.evaluate(
      () => window.__WASE_ACTIVE_POLLS__ || 0
    );
    if (pollsIdle > 0) {
      console.error(`FAIL: unexpected active polls on inbox (${pollsIdle})`);
      process.exit(1);
    }
  }
} else {
  console.log("skip dm SPA hops: not authenticated");
}

const loadsAfterNav = loadCount;
await browser.close();

if (loadsAfterNav !== loadsAfterFirst) {
  console.error(
    `FAIL: full page load fired during SPA nav (before=${loadsAfterFirst}, after=${loadsAfterNav})`
  );
  process.exit(1);
}

console.log(
  `OK: SPA navigation without full reload (document load events=${loadsAfterFirst})`
);
process.exit(0);
