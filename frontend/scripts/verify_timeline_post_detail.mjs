/**
 * Verify Timeline post detail UX.
 * Requires: Django runserver with WASE_REACT_SPA=True, BROWSE_MODE_GATE_ENABLED=False
 * Usage (from frontend/): node scripts/verify_timeline_post_detail.mjs [baseUrl]
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

function fail(message) {
  console.error(`FAIL: ${message}`);
  process.exit(1);
}

const browser = await launchBrowser();
const page = await browser.newPage();
await page.setViewportSize({ width: 390, height: 844 });

await page.goto(spaUrl, { waitUntil: "networkidle" });
await page.waitForSelector('[data-spa-page="タイムライン"]', { timeout: 15000 });

await page.goto(`${spaUrl}posts/999999999`, { waitUntil: "networkidle" });
await page.waitForSelector('[data-spa-page="投稿"]', { timeout: 10000 });
const missingText = await page.locator(".empty-message").first().textContent();
if (!missingText || !missingText.includes("この投稿は表示できません")) {
  fail(`missing post should show safe 404, got: ${missingText}`);
}
console.log("direct missing post -> safe 404");

await page.locator("button.post-detail-back").click();
await page.waitForURL(/\/app\/?$/, { timeout: 10000 });
await page.waitForSelector('[data-spa-page="タイムライン"]', { timeout: 10000 });
console.log("direct/deep-link back -> /app/");

await page.goto(`${spaUrl}#post-1`, { waitUntil: "networkidle" });
await page.waitForSelector('[data-spa-page="タイムライン"]', { timeout: 10000 });
if (!page.url().includes("/app/")) {
  fail(`legacy hash left /app/: ${page.url()}`);
}
console.log(`legacy /#post-1 still on timeline -> ${page.url()}`);

await page.goto(spaUrl, { waitUntil: "networkidle" });
await page.waitForSelector('[data-spa-page="タイムライン"]', { timeout: 15000 });

const card = page.locator("article.tweet-card").first();
if ((await card.count()) === 0) {
  console.log("skip card tap checks: timeline empty");
  await browser.close();
  console.log("OK: post detail route/404/back/legacy hash");
  process.exit(0);
}

const postId = await card.getAttribute("data-spa-post");
if (!postId) fail("timeline card missing data-spa-post");

await card.locator(".tweet-main > .tweet-body").click({ force: true });
await page.waitForURL(new RegExp(`/app/posts/${postId}/?$`), { timeout: 10000 });
await page.waitForSelector('[data-spa-page="投稿"]', { timeout: 10000 });
await page.waitForSelector(".post-detail-page .tweet-comments", { timeout: 10000 });
const focusedAfterBody = await page.evaluate(
  () => document.activeElement?.getAttribute("placeholder") || ""
);
if (focusedAfterBody.includes("コメント")) {
  fail("body tap should not focus composer");
}
console.log(`body tap -> detail /posts/${postId}`);

await page.locator("button.post-detail-back").click();
await page.waitForSelector('[data-spa-page="タイムライン"]', { timeout: 10000 });
console.log("detail back -> timeline");

await page.locator(`article[data-spa-post="${postId}"] .tweet-action--comment`).click();
await page.waitForURL(new RegExp(`/app/posts/${postId}/?$`), { timeout: 10000 });
await page.waitForSelector(".post-detail-page .tweet-comment-form input", {
  timeout: 10000,
});
await page.waitForTimeout(80);
const activeTag = await page.evaluate(() => {
  const el = document.activeElement;
  return el ? `${el.tagName}:${el.getAttribute("placeholder") || ""}` : "";
});
if (!activeTag.startsWith("INPUT:")) {
  fail(`comment icon should focus composer, active=${activeTag}`);
}
console.log("comment icon -> detail + composer focus");

await page.locator("button.post-detail-back").click();
await page.waitForSelector('[data-spa-page="タイムライン"]', { timeout: 10000 });

const likeBefore = page.url();
await page.locator(`article[data-spa-post="${postId}"] .tweet-action--like`).click();
await page.waitForTimeout(250);
if (page.url() !== likeBefore && page.url().includes("/posts/")) {
  fail(`like tap navigated to detail: ${page.url()}`);
}
console.log("like tap stayed on timeline");

const author = page.locator(`article[data-spa-post="${postId}"] a.tweet-author`);
if ((await author.count()) > 0) {
  await author.click();
  await page.waitForURL(/\/app\/users\/\d+/, { timeout: 10000 });
  if (page.url().includes("/posts/")) {
    fail(`avatar/name tap opened post detail: ${page.url()}`);
  }
  console.log(`profile tap -> ${page.url()}`);
  await page.locator("a.profile-back").click();
  await page.waitForSelector('[data-spa-page="タイムライン"]', { timeout: 10000 });
}

const flea = page.locator("a.timeline-flea-share").first();
if ((await flea.count()) > 0) {
  await flea.click();
  await page.waitForURL(/\/app\/flea\/products\/\d+/, { timeout: 10000 });
  if (page.url().includes("/posts/")) {
    fail(`flea card opened post detail: ${page.url()}`);
  }
  console.log(`flea card -> ${page.url()}`);
  await page.locator("a.back-link").first().click();
  await page.waitForTimeout(300);
} else {
  console.log("skip flea card: none in feed");
}

await browser.close();
console.log("OK: timeline post detail UX");
process.exit(0);
