/**
 * Automated flash-cause isolation across spa_nav_diag modes.
 *
 * Compares JS (and mocked Capacitor) event timelines per mode.
 * Does NOT change production behavior — only observes with spa_flash_diag=1.
 *
 * Constraint: this Windows host cannot run iOS Simulator. Visual "ピカッ"
 * on TestFlight cannot be auto-detected here. The script ranks causes by
 * which native-bridge / AdMob / React events disappear in each mode.
 *
 * Usage:
 *   node scripts/verify_flash_diag.mjs [baseUrl]
 *
 * Writes:
 *   scripts/flash-diag-report.json
 *   scripts/flash-diag-report.md
 */
import { chromium } from "playwright";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const baseUrl = (process.argv[2] || "http://127.0.0.1:8000").replace(/\/$/, "");
const __dirname = path.dirname(fileURLToPath(import.meta.url));
const outJson = path.join(__dirname, "flash-diag-report.json");
const outMd = path.join(__dirname, "flash-diag-report.md");

const MODES = [
  { id: "normal", spaNavDiag: "" },
  { id: "no_banner", spaNavDiag: "no_banner" },
  { id: "no_bridge", spaNavDiag: "no_bridge" },
  { id: "no_analytics", spaNavDiag: "no_analytics" },
  { id: "no_keepalive", spaNavDiag: "no_keepalive" },
  { id: "no_transition", spaNavDiag: "no_transition" },
];

const TAB_HOPS = [
  ["コミュニティ", "コミュニティ"],
  ["フリマ", "フリマ"],
  ["時間割", "時間割"],
  ["ホーム", "ホーム"],
];

const SIGNAL_EVENTS = [
  "notify_spa_navigation",
  "schedule_banner_reposition",
  "schedule_banner_reposition_fire",
  "schedule_banner_reposition_skipped",
  "reposition_inline_banner",
  "admob_show_banner",
  "admob_remove_banner",
  "analytics_track_page_view",
  "native_spa_bridge_run",
  "native_spa_bridge_skipped",
  "tab_transition_start",
  "tab_transition_end",
  "tab_transition_instant",
  "keepalive_pane_mount",
];

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

function modeUrl(mode) {
  const params = new URLSearchParams();
  params.set("spa_flash_diag", "1");
  if (mode.spaNavDiag) {
    params.set("spa_nav_diag", mode.spaNavDiag);
  } else {
    params.set("spa_nav_diag", "clear");
  }
  return `${baseUrl}/app/?${params.toString()}`;
}

async function installCapacitorMock(page) {
  await page.addInitScript(() => {
    try {
      sessionStorage.setItem("wase_splash_done", "1");
    } catch {
      /* ignore */
    }
    window.WASE_FLASH_DIAG_FORCE = true;
    const admobCalls = [];
    const flashNative = {
      events: [],
      async beginTrace(opts) {
        this.events.push({ type: "native_beginTrace", opts });
        return { traceId: opts?.traceId || "mock", sampling: true };
      },
      async endTrace(opts) {
        this.events.push({ type: "native_endTrace", opts });
        return { events: this.events.slice(), eventCount: this.events.length };
      },
      async drainNativeEvents() {
        const events = this.events.slice();
        this.events = [];
        return { events };
      },
      async snapshot(opts) {
        const snap = {
          reason: opts?.reason || "snapshot",
          mock: true,
          animationsEnabled: true,
          window: {
            class: "UIWindow",
            backgroundColor: "rgba(0.537,0.118,0.169,1.000)",
            isOpaque: true,
          },
          webView: {
            class: "WKWebView",
            isOpaque: false,
            backgroundColor: "rgba(0.537,0.118,0.169,1.000)",
            scrollViewBackgroundColor: "rgba(0.537,0.118,0.169,1.000)",
            underPageBackgroundColor: "nil",
            frame: { x: 0, y: 0, w: 390, h: 844 },
            alpha: 1,
            isHidden: false,
          },
          bannerViews: [
            {
              class: "MockGADBannerView",
              frame: { x: 0, y: 120, w: 320, h: 50 },
              alpha: 1,
              isHidden: false,
              isOpaque: true,
              backgroundColor: "rgba(1,1,1,1)",
            },
          ],
          bannerViewCount: 1,
          layoutDirtyHints: [],
          inFlightAnimation: false,
        };
        this.events.push({ type: "native_snapshot", snap });
        return snap;
      },
    };

    const AdMob = {
      async initialize() {
        return {};
      },
      async showBanner(options) {
        admobCalls.push({ op: "showBanner", options, t: performance.now() });
        return {};
      },
      async removeBanner() {
        admobCalls.push({ op: "removeBanner", t: performance.now() });
        return {};
      },
      async hideBanner() {
        return {};
      },
      addListener() {
        return { remove() {} };
      },
    };

    window.__WASE_FLASH_MOCK__ = { admobCalls, flashNative };

    window.Capacitor = {
      isNativePlatform: () => true,
      getPlatform: () => "ios",
      getPlugin: (name) => {
        if (name === "AdMob") return AdMob;
        if (name === "FlashDiag") return flashNative;
        return null;
      },
      Plugins: {
        AdMob,
        FlashDiag: flashNative,
      },
    };
  });
}

