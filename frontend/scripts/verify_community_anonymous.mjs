/**
 * Static check: Community SPA surfaces must not render author identity.
 * Usage: node scripts/verify_community_anonymous.mjs
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const hint = "ユーザー番号はスレッドごとに変わります";

const files = [
  "src/pages/CommunitiesPage.tsx",
  "src/pages/CommunityThreadPage.tsx",
  "src/features/community/api.ts",
  "src/features/community/CommunityReportMenu.tsx",
  "src/features/search/DiscoverCompactCards.tsx",
];

const forbidden = [
  { re: /thread\.author/, msg: "thread.author identity" },
  { re: /reply\.author/, msg: "reply.author identity" },
  { re: /\/users\/\$\{.*author/, msg: "author profile link" },
  { re: /avatar_url/, msg: "avatar_url" },
  { re: /display_name/, msg: "display_name" },
  { re: /username/, msg: "username" },
];

let failed = false;
for (const rel of files) {
  const abs = path.join(root, rel);
  const text = fs.readFileSync(abs, "utf8");
  if (rel.endsWith("CommunityThreadPage.tsx") || rel.endsWith("CommunitiesPage.tsx")) {
    if (!text.includes("anonymous_label") && !text.includes("participantLabel")) {
      console.error(`${rel}: missing thread-local participant label`);
      failed = true;
    }
    if (!text.includes(hint) && !text.includes("COMMUNITY_ANON_HINT")) {
      console.error(`${rel}: missing thread-local number hint`);
      failed = true;
    }
    if (text.includes("AuthorAvatar") || text.includes("forum-post__avatar")) {
      console.error(`${rel}: avatar/profile identity UI remains`);
      failed = true;
    }
  }
  if (rel.endsWith("DiscoverCompactCards.tsx")) {
    const fn = text.slice(text.indexOf("export function DiscoverThreadCard"));
    const end = fn.indexOf("export function DiscoverProductCard");
    const block = end >= 0 ? fn.slice(0, end) : fn;
    if (block.includes("thread.author")) {
      console.error(`${rel}: DiscoverThreadCard still uses thread.author`);
      failed = true;
    }
    if (!block.includes("anonymous_label") && !block.includes("participantLabel")) {
      console.error(`${rel}: DiscoverThreadCard missing participant label`);
      failed = true;
    }
    continue;
  }
  for (const { re, msg } of forbidden) {
    if (re.test(text)) {
      console.error(`${rel}: leaked ${msg}`);
      failed = true;
    }
  }
}

const searchPage = fs.readFileSync(path.join(root, "src/pages/SearchPage.tsx"), "utf8");
const searchFn = searchPage.slice(searchPage.indexOf("function SearchThreadCard"));
const searchEnd = searchFn.indexOf("function SearchProductCard");
const searchBlock = searchEnd >= 0 ? searchFn.slice(0, searchEnd) : searchFn;
if (searchBlock.includes("thread.author") || searchBlock.includes("authorName")) {
  console.error("SearchPage.tsx: SearchThreadCard still uses author identity");
  failed = true;
}
if (!searchBlock.includes("anonymous_label") && !searchBlock.includes("participantLabel")) {
  console.error("SearchPage.tsx: SearchThreadCard missing participant label");
  failed = true;
}

if (failed) {
  process.exit(1);
}
console.log("community anonymous UI checks passed");
