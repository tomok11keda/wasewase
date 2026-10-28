import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

const root = dirname(fileURLToPath(import.meta.url));
const view = readFileSync(join(root, "OrganizationEventDetailView.tsx"), "utf8");
const presentation = readFileSync(join(root, "eventDetailPresentation.ts"), "utf8");
const page = readFileSync(join(root, "../../pages/OrganizationEventDetailPage.tsx"), "utf8");
const chat = readFileSync(join(root, "../../pages/OrganizationChatEventDetailPage.tsx"), "utf8");
const css = readFileSync(join(root, "../../styles/org.css"), "utf8");

test("public and draft event details share one information layout", () => {
  assert.equal(page.includes("OrganizationEventDetailView"), true);
  assert.equal(view.includes("eventPublicationStatusLabel"), true);
  assert.equal(view.includes("eventSignupModeLabel"), true);
  assert.equal(view.includes("formatTokyoEventSchedule"), true);
  assert.equal(view.includes("会場"), true);
  assert.equal(view.includes("説明"), true);
  assert.equal(view.includes("showManage"), true);
  assert.equal(view.includes("aria-label=\"イベント管理\""), true);
});

test("admin CTAs stay grouped by draft published and danger actions", () => {
  assert.equal(presentation.includes("イベントを公開する"), true);
  assert.equal(view.includes("タイムラインにシェア"), true);
  assert.equal(presentation.includes("編集する"), true);
  assert.equal(presentation.includes('return "複製"'), true);
  assert.equal(view.includes("その他の操作"), true);
  assert.equal(presentation.includes("イベントを中止"), true);
  assert.equal(presentation.includes("イベントを削除"), true);
  assert.equal(page.includes("publishOrganizationEvent"), true);
  assert.equal(page.includes("unpublishOrganizationEvent"), true);
  assert.equal(page.includes("duplicateOrganizationEvent"), true);
  assert.equal(page.includes("cancelOrganizationEvent"), true);
  assert.equal(page.includes("deleteOrganizationEvent"), true);
  assert.equal(page.includes("shareOrganizationEventToTimeline"), true);
  assert.equal(page.includes("invalidateTimelineFeed"), true);
  assert.equal(page.includes("window.confirm"), true);
  assert.equal(view.includes("投稿を見る"), true);
  assert.equal(view.includes("org-event-detail__image"), true);
});

test("chat events keep the existing detail page", () => {
  assert.equal(chat.includes("OrganizationEventDetailView"), false);
  assert.equal(chat.includes("org-event-detail"), false);
  assert.equal(chat.includes("その他の操作"), false);
});

test("event detail CSS stacks cards and keeps 44px taps", () => {
  assert.match(
    css,
    /\.org-event-detail \.btn[\s\S]{0,200}min-height: 44px/
  );
  assert.match(
    css,
    /\.org-event-badge--draft\s*\{[^}]*background: #eef2f5/
  );
  assert.match(
    css,
    /\.org-event-badge--published\s*\{[^}]*background: #f7edf0/
  );
  assert.match(
    css,
    /\.org-event-badge--cancelled\s*\{[^}]*background: #3d1016/
  );
  assert.match(
    css,
    /\.org-event-more > summary[\s\S]{0,120}min-height: 44px/
  );
  assert.match(
    css,
    /@media \(max-width: 360px\)[\s\S]{0,180}grid-template-columns: 1fr/
  );
});