function countEvents(traces, type) {
  let n = 0;
  for (const tr of traces) {
    for (const ev of tr.events || []) {
      if (ev.type === type) n += 1;
    }
  }
  return n;
}

function eventPresence(traces) {
  const out = {};
  for (const type of SIGNAL_EVENTS) {
    out[type] = countEvents(traces, type);
  }
  return out;
}

async function runMode(browser, mode) {
  const context = await browser.newContext({
    viewport: { width: 390, height: 844 },
    deviceScaleFactor: 2,
  });
  const page = await context.newPage();
  await installCapacitorMock(page);

  await page.goto(modeUrl(mode), {
    waitUntil: "domcontentloaded",
    timeout: 120000,
  });
  await page.waitForSelector(
    '[data-spa-page="ホーム"], [data-spa-page="ログイン"]',
    { timeout: 60000 }
  );
  if (await page.locator('[data-spa-page="ログイン"]').count()) {
    await page.locator("button.linkish", { hasText: "閲覧モード" }).click();
    await page.waitForSelector('[data-spa-page="ホーム"]', { timeout: 30000 });
  }

  // Ensure flash diag + force banner tracking after native bootstrap settles
  await page.evaluate(() => {
    try {
      window.localStorage.setItem("wase_flash_diag", "1");
      window.WASE_FLASH_DIAG_FORCE = true;
      window.WASE_ADMOB_CONFIG = Object.assign({}, window.WASE_ADMOB_CONFIG || {}, {
        DISABLE_ADS: false,
      });
      window.WaseFlashDiag?.refreshEnabled?.();
      window.WaseFlashDiag?.clear?.();
    } catch {
      /* ignore */
    }
  });

  await page.waitForTimeout(500);
  await page.evaluate(async () => {
    try {
      if (window.WaseCapacitor?.showBannerAd) {
        await window.WaseCapacitor.showBannerAd();
      }
    } catch {
      /* ignore */
    }
  });
  await page.waitForTimeout(400);

  // Drop boot traces so hop comparison is clean
  await page.evaluate(() => {
    try {
      window.WaseFlashDiag?.clear?.();
    } catch {
      /* ignore */
    }
  });

  for (const [label, heading] of TAB_HOPS) {
    await page.locator("nav.bottom-nav a.nav-item", { hasText: label }).click();
    await page.waitForSelector(`[data-spa-page="${heading}"]`, {
      timeout: 20000,
    });
    await page.waitForTimeout(550);
  }

  const exportPayload = await page.evaluate(() => {
    const diag = window.WaseCapacitor?.getSpaNavDiag?.() || null;
    const traces = window.WaseFlashDiag?.exportTraces?.() || null;
    const mock = window.__WASE_FLASH_MOCK__ || null;
    return { diag, traces, mock };
  });

  await context.close();

  const traces = exportPayload.traces?.traces || [];
  const presence = eventPresence(traces);
  return {
    mode: mode.id,
    spaNavDiag: mode.spaNavDiag || "normal",
    diagFlags: exportPayload.diag,
    hopCount: TAB_HOPS.length,
    traceCount: traces.length,
    presence,
    summaries: exportPayload.traces?.summaries || [],
    admobCallCount: exportPayload.mock?.admobCalls?.length || 0,
    sampleTrace: traces[traces.length - 1] || null,
  };
}

