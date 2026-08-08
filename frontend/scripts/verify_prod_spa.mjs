/**
 * Production soft-launch verification for React SPA on Render.
 *
 * Usage:
 *   node scripts/verify_prod_spa.mjs [baseUrl]
 *
 * Optional auth (for authenticated flows + poll cleanup):
 *   set WASE_E2E_EMAIL / WASE_E2E_PASSWORD
 *
 * Checks:
 * - /app/ shell boots with react_spa_enabled
 * - BottomNav / sidebar hops without extra document loads
 * - Profile / Flea / Community / DM hops when data exists
 * - 401 JSON → /app/login (not classic /login/)
 * - Chat poll cleanup via window.__WASE_ACTIVE_POLLS__
 */
import { chromium } from "playwright";

const baseUrl = (process.argv[2] || "https://wasewase.onrender.com").replace(
  /\/$/,
  ""
);
const spaUrl = `${baseUrl}/app/`;
const email = process.env.WASE_E2E_EMAIL || "";
const password = process.env.WASE_E2E_PASSWORD || "";

async function assertFrontendAssets() {
  for (const path of [
    "/static/frontend/assets/main.js",
    "/static/frontend/assets/main.css",
  ]) {
    const res = await fetch(`${baseUrl}${path}`);
    if (!res.ok) {
      throw new Error(`Missing SPA asset ${path} (HTTP ${res.status})`);
    }
    const ct = res.headers.get("content-type") || "";
    if (ct.includes("text/html")) {
      throw new Error(`SPA asset ${path} returned HTML instead of static file`);
    }
    console.log(`asset OK: ${path} (${ct || "no-content-type"})`);
  }
}

const findings = {
  spaVisible: false,
  reactSpaEnabled: false,
  checked: [],
  fullReloads: [],
  pollCleanup: "skipped",
  authChecked: [],
  problems: [],
};

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

function note(path) {
  findings.checked.push(path);
  console.log(`OK: ${path}`);
}

const browser = await launchBrowser();
const page = await browser.newPage();
await page.setViewportSize({ width: 390, height: 844 });

try {
  await assertFrontendAssets();
} catch (err) {
  findings.problems.push(String(err.message || err));
  console.error(err);
  await browser.close();
  console.log("\n=== SUMMARY ===");
  console.log(JSON.stringify(findings, null, 2));
  process.exit(1);
}

let loadCount = 0;
page.on("load", () => {
  loadCount += 1;
});

// Cold start (Render free tier may sleep)
await page.goto(spaUrl, { waitUntil: "domcontentloaded", timeout: 120000 });
try {
  await page.waitForSelector('[data-spa-page="ホーム"], [data-spa-page="ログイン"]', {
    timeout: 60000,
  });
} catch (err) {
  findings.problems.push(`SPA shell did not boot: ${err.message}`);
  console.error(await page.content().then((h) => h.slice(0, 500)));
  await browser.close();
  process.exit(1);
}

findings.spaVisible = true;
const me = await page.evaluate(async () => {
  const res = await fetch("/api/v1/me/", {
    credentials: "same-origin",
    headers: { Accept: "application/json" },
  });
  return { status: res.status, ...(await res.json()) };
});
findings.reactSpaEnabled = Boolean(me.react_spa_enabled);
console.log(`me: ${JSON.stringify(me)}`);
if (!me.react_spa_enabled) {
  findings.problems.push("react_spa_enabled is still false on production");
}

let baselineLoads = loadCount;

async function expectNoReload(label, fn) {
  const before = loadCount;
  await fn();
  const after = loadCount;
  if (after !== before) {
    findings.fullReloads.push(`${label} (loads ${before}->${after})`);
    console.error(`RELOAD: ${label}`);
  } else {
    note(label);
  }
}

// Mobile bottom nav hops
const tabs = [
  ["コミュニティ", "コミュニティ"],
  ["フリマ", "フリマ"],
  ["時間割", "時間割"],
  ["その他", "その他"],
  ["ホーム", "ホーム"],
];
for (const [label, heading] of tabs) {
  await expectNoReload(`bottomnav:${label}`, async () => {
    await page.locator("nav.bottom-nav a.nav-item", { hasText: label }).click();
    await page.waitForSelector(`[data-spa-page="${heading}"]`, {
      timeout: 20000,
    });
  });
}

