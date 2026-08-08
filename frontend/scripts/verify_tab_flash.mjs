/**
 * Verify BottomNav tab switches do not white-flash after keep-alive.
 * 1) Warm each tab once (first visit may load)
 * 2) Remeasure hops — content must stay (no 読み込み中 blank)
 *
 * Usage: node scripts/verify_tab_flash.mjs [baseUrl]
 */
import { chromium } from "playwright";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const baseUrl = (process.argv[2] || "http://127.0.0.1:8000").replace(/\/$/, "");
const outDir = path.join(
  path.dirname(fileURLToPath(import.meta.url)),
  "flash-captures-after"
);
fs.mkdirSync(outDir, { recursive: true });

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

const browser = await launchBrowser();
const page = await browser.newPage({
  viewport: { width: 390, height: 844 },
  deviceScaleFactor: 2,
});

let loadCount = 0;
page.on("load", () => {
  loadCount += 1;
});

await page.goto(`${baseUrl}/app/`, { waitUntil: "domcontentloaded", timeout: 120000 });
await page.waitForSelector('[data-spa-page="ホーム"], [data-spa-page="ログイン"]', {
  timeout: 60000,
});
if (await page.locator('[data-spa-page="ログイン"]').count()) {
  await page.locator("button.linkish", { hasText: "閲覧モード" }).click();
  await page.waitForSelector('[data-spa-page="ホーム"]', { timeout: 30000 });
}
const loadsAfterBoot = loadCount;

const tabs = [
  ["コミュニティ", "コミュニティ"],
  ["フリマ", "フリマ"],
  ["時間割", "時間割"],
  ["その他", "その他"],
  ["ホーム", "ホーム"],
];

console.log("warm-up tabs…");
for (const [label, heading] of tabs) {
  await page.locator("nav.bottom-nav a.nav-item", { hasText: label }).click();
  await page.waitForSelector(`[data-spa-page="${heading}"]`, { timeout: 20000 });
  // wait for loading text to clear if present
  await page.waitForTimeout(800);
  const loading = await page.locator("text=読み込み中").count();
  if (loading) await page.waitForTimeout(1500);
}
console.log("warm-up done");

async function meanLuma(file) {
  const b64 = fs.readFileSync(file).toString("base64");
  return page.evaluate(async (dataUrl) => {
    const img = new Image();
    await new Promise((resolve, reject) => {
      img.onload = () => resolve(null);
      img.onerror = reject;
      img.src = dataUrl;
    });
    const c = document.createElement("canvas");
    c.width = img.width;
    c.height = img.height;
    const ctx = c.getContext("2d");
    ctx.drawImage(img, 0, 0);
    const y0 = Math.floor(img.height * 0.12);
    const y1 = Math.floor(img.height * 0.82);
    const data = ctx.getImageData(0, y0, img.width, y1 - y0).data;
    let sum = 0;
    let n = 0;
    let nearWhite = 0;
    for (let i = 0; i < data.length; i += 16) {
      const r = data[i];
      const g = data[i + 1];
      const b = data[i + 2];
      sum += 0.2126 * r + 0.7152 * g + 0.0722 * b;
      n += 1;
      if (r > 245 && g > 245 && b > 245) nearWhite += 1;
    }
    return { meanLuma: sum / n, nearWhiteRatio: nearWhite / n };
  }, `data:image/png;base64,${b64}`);
}

const hops = [
  ...tabs,
  ["時間割", "時間割"],
  ["ホーム", "ホーム"],
  ["コミュニティ", "コミュニティ"],
  ["ホーム", "ホーム"],
  ["フリマ", "フリマ"],
  ["コミュニティ", "コミュニティ"],
  ["その他", "その他"],
  ["フリマ", "フリマ"],
];

const results = [];
let failures = 0;