function diffAgainstNormal(results) {
  const normal = results.find((r) => r.mode === "normal");
  if (!normal) return [];
  return results
    .filter((r) => r.mode !== "normal")
    .map((r) => {
      const disappeared = [];
      const appeared = [];
      const unchanged = [];
      for (const type of SIGNAL_EVENTS) {
        const a = normal.presence[type] || 0;
        const b = r.presence[type] || 0;
        if (a > 0 && b === 0) disappeared.push(type);
        else if (a === 0 && b > 0) appeared.push(type);
        else unchanged.push(type);
      }
      return {
        mode: r.mode,
        disappeared,
        appeared,
        presence: r.presence,
      };
    });
}

function rankCauses(results, diffs) {
  /**
   * Heuristic ranking from event differentials (not visual flash detection).
   * Higher score = more likely iOS-only flash driver.
   */
  const scores = {
    "AdMob banner reposition": 0,
    NativeSpaBridge: 0,
    "React transition / Keep-Alive": 0,
    "WKWebView / iOS compositing": 0,
  };

  const byMode = Object.fromEntries(diffs.map((d) => [d.mode, d]));
  const normal = results.find((r) => r.mode === "normal");

  if (normal?.presence.schedule_banner_reposition > 0) {
    scores["AdMob banner reposition"] += 3;
  }
  if (byMode.no_banner?.disappeared.includes("schedule_banner_reposition")) {
    scores["AdMob banner reposition"] += 5;
  }
  if (byMode.no_banner?.disappeared.includes("reposition_inline_banner")) {
    scores["AdMob banner reposition"] += 3;
  }
  if (byMode.no_bridge?.disappeared.includes("notify_spa_navigation")) {
    scores.NativeSpaBridge += 4;
  }
  if (byMode.no_bridge?.disappeared.includes("schedule_banner_reposition")) {
    scores.NativeSpaBridge += 2;
    scores["AdMob banner reposition"] += 1;
  }
  if (byMode.no_analytics?.disappeared.includes("analytics_track_page_view")) {
    // Analytics alone is weak for visual flash
    scores.NativeSpaBridge += 0;
  }
  if (byMode.no_keepalive?.disappeared.includes("keepalive_pane_mount")) {
    scores["React transition / Keep-Alive"] += 2;
  }
  if (
    byMode.no_transition?.disappeared.includes("tab_transition_start") ||
    byMode.no_transition?.appeared.includes("tab_transition_instant")
  ) {
    scores["React transition / Keep-Alive"] += 2;
  }

  // Web cannot exercise real WKWebView compositing; leave as residual candidate
  scores["WKWebView / iOS compositing"] += 1;
  if (
    (normal?.presence.schedule_banner_reposition || 0) === 0 &&
    (normal?.presence.notify_spa_navigation || 0) === 0
  ) {
    scores["WKWebView / iOS compositing"] += 3;
  }

  const ranked = Object.entries(scores)
    .sort((a, b) => b[1] - a[1])
    .map(([cause, score], i) => ({ rank: i + 1, cause, score }));

  return { scores, ranked };
}

