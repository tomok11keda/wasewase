/**
 * Smoke: SpaDiagSection only on Capacitor native; no_banner / clear work.
 * Usage: node scripts/verify_spa_diag_ui.mjs [baseUrl]
 */
import { chromium } from "playwright";

const baseUrl = (process.argv[2] || "http://127.0.0.1:8000").replace(/\/$/, "");

async function launchBrowser() {
  for (const channel of [
    process.env.PLAYWRIGHT_CHANNEL,
    "chrome",
    "msedge",
    undefined,
  ]) {
    try {
      return await chromium.launch({
        headless: true,
        ...(channel ? { channel } : {}),
      });
    } catch {
      /* next */
    }
  }
  throw new Error("no browser");
}

async function openMore(page) {
  await page.goto(`${baseUrl}/app/more`, {
    waitUntil: "domcontentloaded",
    timeout: 120000,
  });
  // Avoid embedding Japanese literals (Windows shell encoding).
  await page.waitForFunction(
    () =>
      Boolean(
        document.querySelector('[data-spa-page]') ||
          document.querySelector("#root")?.textContent
      ),
    { timeout: 60000 }
  );
  const loginBtn = page.locator("button.linkish", { hasText: "閲覧モード" });
  if (await loginBtn.count()) {
    await loginBtn.click();
    await page.goto(`${baseUrl}/app/more`, {
      waitUntil: "domcontentloaded",
      timeout: 60000,
    });
    await page.waitForSelector(".spa-diag-section, .more-page, .page-title", {
      timeout: 30000,
    });
  }
}

const browser = await launchBrowser();

const web = await browser.newPage({ viewport: { width: 390, height: 844 } });
await openMore(web);
const webDiag = await web.locator(".spa-diag-section").count();
if (webDiag !== 0) {
  throw new Error(`Web must hide diag UI, found ${webDiag}`);
}
console.log("OK web: diag UI hidden");

const nativeCtx = await browser.newContext();
const native = await nativeCtx.newPage({
  viewport: { width: 390, height: 844 },
});
await native.addInitScript(() => {
  window.Capacitor = {
    isNativePlatform: () => true,
    getPlatform: () => "ios",
    getPlugin: () => null,
    Plugins: {},
  };
  try {
    sessionStorage.setItem("wase_splash_done", "1");
  } catch {
    /* ignore */
  }
});
await openMore(native);
const nativeDiag = await native.locator(".spa-diag-section").count();
if (nativeDiag !== 1) {
  throw new Error(`Native must show diag UI once, found ${nativeDiag}`);
}
console.log("OK native: diag UI visible");

await native.locator(".spa-diag-section button", { hasText: "no_banner" }).click();
await native.waitForURL(/spa_nav_diag=no_banner/, { timeout: 15000 });
const afterBanner = await native.evaluate(() => ({
  url: location.href,
  nav: localStorage.getItem("wase_spa_nav_diag"),
  flash: localStorage.getItem("wase_flash_diag"),
}));
if (afterBanner.nav !== "no_banner" || afterBanner.flash !== "1") {
  throw new Error(`no_banner not applied: ${JSON.stringify(afterBanner)}`);
}
if (!afterBanner.url.includes("spa_flash_diag=1")) {
  throw new Error(`flash query missing: ${afterBanner.url}`);
}
console.log("OK no_banner applied", afterBanner);

await openMore(native);
await native.locator(".spa-diag-section button", { hasText: "Clear" }).click();
await native.waitForURL(/spa_nav_diag=clear/, { timeout: 15000 });
const afterClear = await native.evaluate(() => ({
  url: location.href,
  nav: localStorage.getItem("wase_spa_nav_diag"),
  flash: localStorage.getItem("wase_flash_diag"),
}));
if (afterClear.nav) {
  throw new Error(`clear left nav key: ${JSON.stringify(afterClear)}`);
}
if (afterClear.flash) {
  throw new Error(`clear left flash key: ${JSON.stringify(afterClear)}`);
}
console.log("OK clear restored", afterClear);

await browser.close();
console.log("OK: spa diag UI checks passed");
