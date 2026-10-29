import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

const root = dirname(fileURLToPath(import.meta.url));
const card = readFileSync(join(root, "TimelinePostCard.tsx"), "utf8");
const eventCard = readFileSync(join(root, "TimelineOrgEventShareCard.tsx"), "utf8");
const home = readFileSync(join(root, "../../pages/HomePage.tsx"), "utf8");
const search = readFileSync(join(root, "../../pages/SearchPage.tsx"), "utf8");

test("feed and search cards render a live event share without dropping org posts", () => {
  assert.equal(card.includes("TimelineOrgEventShareCard"), true);
  assert.equal(card.includes("post.shared_organization_event"), true);
  assert.equal(home.includes("visiblePosts.map"), true);
  assert.equal(home.includes("visiblePosts.filter"), false);
  assert.equal(home.includes("setPosts(data.posts)"), true);
  assert.equal(search.includes("kind === \"post\""), true);
  assert.equal(search.includes("TimelinePostCard"), true);
});

test("event share card links to the event detail path", () => {
  assert.equal(eventCard.includes("イベントを見る"), true);
  assert.equal(eventCard.includes("event.path"), true);
  assert.equal(eventCard.includes("/organizations/${event.organization_slug}/events/${event.id}"), true);
  assert.equal(eventCard.includes("event.image_url"), true);
  assert.equal(eventCard.includes("event.title"), true);
});

test("home latest fetch does not re-apply leftover faculty or q filters", () => {
  assert.equal(home.includes("faculty: faculty || undefined"), false);
  assert.equal(home.includes("q: qParam || undefined"), false);
  assert.equal(home.includes("stripHomeTimelineLeftoverParams"), true);
  assert.equal(home.includes("location.pathname"), true);
  assert.equal(home.includes("sort: HOME_TIMELINE_SORT"), true);
});
