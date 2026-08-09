/**
 * Measure tab-switch luminance jumps (not just loadingFlash).
 * After warm-up, each hop samples frames across the crossfade window
 * and reports max frame-to-frame Δluma / near-white.
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
  "flash-captures-luma"
);
fs.mkdirSync(outDir, { recursive: true });

/** Must cover TAB_CROSSFADE_MS (220) */
const SAMPLE_MS = [0, 16, 33, 50, 80, 120, 160, 200, 240, 300];

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

await page.goto(`${baseUrl}/app/`, {
  waitUntil: "domcontentloaded",
  timeout: 120000,
});
await page.waitForSelector(
  '[data-spa-page="タイムライン"], [data-spa-page="ログイン"]',
  { timeout: 60000 }
);
if (await page.locator('[data-spa-page="ログイン"]').count()) {
  await page.locator("button.linkish", { hasText: "閲覧モード" }).click();
  await page.waitForSelector('[data-spa-page="タイムライン"]', { timeout: 30000 });
}
const loadsAfterBoot = loadCount;

const tabs = [
  ["コミュニティ", "コミュニティ"],
  ["フリマ", "フリマ"],
  ["時間割", "時間割"],
  ["タイムライン", "タイムライン"],
];

console.log("warm-up…");
for (const [label, heading] of tabs) {
  await page.locator("nav.bottom-nav a.nav-item", { hasText: label }).click();
  await page.waitForSelector(`[data-spa-page="${heading}"]`, { timeout: 20000 });
  await page.waitForTimeout(600);
}
console.log("warm-up done");

async function sampleViewport() {
  return page.evaluate(() => {
    // Draw current viewport via screenshot is external; here read DOM metrics
    // plus a canvas sample of the main column if available is hard without bitmap.
    // Caller uses page.screenshot + this for structural probes.
    const stack = document.querySelector(".tab-keep-alive-stack");
    const active = document.querySelector(".tab-keep-alive-pane.is-active");
    const leaving = document.querySelector(".tab-keep-alive-pane.is-leaving");
    const loadingVisible = Array.from(
      document.querySelectorAll(".empty-message, .timetable-note")
    ).some(
      (el) =>
        active?.contains(el) && (el.textContent || "").includes("読み込み中")
    );
    return {
      activeTab: active?.getAttribute("data-tab-pane"),
      leavingTab: leaving?.getAttribute("data-tab-pane"),
      activeOpacity: active ? getComputedStyle(active).opacity : null,
      leavingOpacity: leaving ? getComputedStyle(leaving).opacity : null,
      stackBg: stack ? getComputedStyle(stack).backgroundColor : null,
      bodyBg: getComputedStyle(document.body).backgroundColor,
      rootBg: getComputedStyle(document.documentElement).backgroundColor,
      loadingVisible,
      shell: Boolean(document.querySelector(".app-shell")),
      nav: Boolean(document.querySelector(".bottom-nav")),
      header: Boolean(document.querySelector(".site-header")),
      displayNoneActive: active
        ? getComputedStyle(active).display === "none"
        : null,
    };
  });
}

async function lumaFromFile(file) {
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
    // Content band below header / above bottom nav
    const y0 = Math.floor(img.height * 0.12);
    const y1 = Math.floor(img.height * 0.82);
    const data = ctx.getImageData(0, y0, img.width, y1 - y0).data;
    let sum = 0;
    let n = 0;
    let nearWhite = 0;
    let maxLuma = 0;
    for (let i = 0; i < data.length; i += 16) {
      const r = data[i];
      const g = data[i + 1];
      const b = data[i + 2];
      const luma = 0.2126 * r + 0.7152 * g + 0.0722 * b;
      sum += luma;
      n += 1;
      if (luma > maxLuma) maxLuma = luma;
      if (r > 245 && g > 245 && b > 245) nearWhite += 1;
    }
    return {
      meanLuma: sum / n,
      maxLuma,
      nearWhiteRatio: nearWhite / n,
    };
  }, `data:image/png;base64,${b64}`);
}