// Flea detail if available
await page.locator("nav.bottom-nav a.nav-item", { hasText: "フリマ" }).click();
await page.waitForSelector('[data-spa-page="フリマ"]', { timeout: 20000 });
const product = page.locator("a.product-card").first();
if ((await product.count()) > 0) {
  await expectNoReload("flea:list→detail", async () => {
    await product.click();
    await page.waitForURL(/\/app\/flea\/products\/\d+/, { timeout: 20000 });
    await page.waitForSelector(".product-detail-page", { timeout: 20000 });
  });
  await expectNoReload("flea:detail→list", async () => {
    await page.locator("a.back-link", { hasText: "フリマへ戻る" }).click();
    await page.waitForSelector(".flea-page", { timeout: 20000 });
  });
} else {
  console.log("skip flea detail (empty)");
}

// Community thread if available
await page.locator("nav.bottom-nav a.nav-item", { hasText: "コミュニティ" }).click();
await page.waitForSelector('[data-spa-page="コミュニティ"]', { timeout: 20000 });
const thread = page.locator("a.community-thread-link, a.thread-card, .community-list a").first();
if ((await thread.count()) > 0) {
  await expectNoReload("community:list→thread", async () => {
    await thread.click();
    await page.waitForURL(/\/app\/communities\/.+\/threads\/\d+/, {
      timeout: 20000,
    });
  });
  await expectNoReload("community:thread→list", async () => {
    await page.locator("a.back-link, a.community-back").first().click();
    await page.waitForSelector('[data-spa-page="コミュニティ"]', {
      timeout: 20000,
    });
  });
} else {
  console.log("skip community thread (empty)");
}

// Timeline → Profile
await page.locator("nav.bottom-nav a.nav-item", { hasText: "ホーム" }).click();
await page.waitForSelector('[data-spa-page="ホーム"]', { timeout: 20000 });
const author = page.locator("a.tweet-author").first();
if ((await author.count()) > 0) {
  await expectNoReload("timeline→profile", async () => {
    await author.click();
    await page.waitForURL(/\/app\/users\/\d+/, { timeout: 20000 });
    await page.waitForSelector('[data-spa-page="プロフィール"]', {
      timeout: 20000,
    });
  });
  await expectNoReload("profile tabs", async () => {
    await page.locator("a.profile-tab", { hasText: "フリマ" }).click();
    await page.waitForURL(/\/app\/users\/\d+\/flea/, { timeout: 20000 });
    await page.locator("a.profile-tab", { hasText: "投稿" }).click();
    await page.waitForURL(/\/app\/users\/\d+\/posts/, { timeout: 20000 });
  });
} else {
  console.log("skip profile hop (no authors)");
}

// Desktop sidebar hops
await page.setViewportSize({ width: 1200, height: 800 });
await expectNoReload("sidebar:search", async () => {
  await page.locator('a.sidebar-nav__item', { hasText: "検索" }).click();
  await page.waitForSelector('[data-spa-page="検索"]', { timeout: 20000 });
});
await expectNoReload("sidebar:notifications-or-login", async () => {
  await page.locator('a.sidebar-nav__item', { hasText: "通知" }).click();
  await page.waitForTimeout(800);
  const url = page.url();
  if (!url.includes("/app/")) {
    findings.problems.push(`left /app/ after notifications: ${url}`);
  }
});

// 401 handling: hit protected API while logged out (if still logged out)
if (!me.authenticated) {
  const unauthorized = await page.evaluate(async () => {
    const res = await fetch("/api/v1/notifications/", {
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    });
    const ct = res.headers.get("content-type") || "";
    let body = null;
    try {
      body = await res.json();
    } catch {
      body = null;
    }
    return { status: res.status, ct, body, href: location.href };
  });
  console.log(`401 probe: ${JSON.stringify(unauthorized)}`);
  if (unauthorized.status !== 401 || !unauthorized.ct.includes("json")) {
    findings.problems.push(
      `expected JSON 401 from notifications API, got ${unauthorized.status} ${unauthorized.ct}`
    );
  } else {
    findings.authChecked.push("api-401-json");
  }
  // Wait briefly for UnauthorizedRedirect
  await page.waitForTimeout(500);
  if (page.url().includes("/app/login")) {
    findings.authChecked.push("401→/app/login");
    note("401→/app/login");
  } else {
    // Navigate login explicitly and confirm SPA login page
    await page.goto(`${baseUrl}/app/login`, { waitUntil: "domcontentloaded" });
    await page.waitForSelector('[data-spa-page="ログイン"], form', {
      timeout: 20000,
    });
    findings.authChecked.push("spa-login-page");
    baselineLoads = loadCount;
  }
}

