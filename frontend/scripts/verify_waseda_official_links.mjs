/**
 * Targeted checks for Waseda official-service shortcuts in the SPA menu.
 * Usage: node scripts/verify_waseda_official_links.mjs
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const linksPath = join(root, "src/lib/wasedaOfficialLinks.ts");
const menuPath = join(root, "src/components/AccountMenuContent.tsx");

const linksSrc = readFileSync(linksPath, "utf8");
const menuSrc = readFileSync(menuPath, "utf8");

const expected = [
  { id: "mywaseda", label: "MyWaseda", href: "https://my.waseda.jp/" },
  {
    id: "moodle",
    label: "Waseda Moodle",
    href: "https://wsdmoodle.waseda.jp/",
  },
  {
    id: "grades",
    label: "成績照会",
    href: "https://my.waseda.jp/login/login",
  },
];

for (const item of expected) {
  assert.match(linksSrc, new RegExp(`id: "${item.id}"`));
  assert.match(linksSrc, new RegExp(`label: "${item.label}"`));
  assert.match(
    linksSrc,
    new RegExp(`href: "${item.href.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}"`),
  );
}

assert.match(menuSrc, /大学サービス/);
assert.match(menuSrc, /WASEDA_OFFICIAL_LINKS/);
assert.match(menuSrc, /\{item\.label\}/);
assert.match(menuSrc, /href=\{item\.href\}/);
assert.match(menuSrc, /target="_blank"/);
assert.match(menuSrc, /rel="noopener noreferrer"/);
assert.match(menuSrc, /OfficialExternalLink/);
assert.doesNotMatch(menuSrc, /window\.open/);
assert.doesNotMatch(menuSrc, /Browser\.open/);
assert.doesNotMatch(menuSrc, /AppLauncher/);
assert.doesNotMatch(menuSrc, /eval\(/);
assert.doesNotMatch(menuSrc, /type=["']password["']/);
assert.doesNotMatch(menuSrc, /localStorage/);
assert.doesNotMatch(menuSrc, /sessionStorage/);
assert.doesNotMatch(menuSrc, /to=\{item\.href\}/);
assert.doesNotMatch(menuSrc, /navigate\(item\.href\)/);

const httpsHrefs = [...linksSrc.matchAll(/href: "(https:[^"]+)"/g)].map(
  (m) => m[1],
);
assert.equal(httpsHrefs.length, 3);
for (const href of httpsHrefs) {
  assert.ok(href.startsWith("https://"), href);
  assert.ok(!href.includes("wasewase"), href);
}

console.log("verify_waseda_official_links: ok");
console.log(expected.map((item) => `${item.label} -> ${item.href}`).join("\n"));