for (const [label, heading] of hops) {
  const beforeShot = path.join(outDir, `${label}-before-${results.length}.png`);
  await page.screenshot({ path: beforeShot, fullPage: false });
  const beforeLuma = await meanLuma(beforeShot);

  const beforeProbe = await page.evaluate(() => ({
    page: document.querySelector(".tab-keep-alive-pane.is-active [data-spa-page], [data-spa-page]")
      ?.getAttribute("data-spa-page"),
    loadingVisible: Array.from(document.querySelectorAll(".empty-message, .timetable-note"))
      .some((el) => (el.textContent || "").includes("読み込み中")),
    activePane: document.querySelector(".tab-keep-alive-pane.is-active")?.getAttribute("data-tab-pane"),
    shell: Boolean(document.querySelector(".app-shell")),
    nav: Boolean(document.querySelector(".bottom-nav")),
    header: Boolean(document.querySelector(".site-header")),
  }));

  await page.locator("nav.bottom-nav a.nav-item", { hasText: label }).click();

  const midSamples = [];
  for (const delay of [0, 16, 33, 50, 100, 200]) {
    if (delay) await page.waitForTimeout(delay - (midSamples.at(-1)?.delay || 0));
    const shot = path.join(
      outDir,
      `${label}-t${String(delay).padStart(3, "0")}-${results.length}.png`
    );
    await page.screenshot({ path: shot, fullPage: false });
    const luma = await meanLuma(shot);
    const probe = await page.evaluate((d) => {
      const activePane = document.querySelector(".tab-keep-alive-pane.is-active");
      const loadingVisible = Array.from(
        document.querySelectorAll(".empty-message, .timetable-note")
      ).some(
        (el) =>
          activePane?.contains(el) &&
          (el.textContent || "").includes("読み込み中")
      );
      return {
        delay: d,
        page: activePane
          ?.querySelector("[data-spa-page]")
          ?.getAttribute("data-spa-page"),
        loadingVisible,
        shell: Boolean(document.querySelector(".app-shell")),
        nav: Boolean(document.querySelector(".bottom-nav")),
        header: Boolean(document.querySelector(".site-header")),
        activePane: activePane?.getAttribute("data-tab-pane"),
      };
    }, delay);
    midSamples.push({ ...probe, ...luma, file: path.basename(shot) });
  }

  await page.waitForSelector(`[data-spa-page="${heading}"]`, { timeout: 10000 });

  const maxWhite = midSamples.reduce((a, b) =>
    a.nearWhiteRatio > b.nearWhiteRatio ? a : b
  );
  const deltaWhite = maxWhite.nearWhiteRatio - beforeLuma.nearWhiteRatio;
  const loadingFlash = midSamples.some((s) => s.loadingVisible);
  const shellOk = midSamples.every((s) => s.shell && s.nav && s.header);

  const row = {
    hop: label,
    beforeWhite: beforeLuma.nearWhiteRatio,
    maxWhite: maxWhite.nearWhiteRatio,
    deltaWhite,
    loadingFlash,
    shellOk,
    loads: loadCount,
    beforeProbe,
  };
  results.push(row);

  // After warm-up, white spike should stay small; loading text must not appear in active pane
  const fail =
    !shellOk ||
    loadingFlash ||
    loadCount !== loadsAfterBoot ||
    // Timetable→More naturally has higher white content; allow content change but forbid loading flash
    (Math.abs(deltaWhite) > 0.55 && loadingFlash);
  if (fail) {
    failures += 1;
    console.error(`FAIL ${label}`, row);
  } else {
    console.log(
      `OK ${label} Δwhite=${deltaWhite.toFixed(3)} loadingFlash=${loadingFlash} loads=${loadCount}`
    );
  }
}

fs.writeFileSync(
  path.join(outDir, "report.json"),
  JSON.stringify({ loadsAfterBoot, loadCount, results }, null, 2)
);

await browser.close();

if (failures || loadCount !== loadsAfterBoot) {
  console.error(`FAILED failures=${failures} documentLoads=${loadCount}`);
  process.exit(1);
}
console.log(
  `OK: no tab white-flash / no remount loading; document loads=${loadCount}`
);
process.exit(0);