// Authenticated flows
if (email && password) {
  if (!page.url().includes("/app/login")) {
    await page.goto(`${baseUrl}/app/login`, { waitUntil: "domcontentloaded" });
  }
  await page.waitForSelector('input[type="email"], input[name="email"]', {
    timeout: 20000,
  });
  await page.fill('input[type="email"], input[name="email"]', email);
  await page.fill('input[type="password"], input[name="password"]', password);
  await page.locator('button[type="submit"]').click();
  await page.waitForTimeout(2000);
  const afterLogin = page.url();
  if (afterLogin.includes("/app/login")) {
    findings.problems.push("login failed (still on /app/login)");
  } else if (!afterLogin.includes("/app")) {
    findings.fullReloads.push(`login redirect left SPA: ${afterLogin}`);
    findings.problems.push(`login left /app/: ${afterLogin}`);
  } else {
    findings.authChecked.push("login");
    note("login→spa");
    baselineLoads = loadCount;
  }

  // DM inbox + room poll cleanup
  await page.setViewportSize({ width: 390, height: 844 });
  const dmLink = page.locator("a.shell-header-dm, a[href*='/app/dm']").first();
  if ((await dmLink.count()) > 0) {
    await expectNoReload("dm:inbox", async () => {
      await dmLink.click();
      await page.waitForURL(/\/app\/dm/, { timeout: 20000 });
      await page.waitForSelector('[data-spa-page="メッセージ"]', {
        timeout: 20000,
      });
    });
    const room = page.locator("a.dm-inbox-item").first();
    if ((await room.count()) > 0) {
      await expectNoReload("dm:inbox→room", async () => {
        await room.click();
        await page.waitForURL(/\/app\/(dm\/\d+|dm\/groups\/\d+|flea\/chats\/\d+)/, {
          timeout: 20000,
        });
      });
      await page.waitForTimeout(500);
      const pollsOpen = await page.evaluate(
        () => window.__WASE_ACTIVE_POLLS__ || 0
      );
      console.log(`polls while in room: ${pollsOpen}`);
      await expectNoReload("dm:room→inbox", async () => {
        await page.locator("a.dm-back-text, a.back-link").first().click();
        await page.waitForTimeout(400);
      });
      const pollsAfter = await page.evaluate(
        () => window.__WASE_ACTIVE_POLLS__ || 0
      );
      console.log(`polls after leave: ${pollsAfter}`);
      if (pollsAfter > 0) {
        findings.problems.push(`poll leak after leave: ${pollsAfter}`);
        findings.pollCleanup = `FAIL leaks=${pollsAfter}`;
      } else {
        findings.pollCleanup = `OK (open=${pollsOpen}, after=0)`;
        findings.authChecked.push("dm-poll-cleanup");
      }
    } else {
      findings.pollCleanup = "skipped (empty inbox)";
    }
  }

  // Notifications SPA
  await page.setViewportSize({ width: 1200, height: 800 });
  await expectNoReload("notifications", async () => {
    await page.locator('a.sidebar-nav__item', { hasText: "通知" }).click();
    await page.waitForSelector('[data-spa-page="通知"]', { timeout: 20000 });
  });
  findings.authChecked.push("notifications");
} else {
  console.log("skip authenticated flows (set WASE_E2E_EMAIL / WASE_E2E_PASSWORD)");
}

await browser.close();

console.log("\n=== SUMMARY ===");
console.log(JSON.stringify(findings, null, 2));
console.log(`document loads total=${loadCount} (baseline after boot=${baselineLoads})`);

if (findings.problems.length || findings.fullReloads.length) {
  process.exit(1);
}
process.exit(0);
