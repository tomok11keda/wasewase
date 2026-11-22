/**
 * Mobile UI smoke for official course search/enroll (local only).
 * Requires Django with WASE_REACT_SPA=1 and WASE_OFFICIAL_CLASS_STUDENT_UI=1
 * and fictional fixtures from seed_official_e2e_fixtures.
 *
 * Usage (from frontend/):
 *   node scripts/verify_official_course_e2e.mjs [baseUrl]
 */
import { chromium } from "playwright";
import fs from "node:fs";
import path from "node:path";

const baseUrl = (process.argv[2] || "http://127.0.0.1:8765").replace(/\/$/, "");
const email = process.env.E2E_EMAIL || "e2e-official-local@example.com";
const password = process.env.E2E_PASSWORD || "e2e-pass-12345";
const outDir = process.env.E2E_ARTIFACT_DIR || "/opt/cursor/artifacts";
fs.mkdirSync(outDir, { recursive: true });

const results = [];
function record(step, ok, detail = "") {
  results.push({ step, ok, detail });
  console.log(`${ok ? "PASS" : "FAIL"}: ${step}${detail ? ` — ${detail}` : ""}`);
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

async function loginViaApi(page) {
  await page.goto(`${baseUrl}/app/login`, { waitUntil: "networkidle" });
  const csrf = await page.evaluate(async () => {
    const res = await fetch("/api/v1/auth/csrf/", { credentials: "same-origin" });
    const data = await res.json();
    return (
      document.cookie
        .split("; ")
        .find((c) => c.startsWith("csrftoken="))
        ?.split("=")[1] || ""
    );
  });
  const login = await page.evaluate(
    async ({ email, password, csrf }) => {
      const res = await fetch("/api/v1/auth/login/", {
        method: "POST",
        credentials: "same-origin",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": csrf,
        },
        body: JSON.stringify({ email, password }),
      });
      return { status: res.status, data: await res.json() };
    },
    { email, password, csrf }
  );
  if (!login.data?.ok) {
    throw new Error(`login failed: ${JSON.stringify(login)}`);
  }
  return login.data;
}

async function shot(page, name) {
  const file = path.join(outDir, name);
  await page.screenshot({ path: file, fullPage: true });
  return file;
}

const browser = await launchBrowser();
const context = await browser.newContext({
  viewport: { width: 390, height: 844 },
  deviceScaleFactor: 2,
});
const page = await context.newPage();
page.setDefaultTimeout(20000);

