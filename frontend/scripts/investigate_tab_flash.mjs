/**
 * Investigate white flash on BottomNav tab switches (read-only diagnostics).
 * Usage: node scripts/investigate_tab_flash.mjs [baseUrl]
 */
import { chromium } from "playwright";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const baseUrl = (process.argv[2] || "https://wasewase.onrender.com").replace(
  /\/$/,
  ""
);
const outDir = path.join(
  path.dirname(fileURLToPath(import.meta.url)),
  "flash-captures"
);
fs.mkdirSync(outDir, { recursive: true });

async function launchBrowser() {
  for (const channel of [process.env.PLAYWRIGHT_CHANNEL, "chrome", "msedge", undefined]) {
    try {
      return await chromium.launch({
        headless: true,
        ...(channel ? { channel } : {}),
      });
    } catch {
      /* try next */
    }
  }
  throw new Error("no browser");
}

function avgLuma(buf) {
  // PNG via playwright screenshot is raw; use evaluate on canvas instead.
  return null;
}

const browser = await launchBrowser();
const page = await browser.newPage({
  viewport: { width: 390, height: 844 },
  deviceScaleFactor: 2,
});

await page.addInitScript(() => {
  window.__WASE_FLASH_DIAG__ = {
    shellMounts: 0,
    outletSwaps: 0,
    rootChildCounts: [],
    bgSamples: [],
  };
});

await page.goto(`${baseUrl}/app/`, { waitUntil: "domcontentloaded", timeout: 120000 });
await page.waitForSelector('[data-spa-page="ホーム"], [data-spa-page="ログイン"]', {
  timeout: 60000,
});
if (await page.locator('[data-spa-page="ログイン"]').count()) {
  await page.locator("button.linkish", { hasText: "閲覧モード" }).click();
  await page.waitForSelector('[data-spa-page="ホーム"]', { timeout: 30000 });
}

// Instrument DOM for remount / emptiness
await page.evaluate(() => {
  const diag = window.__WASE_FLASH_DIAG__;
  const root = document.getElementById("root");
  const noteBg = (label) => {
    const body = getComputedStyle(document.body).backgroundColor;
    const html = getComputedStyle(document.documentElement).backgroundColor;
    const rootEl = root ? getComputedStyle(root).backgroundColor : "n/a";
    const shell = document.querySelector(".app-shell");
    const main = document.querySelector(".main-column");
    const outlet = document.querySelector("[data-spa-page]");
    diag.bgSamples.push({
      label,
      t: performance.now(),
      html,
      body,
      root: rootEl,
      shell: shell ? getComputedStyle(shell).backgroundColor : null,
      main: main ? getComputedStyle(main).backgroundColor : null,
      page: outlet ? getComputedStyle(outlet).backgroundColor : null,
      pageAttr: outlet?.getAttribute("data-spa-page") || null,
      mainHTMLLen: main ? main.innerHTML.length : 0,
      rootChildren: root ? root.childElementCount : 0,
    });
  };

  // Count AppShell remounts via MutationObserver on .app-shell presence
  let hadShell = Boolean(document.querySelector(".app-shell"));
  const mo = new MutationObserver(() => {
    const hasShell = Boolean(document.querySelector(".app-shell"));
    if (hasShell && !hadShell) diag.shellMounts += 1;
    hadShell = hasShell;
    const pageEl = document.querySelector("[data-spa-page]");
    if (pageEl) diag.outletSwaps += 1;
    noteBg("mutation");
  });
  mo.observe(document.getElementById("root"), {
    childList: true,
    subtree: true,
  });
  window.__WASE_FLASH_MO__ = mo;
  noteBg("baseline");
});

const hops = [
  ["コミュニティ", "コミュニティ"],
  ["フリマ", "フリマ"],
  ["時間割", "時間割"],
  ["その他", "その他"],
  ["ホーム", "ホーム"],
];

const flashReports = [];