const hops = [
  ...tabs,
  ["時間割", "時間割"],
  ["タイムライン", "タイムライン"],
  ["時間割", "時間割"],
  ["タイムライン", "タイムライン"],
  ["フリマ", "フリマ"],
  ["タイムライン", "タイムライン"],
];

const results = [];
let failures = 0;

for (const [label, heading] of hops) {
  const idx = results.length;
  const beforePath = path.join(outDir, `${idx}-${label}-before.png`);
  await page.screenshot({ path: beforePath, fullPage: false });
  const beforeLuma = await lumaFromFile(beforePath);
  const beforeProbe = await sampleViewport();

  await page.locator("nav.bottom-nav a.nav-item", { hasText: label }).click();

  const frames = [];
  let lastDelay = 0;
  for (const delay of SAMPLE_MS) {
    if (delay > lastDelay) await page.waitForTimeout(delay - lastDelay);
    lastDelay = delay;
    const shot = path.join(
      outDir,
      `${idx}-${label}-t${String(delay).padStart(3, "0")}.png`
    );
    await page.screenshot({ path: shot, fullPage: false });
    const luma = await lumaFromFile(shot);
    const probe = await sampleViewport();
    frames.push({ delay, ...luma, ...probe, file: path.basename(shot) });
  }

  await page.waitForSelector(`[data-spa-page="${heading}"]`, { timeout: 10000 });

  // Frame-to-frame jumps
  let maxStepLuma = 0;
  let maxStepWhite = 0;
  for (let i = 1; i < frames.length; i++) {
    maxStepLuma = Math.max(
      maxStepLuma,
      Math.abs(frames[i].meanLuma - frames[i - 1].meanLuma)
    );
    maxStepWhite = Math.max(
      maxStepWhite,
      Math.abs(frames[i].nearWhiteRatio - frames[i - 1].nearWhiteRatio)
    );
  }
  // Also compare each frame vs before
  let maxJumpFromBefore = 0;
  for (const f of frames) {
    maxJumpFromBefore = Math.max(
      maxJumpFromBefore,
      Math.abs(f.meanLuma - beforeLuma.meanLuma)
    );
  }

  const loadingFlash = frames.some((f) => f.loadingVisible);
  const usedDisplayNone = frames.some((f) => f.displayNoneActive === true);
  const shellOk = frames.every((f) => f.shell && f.nav && f.header);
  const sawLeaving = frames.some((f) => Boolean(f.leavingTab));
  const opacityMid = frames.find((f) => f.delay === 80 || f.delay === 120);

  const row = {
    hop: label,
    beforeMean: beforeLuma.meanLuma,
    beforeWhite: beforeLuma.nearWhiteRatio,
    maxStepLuma,
    maxStepWhite,
    maxJumpFromBefore,
    loadingFlash,
    usedDisplayNone,
    shellOk,
    sawLeaving,
    midOpacity: opacityMid
      ? { active: opacityMid.activeOpacity, leaving: opacityMid.leavingOpacity }
      : null,
    loads: loadCount,
  };
  results.push(row);

  // Thresholds: allow content brightness change, forbid sudden spikes & loading blanks
  // meanLuma is 0-255; step > 40 in one ~16-50ms frame is a "ピカッ"
  const fail =
    !shellOk ||
    loadingFlash ||
    usedDisplayNone ||
    loadCount !== loadsAfterBoot ||
    maxStepLuma > 42;

  if (fail) {
    failures += 1;
    console.error(`FAIL ${label}`, JSON.stringify(row));
  } else {
    console.log(
      `OK ${label} stepLuma=${maxStepLuma.toFixed(1)} jump=${maxJumpFromBefore.toFixed(1)} leaving=${sawLeaving} mid=${JSON.stringify(row.midOpacity)}`
    );
  }
}

fs.writeFileSync(
  path.join(outDir, "report.json"),
  JSON.stringify({ loadsAfterBoot, loadCount, results }, null, 2)
);

await browser.close();

if (failures) {
  console.error(`FAILED count=${failures} documentLoads=${loadCount}`);
  process.exit(1);
}
console.log(
  `OK: luminance steps controlled; document loads=${loadCount}; captures=${outDir}`
);
process.exit(0);
