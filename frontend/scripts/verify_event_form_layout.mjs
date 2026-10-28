/**
 * Measure the event create form at phone widths and the desktop center column.
 * Usage (from frontend/): node scripts/verify_event_form_layout.mjs
 */
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const css = readFileSync(join(root, "src/styles/org.css"), "utf8");

const html = `<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <style>
    * { box-sizing: border-box; }
    html, body { margin: 0; background: #f7f9fc; font-family: sans-serif; }
    ${css}
  </style>
</head>
<body>
  <div class="org-edit-page">
    <div class="main-inner">
      <p class="form-lead">まずは下書きを保存します。公開と抽選は作成後に設定できます。</p>
      <form class="form-card org-event-form">
        <div class="form-group">
          <label for="event-title">イベント名</label>
          <input id="event-title" value="新歓説明会" />
        </div>
        <fieldset class="form-group org-event-signup-mode">
          <legend>申込方式</legend>
          <div class="org-event-signup-mode__options" role="radiogroup">
            <label class="org-event-choice is-selected">
              <input type="radio" name="event-signup-mode" checked />
              <span class="org-event-choice__text">
                <strong>参加申込あり</strong>
                <small>締切後に抽選もできます。参加者を受け付ける公開イベント向けです。</small>
              </span>
            </label>
            <label class="org-event-choice">
              <input type="radio" name="event-signup-mode" />
              <span class="org-event-choice__text">
                <strong>告知のみ</strong>
                <small>申込・抽選は使いません。早稲田祭の屋台・公演などの案内向けです。</small>
              </span>
            </label>
          </div>
        </fieldset>
        <div class="form-group">
          <label for="event-description">説明</label>
          <textarea id="event-description" rows="6">説明文</textarea>
        </div>
        <div class="org-event-form__when">
          <div class="form-group">
            <label for="event-starts-at">開始日時（日本時間）</label>
            <input id="event-starts-at" type="datetime-local" value="2026-11-01T10:00" />
          </div>
          <div class="form-group">
            <label for="event-ends-at">終了日時（日本時間）</label>
            <input id="event-ends-at" type="datetime-local" value="2026-11-01T16:00" />
          </div>
        </div>
        <label class="org-event-check">
          <input type="checkbox" checked />
          <span>申し込みを受け付ける</span>
        </label>
      </form>
    </div>
  </div>
</body>
</html>`;

const VIEWPORTS = [
  { name: "320", width: 320, height: 720 },
  { name: "375", width: 375, height: 812 },
  { name: "390", width: 390, height: 844 },
  { name: "430", width: 430, height: 932 },
  { name: "desktop-center", width: 1024, height: 800 },
];

async function launchBrowser() {
  const channels = ["chrome"];
  if (process.env.PLAYWRIGHT_CHANNEL) channels.unshift(process.env.PLAYWRIGHT_CHANNEL);
  channels.push(undefined);
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

const browser = await launchBrowser();
const page = await browser.newPage();
const failures = [];

for (const viewport of VIEWPORTS) {
  await page.setViewportSize({ width: viewport.width, height: viewport.height });
  await page.setContent(html, { waitUntil: "load" });
  const report = await page.evaluate(() => {
    const doc = document.documentElement;
    const choices = [...document.querySelectorAll(".org-event-choice")].map((el) => {
      const radio = el.querySelector('input[type="radio"]');
      const title = el.querySelector("strong");
      const radioBox = radio?.getBoundingClientRect();
      const titleBox = title?.getBoundingClientRect();
      const box = el.getBoundingClientRect();
      return {
        top: box.top,
        bottom: box.bottom,
        left: box.left,
        right: box.right,
        width: box.width,
        height: box.height,
        radioWidth: radioBox?.width || 0,
        titleWidth: titleBox?.width || 0,
        titleHeight: titleBox?.height || 0,
        titleText: title?.textContent || "",
      };
    });
    return {
      scrollWidth: doc.scrollWidth,
      clientWidth: doc.clientWidth,
      innerWidth: window.innerWidth,
      formWidth: document.querySelector(".org-event-form")?.getBoundingClientRect().width || 0,
      optionsWidth:
        document.querySelector(".org-event-signup-mode__options")?.getBoundingClientRect()
          .width || 0,
      choices,
    };
  });

  if (report.scrollWidth > report.clientWidth + 1) {
    failures.push(`${viewport.name}: horizontal scroll ${report.scrollWidth} > ${report.clientWidth}`);
  }
  if (report.choices.length !== 2) {
    failures.push(`${viewport.name}: expected 2 choice cards`);
  }
  const [first, second] = report.choices;
  if (first && second && second.top < first.bottom - 1) {
    failures.push(`${viewport.name}: choice cards overlap or sit side by side`);
  }
  for (const choice of report.choices) {
    if (choice.radioWidth > 28) {
      failures.push(`${viewport.name}: radio stretched to ${choice.radioWidth}px`);
    }
    if (choice.titleWidth < 48) {
      failures.push(
        `${viewport.name}: title squeezed (${choice.titleWidth}px) for ${choice.titleText}`
      );
    }
    if (choice.titleHeight > 40) {
      failures.push(
        `${viewport.name}: title stacked vertically (${choice.titleHeight}px) for ${choice.titleText}`
      );
    }
    if (choice.height > 160) {
      failures.push(`${viewport.name}: choice card is unusually tall (${choice.height}px)`);
    }
    if (Math.abs(choice.width - report.optionsWidth) > 1) {
      failures.push(
        `${viewport.name}: choice card ${choice.width}px != options ${report.optionsWidth}px`
      );
    }
  }
  console.log(
    `${viewport.name}: form=${Math.round(report.formWidth)} cards=${report.choices
      .map((c) => `${Math.round(c.width)}x${Math.round(c.height)}`)
      .join(", ")} titleW=${report.choices.map((c) => Math.round(c.titleWidth)).join("/")}`
  );
}

await browser.close();
if (failures.length) {
  console.error(failures.join("\n"));
  process.exit(1);
}
console.log("event form layout ok");
