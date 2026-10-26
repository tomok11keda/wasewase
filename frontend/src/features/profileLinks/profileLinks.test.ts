import assert from "node:assert/strict";
import test from "node:test";
import {
  draftsFromLinks,
  isSafeHttpUrl,
  legacyUrlsFromLinks,
  parseProfileLinks,
  profileLinkDisplayTitle,
  profileLinkHostname,
  profileLinksChipLabel,
  seedLinksFromLegacyUrls,
  serializeLinksForApi,
  validateProfileLinkDrafts,
  visibleProfileLinks,
} from "./profileLinks.ts";

const ig = {
  id: 1,
  title: "Instagram",
  url: "https://instagram.com/example",
  position: 0,
};
const web = {
  id: 2,
  title: "公式Webサイト",
  url: "https://example.com/about",
  position: 1,
};
const extra = {
  id: 3,
  title: "",
  url: "https://forms.google.com/x",
  position: 2,
};

test("0 links stay hidden", () => {
  assert.equal(profileLinksChipLabel([]), null);
  assert.deepEqual(visibleProfileLinks([]), []);
});

test("1 link uses the display name and is a direct href candidate", () => {
  assert.equal(profileLinksChipLabel([ig]), "Instagram");
});

test("2+ links use representative name plus remaining count", () => {
  assert.equal(profileLinksChipLabel([ig, web, extra]), "Instagram 他2件");
});

test("empty title falls back to hostname without www", () => {
  assert.equal(profileLinkDisplayTitle(extra), "forms.google.com");
  assert.equal(profileLinkHostname("https://www.example.com/about"), "example.com");
});

test("parser drops dangerous schemes and keeps at most five", () => {
  const parsed = parseProfileLinks([
    { title: "xss", url: "javascript:alert(1)", position: 0 },
    { title: "ok", url: "https://example.com", position: 1 },
    { title: "data", url: "data:text/html,hi", position: 2 },
    ...Array.from({ length: 6 }, (_, i) => ({
      title: `L${i}`,
      url: `https://example.com/${i}`,
      position: i + 3,
    })),
  ]);
  assert.equal(parsed.length, 5);
  assert.ok(parsed.every((item) => isSafeHttpUrl(item.url)));
  assert.equal(
    parsed.some((item) => item.url.startsWith("javascript:")),
    false
  );
});

test("draft validation rejects a sixth filled url and javascript", () => {
  const drafts = Array.from({ length: 6 }, (_, i) => ({
    clientKey: String(i),
    id: null,
    title: `L${i}`,
    url: `https://example.com/${i}`,
  }));
  assert.ok(validateProfileLinkDrafts(drafts).links);
  assert.ok(
    validateProfileLinkDrafts([
      { clientKey: "x", id: null, title: "xss", url: "javascript:alert(1)" },
    ])["links.0.url"]
  );
});

test("legacy instagram and website seed without duplicating the same url", () => {
  const seeded = seedLinksFromLegacyUrls(
    "https://instagram.com/wasewase",
    "https://instagram.com/wasewase"
  );
  assert.equal(seeded.length, 1);
  assert.equal(seeded[0].title, "Instagram");
});

test("saving drafts derives instagram then website columns", () => {
  const drafts = draftsFromLinks([ig, web, extra]);
  const payload = serializeLinksForApi(drafts);
  assert.equal(payload[0].position, 0);
  assert.deepEqual(legacyUrlsFromLinks(drafts), {
    instagram_url: "https://instagram.com/example",
    website_url: "https://example.com/about",
  });
});