for (const [label, heading] of hops) {
  const samples = [];
  const before = await page.evaluate(() => {
    const diag = window.__WASE_FLASH_DIAG__;
    const main = document.querySelector(".main-column");
    return {
      shellMounts: diag.shellMounts,
      page: document.querySelector("[data-spa-page]")?.getAttribute("data-spa-page"),
      mainLen: main ? main.innerHTML.length : 0,
      bodyBg: getComputedStyle(document.body).backgroundColor,
      mainBg: main ? getComputedStyle(main).backgroundColor : null,
    };
  });

  await page.screenshot({
    path: path.join(outDir, `${label}-0-before.png`),
    fullPage: false,
  });

  await page
    .locator("nav.bottom-nav a.nav-item", { hasText: label })
    .click();

  // Burst screenshots + DOM probes right after click (sequential for timing accuracy)
  for (const delay of [0, 16, 33, 50, 83, 116, 150, 200, 300, 500]) {
    if (delay > 0) await page.waitForTimeout(delay - (samples.at(-1)?.delay || 0));
    const shot = path.join(outDir, `${label}-t${String(delay).padStart(3, "0")}.png`);
    await page.screenshot({ path: shot, fullPage: false });
    const probe = await page.evaluate((d) => {
      const main = document.querySelector(".main-column");
      const pageEl = document.querySelector("[data-spa-page]");
      return {
        delay: d,
        page: pageEl?.getAttribute("data-spa-page") || null,
        mainLen: main ? main.innerHTML.length : 0,
        bodyBg: getComputedStyle(document.body).backgroundColor,
        mainBg: main ? getComputedStyle(main).backgroundColor : null,
        rootBg: getComputedStyle(document.getElementById("root")).backgroundColor,
        shellExists: Boolean(document.querySelector(".app-shell")),
        bottomNavExists: Boolean(document.querySelector(".bottom-nav")),
        headerExists: Boolean(document.querySelector(".site-header")),
      };
    }, delay);
    samples.push(probe);
  }
  await page.waitForSelector(`[data-spa-page="${heading}"]`, { timeout: 20000 });
  await page.waitForTimeout(200);

  const after = await page.evaluate(() => {
    const diag = window.__WASE_FLASH_DIAG__;
    const main = document.querySelector(".main-column");
    return {
      shellMounts: diag.shellMounts,
      page: document.querySelector("[data-spa-page]")?.getAttribute("data-spa-page"),
      mainLen: main ? main.innerHTML.length : 0,
      bodyBg: getComputedStyle(document.body).backgroundColor,
      mainBg: main ? getComputedStyle(main).backgroundColor : null,
    };
  });

  await page.screenshot({
    path: path.join(outDir, `${label}-z-after.png`),
    fullPage: false,
  });

  // Analyze PNG brightness for mid-burst frames via page canvas read of screenshots is hard;
  // instead compare mainLen dips (content emptiness proxy)
  const minMainLen = Math.min(...samples.map((s) => s.mainLen));
  const emptyish = samples.filter((s) => s.mainLen < before.mainLen * 0.35);
  flashReports.push({
    hop: label,
    before,
    after,
    shellRemounted: after.shellMounts > before.shellMounts,
    minMainLen,
    beforeMainLen: before.mainLen,
    emptinessDips: emptyish.length,
    samples: samples.sort((a, b) => a.delay - b.delay),
  });
  console.log(
    `hop=${label} shellRemount=${after.shellMounts > before.shellMounts} mainLen ${before.mainLen}->min${minMainLen}->${after.mainLen} emptyDips=${emptyish.length}`
  );
}

// Pixel luminance analysis of captured PNGs (Node buffer)
async function meanLuma(file) {
  // Use sharp if unavailable — decode via playwright page
  const b64 = fs.readFileSync(file).toString("base64");
  return page.evaluate(async (dataUrl) => {
    const img = new Image();
    const done = new Promise((resolve, reject) => {
      img.onload = () => resolve(null);
      img.onerror = reject;
    });
    img.src = dataUrl;
    await done;
    const c = document.createElement("canvas");
    c.width = img.width;
    c.height = img.height;
    const ctx = c.getContext("2d");
    ctx.drawImage(img, 0, 0);
    // Sample center content band (below header ~80px, above bottom nav ~120px)
    const y0 = Math.floor(img.height * 0.12);
    const y1 = Math.floor(img.height * 0.82);
    const data = ctx.getImageData(0, y0, img.width, y1 - y0).data;
    let sum = 0;
    let n = 0;
    let nearWhite = 0;
    for (let i = 0; i < data.length; i += 16) {
      // subsample every 4th pixel
      const r = data[i];
      const g = data[i + 1];
      const b = data[i + 2];
      const luma = 0.2126 * r + 0.7152 * g + 0.0722 * b;
      sum += luma;
      n += 1;
      if (r > 245 && g > 245 && b > 245) nearWhite += 1;
    }
    return {
      meanLuma: sum / n,
      nearWhiteRatio: nearWhite / n,
    };
  }, `data:image/png;base64,${b64}`);
}

const lumaReport = [];
for (const [label] of hops) {
  const files = fs
    .readdirSync(outDir)
    .filter((f) => f.startsWith(`${label}-`))
    .sort();
  const row = { hop: label, frames: [] };
  for (const f of files) {
    const metrics = await meanLuma(path.join(outDir, f));
    row.frames.push({ file: f, ...metrics });
  }
  // Detect spike: frame meanLuma much higher than before, or nearWhiteRatio jump
  const before = row.frames.find((f) => f.file.includes("-0-before"));
  const mids = row.frames.filter((f) => f.file.includes("-t"));
  if (before && mids.length) {
    const maxWhite = mids.reduce((a, b) =>
      a.nearWhiteRatio > b.nearWhiteRatio ? a : b
    );
    const maxLuma = mids.reduce((a, b) => (a.meanLuma > b.meanLuma ? a : b));
    row.spike = {
      maxNearWhite: maxWhite,
      maxLuma,
      deltaWhite: maxWhite.nearWhiteRatio - before.nearWhiteRatio,
      deltaLuma: maxLuma.meanLuma - before.meanLuma,
    };
  }
  lumaReport.push(row);
  console.log(
    `luma ${label}: beforeWhite=${before?.nearWhiteRatio?.toFixed(3)} spikeWhite=${row.spike?.maxNearWhite?.nearWhiteRatio?.toFixed(3)} delta=${row.spike?.deltaWhite?.toFixed(3)} file=${row.spike?.maxNearWhite?.file}`
  );
}

const summary = {
  flashReports,
  lumaReport: lumaReport.map((r) => ({
    hop: r.hop,
    spike: r.spike,
    frames: r.frames,
  })),
  outDir,
};

fs.writeFileSync(
  path.join(outDir, "report.json"),
  JSON.stringify(summary, null, 2)
);
console.log("\n=== DONE ===");
console.log(`captures: ${outDir}`);
await browser.close();
