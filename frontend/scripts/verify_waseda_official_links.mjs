/**
 * Targeted checks for the single Waseda official-service shortcut in the SPA menu.
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

const href = "https://my.waseda.jp/";
const label = "早稲田大学サービス";
const note = "MyWaseda・Moodle・成績照会";

assert.match(linksSrc, /WASEDA_OFFICIAL_SERVICE/);
assert.match(linksSrc, new RegExp(`label: "${label}"`));
assert.match(linksSrc, new RegExp(`note: "${note}"`));
assert.match(
  linksSrc,
  new RegExp(`href: "${href.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}"`),
);
assert.doesNotMatch(linksSrc, /WASEDA_OFFICIAL_LINKS/);
assert.doesNotMatch(linksSrc, /wsdmoodle\.waseda\.jp/);
assert.doesNotMatch(linksSrc, /coursereg\.waseda\.jp/);
assert.doesNotMatch(linksSrc, /login\/login/);

assert.match(menuSrc, /大学サービス/);
assert.match(menuSrc, /WASEDA_OFFICIAL_SERVICE/);
assert.match(menuSrc, /WASEDA_OFFICIAL_SERVICE\.label/);
assert.match(menuSrc, /WASEDA_OFFICIAL_SERVICE\.note/);
assert.match(menuSrc, /WASEDA_OFFICIAL_SERVICE\.href/);
assert.match(menuSrc, /more-link-copy/);
assert.match(menuSrc, /target="_blank"/);
assert.match(menuSrc, /rel="noopener noreferrer"/);
assert.match(menuSrc, /OfficialExternalLink/);
assert.doesNotMatch(menuSrc, /\.map\(/);
assert.doesNotMatch(menuSrc, /window\.open/);
assert.doesNotMatch(menuSrc, /Browser\.open/);
assert.doesNotMatch(menuSrc, /AppLauncher/);
assert.doesNotMatch(menuSrc, /eval\(/);
assert.doesNotMatch(menuSrc, /type=["']password["']/);
assert.doesNotMatch(menuSrc, /localStorage/);
assert.doesNotMatch(menuSrc, /sessionStorage/);
assert.doesNotMatch(menuSrc, /to=\{WASEDA_OFFICIAL_SERVICE\.href\}/);
assert.doesNotMatch(menuSrc, /navigate\(WASEDA_OFFICIAL_SERVICE\.href\)/);

const httpsHrefs = [...linksSrc.matchAll(/href: "(https:[^"]+)"/g)].map(
  (m) => m[1],
);
assert.equal(httpsHrefs.length, 1);
assert.equal(httpsHrefs[0], href);

console.log("verify_waseda_official_links: ok");
console.log(`${label} (${note}) -> ${href}`);