function toMarkdown(report) {
  const lines = [];
  lines.push("# Flash diag automated report");
  lines.push("");
  lines.push(`- Generated: ${report.generatedAt}`);
  lines.push(`- Base URL: ${report.baseUrl}`);
  lines.push(`- Platform: ${report.platform}`);
  lines.push("");
  lines.push("## Constraints");
  lines.push("");
  for (const c of report.constraints) {
    lines.push(`- ${c}`);
  }
  lines.push("");
  lines.push("## Cause ranking (from event differentials)");
  lines.push("");
  for (const r of report.ranking.ranked) {
    lines.push(`${r.rank}. **${r.cause}** (score ${r.score})`);
  }
  lines.push("");
  lines.push("## Mode presence matrix");
  lines.push("");
  lines.push(
    ["mode", ...SIGNAL_EVENTS.map((e) => e.replace(/_/g, " "))].join(" | ")
  );
  lines.push(["---", ...SIGNAL_EVENTS.map(() => "---")].join(" | "));
  for (const m of report.results) {
    lines.push(
      [
        m.mode,
        ...SIGNAL_EVENTS.map((e) => String(m.presence[e] || 0)),
      ].join(" | ")
    );
  }
  lines.push("");
  lines.push("## Diff vs normal (events that disappear)");
  lines.push("");
  for (const d of report.diffs) {
    lines.push(`### ${d.mode}`);
    lines.push("");
    lines.push(
      d.disappeared.length
        ? d.disappeared.map((x) => `- \`${x}\``).join("\n")
        : "- (none)"
    );
    lines.push("");
  }
  lines.push("## Interpretation");
  lines.push("");
  lines.push(report.interpretation);
  lines.push("");
  lines.push("## Next minimal fix (only after TestFlight confirms)");
  lines.push("");
  lines.push(report.nextStep);
  lines.push("");
  return lines.join("\n");
}

const browser = await launchBrowser();
const results = [];
try {
  for (const mode of MODES) {
    console.log(`mode=${mode.id} …`);
    const result = await runMode(browser, mode);
    console.log(
      `  traces=${result.traceCount} notify=${result.presence.notify_spa_navigation} bannerSched=${result.presence.schedule_banner_reposition} admob=${result.admobCallCount}`
    );
    results.push(result);
  }
} finally {
  await browser.close();
}

const diffs = diffAgainstNormal(results);
const ranking = rankCauses(results, diffs);

const interpretation = (() => {
  const top = ranking.ranked[0]?.cause;
  const noBanner = diffs.find((d) => d.mode === "no_banner");
  if (
    noBanner?.disappeared.includes("schedule_banner_reposition") ||
    noBanner?.disappeared.includes("reposition_inline_banner")
  ) {
    return [
      "観測上、通常時のタブ切替トレースには `schedule_banner_reposition` / AdMob banner 経路が含まれ、",
      "`no_banner` モードでのみそれが消える。これは iOS 限定のピカッ主因候補として",
      "**AdMob banner reposition** を最上位に置く根拠になる。",
      "ただし本スクリプトは視覚フラッシュ自体を検出していない。TestFlight で `no_banner` 時にピカッが消えるかを最終確認すること。",
    ].join("");
  }
  return `自動比較の最上候補は「${top}」。TestFlight の spa_nav_diag 手動確認で視覚症状と突き合わせること。`;
})();

const nextStep = (() => {
  const top = ranking.ranked[0]?.cause;
  if (top === "AdMob banner reposition") {
    return "TestFlight で `?spa_nav_diag=no_banner` を確認し、ピカッが消えたら SPA タブ切替時のみ `scheduleBannerReposition` を呼ばない最小修正を入れる（通常の scroll/resize 再配置は維持）。";
  }
  return "TestFlight で ranking 上位モードを順に試し、ピカッが消えるモードを確定してから最小修正する。";
})();

const report = {
  generatedAt: new Date().toISOString(),
  baseUrl,
  platform: process.platform,
  constraints: [
    "iOS Simulator / 実機はこの Windows 環境では実行不可。視覚的なピカッの自動検出は未実施。",
    "Playwright は Capacitor/AdMob/FlashDiag をモックし、JS 経路のイベント差分を比較する。",
    "本番の通常挙動（banner reposition 含む）は変更していない。",
    "本物の WKWebView compositing / CATransaction は FlashDiagPlugin を含む iOS ビルドで観測する。",
  ],
  results,
  diffs,
  ranking,
  interpretation,
  nextStep,
};

fs.writeFileSync(outJson, JSON.stringify(report, null, 2), "utf8");
fs.writeFileSync(outMd, toMarkdown(report), "utf8");
console.log(`\nWrote ${outJson}`);
console.log(`Wrote ${outMd}`);
console.log("\nRanking:");
for (const r of ranking.ranked) {
  console.log(`  ${r.rank}. ${r.cause} (score ${r.score})`);
}
