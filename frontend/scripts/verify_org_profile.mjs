/**
 * Mocked organization profile UI checks. Does not create DB rows.
 * Usage: node scripts/verify_org_profile.mjs [baseUrl]
 */
import { chromium } from "playwright";

const baseUrl = (process.argv[2] || "http://127.0.0.1:8766").replace(/\/$/, "");

const listedOrg = {
  ok: true,
  organization: {
    id: 9,
    name: "公開サークル",
    slug: "listed-circle",
    description: "長い説明文 ".repeat(40),
    avatar_url: "",
    category: "circle",
    instagram_url: "https://instagram.com/example",
    website_url: "javascript:alert(1)",
    is_verified: true,
    links: [
      {
        id: 1,
        title: "Instagram",
        url: "https://instagram.com/example",
        position: 0,
      },
    ],
  },
  can_manage: false,
  my_role: null,
};

const managedOrg = {
  ...listedOrg,
  can_manage: true,
  my_role: "owner",
  organization: {
    ...listedOrg.organization,
    slug: "managed-circle",
    name: "管理サークル",
    website_url: "https://example.com",
    is_verified: false,
    links: [
      {
        id: 1,
        title: "Instagram",
        url: "https://instagram.com/example",
        position: 0,
      },
      {
        id: 2,
        title: "公式Webサイト",
        url: "https://example.com",
        position: 1,
      },
    ],
  },
};

function mePayload(authenticated) {
  return {
    ok: true,
    authenticated,
    is_browse_mode: !authenticated,
    react_spa_enabled: true,
    user: authenticated
      ? {
          id: 1,
          username: "tester",
          display_name: "テスター",
          avatar_url: "",
          initial: "テ",
        }
      : null,
    unread_notifications: 0,
    dm_unread_total: 0,
    onboarding_required: false,
    onboarding_completed: true,
  };
}

async function launchBrowser() {
  const channels = [process.env.PLAYWRIGHT_CHANNEL, "chrome", "msedge", undefined].filter(
    (value, index, arr) => arr.indexOf(value) === index
  );
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

async function openPage(browser, { me, orgStatus, orgBody, failOnce = false }) {
  const page = await browser.newPage();
  await page.setViewportSize({ width: 390, height: 844 });
  let orgHits = 0;
  let currentOrg = orgBody;
  await page.route("**/api/v1/me/**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(mePayload(me)),
    });
  });
  await page.route("**/api/v1/auth/browse/**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ ok: true, me: mePayload(false) }),
    });
  });
  await page.route("**/api/v1/organizations/**", async (route) => {
    const method = route.request().method();
    if (method === "PATCH") {
      const updated = JSON.parse(JSON.stringify(currentOrg));
      updated.organization = {
        ...updated.organization,
        name: "更新後の団体名",
      };
      currentOrg = updated;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(updated),
      });
      return;
    }
    orgHits += 1;
    if (failOnce && orgHits === 1) {
      await route.fulfill({ status: 500, contentType: "application/json", body: "{}" });
      return;
    }
    await route.fulfill({
      status: orgStatus,
      contentType: "application/json",
      body: JSON.stringify(currentOrg),
    });
  });
  return page;
}

const browser = await launchBrowser();
try {
  const listed = await openPage(browser, {
    me: true,
    orgStatus: 200,
    orgBody: listedOrg,
  });
  await listed.goto(`${baseUrl}/app/orgs/listed-circle/`, { waitUntil: "networkidle" });
  await listed.waitForSelector('[data-spa-page="団体"]');
  const listedText = await listed.locator('[data-spa-page="団体"]').innerText();
  if (!listedText.includes("公開サークル")) throw new Error("listed name missing");
  if (!listedText.includes("サークル")) throw new Error("category missing");
  if (!listedText.includes("運営確認済み団体")) throw new Error("verified badge missing");
  if (!listedText.includes("Instagram")) throw new Error("instagram link missing");
  if (listedText.includes("javascript:alert")) throw new Error("unsafe website leaked");
  if (listedText.includes("プロフィールを編集")) throw new Error("edit shown without can_manage");
  const chip = listed.locator("a.profile-links-chip");
  if ((await chip.count()) !== 1) throw new Error("expected one profile link chip");
  if ((await listed.locator("a.org-profile-link").count()) !== 0) {
    throw new Error("legacy org-profile-link should not render");
  }
  const href = await chip.getAttribute("href");
  if (href !== "https://instagram.com/example") throw new Error("instagram href mismatch");
  const target = await chip.getAttribute("target");
  if (target !== "_blank") throw new Error("profile link target missing");
  const rel = await chip.getAttribute("rel") || "";
  if (!rel.includes("noopener") || !rel.includes("noreferrer")) {
    throw new Error("profile link rel missing");
  }
  const label = await chip.locator(".profile-links-chip__label").innerText();
  if (label.trim() !== "Instagram") throw new Error("profile link label mismatch");
  console.log("ok listed profile");

  const missing = await openPage(browser, {
    me: true,
    orgStatus: 404,
    orgBody: { ok: false, error: "not_found" },
  });
  await missing.goto(`${baseUrl}/app/orgs/does-not-exist/`, { waitUntil: "networkidle" });
  await missing.waitForSelector('[data-spa-page="団体"]');
  const missingText = await missing.locator('[data-spa-page="団体"]').innerText();
  if (!missingText.includes("見つからない")) throw new Error("404 copy missing");
  if (missingText.includes("下書き") || missingText.includes("停止")) {
    throw new Error("unpublished status leaked");
  }
  console.log("ok 404");

  const retryPage = await openPage(browser, {
    me: true,
    orgStatus: 200,
    orgBody: listedOrg,
    failOnce: true,
  });
  await retryPage.goto(`${baseUrl}/app/orgs/listed-circle/`, { waitUntil: "networkidle" });
  await retryPage.getByRole("button", { name: "再試行" }).click();
  await retryPage.waitForSelector("text=公開サークル");
  console.log("ok retry");

  const managed = await openPage(browser, {
    me: true,
    orgStatus: 200,
    orgBody: managedOrg,
  });
  await managed.goto(`${baseUrl}/app/orgs/managed-circle/`, { waitUntil: "networkidle" });
  await managed.getByRole("link", { name: "プロフィールを編集" }).click();
  await managed.waitForURL(/\/app\/orgs\/managed-circle\/edit/);
  await managed.waitForSelector('[data-spa-page="団体を編集"]');
  if (await managed.locator("#org-slug").count()) throw new Error("slug field should not exist");
  await managed.fill("#org-name", "更新後の団体名");
  await managed.getByRole("button", { name: "保存する" }).click();
  await managed.waitForURL(/\/app\/orgs\/managed-circle\/?$/);
  await managed.waitForSelector("text=更新後の団体名");
  console.log("ok manage and save");

  const guest = await openPage(browser, {
    me: false,
    orgStatus: 401,
    orgBody: { ok: false, error: "unauthorized" },
  });
  await guest.goto(`${baseUrl}/app/orgs/listed-circle/`, { waitUntil: "networkidle" });
  const guestText = await guest.locator("body").innerText();
  if (!guestText.includes("ログイン")) throw new Error("401 login copy missing");
  console.log("ok 401/browse login path");
} finally {
  await browser.close();
}