try {
  const me = await loginViaApi(page);
  record(
    "login",
    true,
    `spa=${me.me?.react_spa_enabled} onboard=${me.me?.onboarding_required}`
  );

  const meta = await page.evaluate(async () => {
    const res = await fetch("/api/v1/courses/meta/", { credentials: "same-origin" });
    return res.json();
  });
  record(
    "feature_flag_on",
    Boolean(meta.official_class_search_enabled),
    JSON.stringify(meta.official_class_pilot_schools || [])
  );

  await page.goto(`${baseUrl}/app/timetable`, { waitUntil: "networkidle" });
  await page.waitForSelector(".timetable-page .timetable-grid, .timetable-grid", {
    timeout: 20000,
  });
  await shot(page, "official-e2e-mobile-timetable.png");
  record("timetable_render", true, page.url());

  // Prefer continuous add button (works even when empty CTA is hidden).
  const addBtn = page.locator("button.timetable-add-btn").first();
  if ((await addBtn.count()) === 0) {
    // Fall back to empty slot Thursday period 1 (p1-d3)
    const slot = page.locator('[data-timetable-slot][data-slot-key="p1-d3"]');
    await slot.click({ force: true });
  } else {
    await addBtn.click();
  }

  await page.waitForSelector(".course-add-sheet, [data-course-add-sheet], .sheet", {
    timeout: 15000,
  }).catch(() => null);

  // CourseAddSheet root class from CSS
  const sheetVisible =
    (await page.locator("text=公式から選ぶ").count()) > 0 ||
    (await page.locator("text=みんなの授業").count()) > 0;
  if (!sheetVisible) {
    // Try empty cell click
    const empty = page.locator(".timetable-slot.is-empty").first();
    if ((await empty.count()) > 0) {
      await empty.click({ force: true });
      await page.waitForTimeout(800);
    }
  }

  const hasOfficialTab = (await page.locator("text=公式から選ぶ").count()) > 0;
  const hasCommunityTab = (await page.locator("text=みんなの授業").count()) > 0;
  await shot(page, "official-e2e-mobile-add-sheet.png");
  record(
    "add_sheet_tabs",
    hasOfficialTab && hasCommunityTab,
    `official=${hasOfficialTab} community=${hasCommunityTab}`
  );

  if (hasOfficialTab) {
    await page.locator("text=公式から選ぶ").first().click();
    const input = page.locator(
      'input[placeholder*="公式"], input[placeholder*="検索"], .course-add-sheet input[type="search"], .course-add-sheet input'
    ).first();
    await input.fill("架空");
    await page.waitForTimeout(900);
    await shot(page, "official-e2e-mobile-search.png");
    const list = page.locator(".course-sheet__list .course-sheet__item");
    const hasResults = (await list.count()) > 0;
    const emptyMsg = await page.locator(".course-sheet__empty").first().textContent().catch(() => "");
    record(
      "official_search_results",
      hasResults,
      hasResults ? `count=${await list.count()}` : `empty=${emptyMsg}`
    );

    // Try pending/conflict row click for alert
    page.once("dialog", async (dialog) => {
      record(
        "error_alert_japanese",
        /準備中|複数|確認|共通時間割/.test(dialog.message()),
        dialog.message()
      );
      await dialog.accept();
    });
    const pending = page.locator(".course-sheet__item", {
      hasText: "組織行動入門",
    });
    const conflict = page.locator(".course-sheet__item", {
      hasText: "マーケティング演習",
    });
    if ((await pending.count()) > 0) {
      await pending.first().click();
      await page.waitForTimeout(600);
    } else if ((await conflict.count()) > 0) {
      await conflict.first().click();
      await page.waitForTimeout(600);
    } else {
      record("error_alert_japanese", false, "no pending/conflict row visible");
    }

    // Enroll ready business ethics if visible
    const ready = page.locator(".course-sheet__item", {
      hasText: "ビジネス倫理",
    });
    if ((await ready.count()) > 0) {
      await ready.first().click();
      await page.waitForTimeout(1500);
      await shot(page, "official-e2e-mobile-after-enroll-attempt.png");
      const toast = page.locator(".course-sheet__toast");
      const toastText =
        (await toast.count()) > 0 ? await toast.first().textContent() : "";
      const toastOk = /追加しました/.test(toastText || "");
      // Sheet may close on success; treat disappearance of item as success too.
      const stillOpen = (await ready.count()) > 0;
      record(
        "enroll_attempt",
        toastOk || !stillOpen,
        toastText || (stillOpen ? "no toast" : "sheet closed/updated after click")
      );
    } else {
      record("enroll_attempt", false, "ビジネス倫理 not in list");
    }
  }

  // Community tab still present
  if (hasCommunityTab) {
    await page.locator("text=みんなの授業").first().click();
    await page.waitForTimeout(400);
    await shot(page, "official-e2e-mobile-community-tab.png");
    record("community_tab_switch", true);
  }
} catch (err) {
  record("fatal", false, String(err));
  try {
    await shot(page, "official-e2e-mobile-fatal.png");
  } catch {
    /* ignore */
  }
} finally {
  await browser.close();
}

const failed = results.filter((r) => !r.ok);
console.log("\n=== SUMMARY ===");
console.log(JSON.stringify(results, null, 2));
process.exit(failed.length ? 1 : 0);
