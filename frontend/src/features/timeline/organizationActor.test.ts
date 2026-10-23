import assert from "node:assert/strict";
import test from "node:test";
import {
  isDeletedPersonalAuthor,
  isOrganizationTimelinePost,
  ORGANIZATION_KIND_LABEL,
  organizationPostDisplay,
  organizationPostLeaksOperator,
  organizationProfilePath,
} from "./organizationActor.ts";

const org = {
  id: 7,
  name: "Circledancers",
  slug: "circledancers",
  avatar_url: "https://example.com/org.png",
  is_verified: true,
};

test("personal posts keep the existing author identity", () => {
  const post = {
    author: { id: 3, username: "taro", display_name: "太郎" },
  };
  assert.equal(isOrganizationTimelinePost(post), false);
  assert.equal(organizationPostDisplay(post), null);
  assert.equal(isDeletedPersonalAuthor(post), false);
  assert.equal(organizationPostLeaksOperator(post), false);
});

test("deleted personal authors stay deleted, not organization posts", () => {
  const post = { author: null };
  assert.equal(isOrganizationTimelinePost(post), false);
  assert.equal(isDeletedPersonalAuthor(post), true);
  assert.equal(organizationPostDisplay(post), null);
});

test("organization posts use org name, avatar, verified, and profile path", () => {
  const post = {
    actor_type: "organization",
    author: null,
    organization: org,
  };
  assert.equal(isOrganizationTimelinePost(post), true);
  assert.equal(isDeletedPersonalAuthor(post), false);
  const display = organizationPostDisplay(post);
  assert.ok(display);
  assert.equal(display?.name, "Circledancers");
  assert.equal(display?.avatarUrl, org.avatar_url);
  assert.equal(display?.isVerified, true);
  assert.equal(display?.kindLabel, ORGANIZATION_KIND_LABEL);
  assert.equal(display?.href, "/orgs/circledancers");
  assert.equal(display?.initial, "C");
  assert.equal(organizationProfilePath("circledancers"), "/orgs/circledancers");
});

test("organization posts never fall back to operator author fields", () => {
  const post = {
    actor_type: "organization",
    author: { id: 99, username: "operator", display_name: "Secret Operator" },
    organization: org,
  };
  assert.equal(isOrganizationTimelinePost(post), true);
  assert.equal(isDeletedPersonalAuthor(post), false);
  assert.equal(organizationPostLeaksOperator(post), true);
  const display = organizationPostDisplay(post);
  assert.equal(display?.name, "Circledancers");
  assert.notEqual(display?.name, "Secret Operator");
  assert.equal(display?.href, "/orgs/circledancers");
  assert.ok(display?.href && !display.href.includes("/users/"));
});

test("organization actor_type without payload still is not a deleted user", () => {
  const post = { actor_type: "organization", author: null, organization: null };
  assert.equal(isOrganizationTimelinePost(post), true);
  assert.equal(isDeletedPersonalAuthor(post), false);
  const display = organizationPostDisplay(post);
  assert.equal(display?.name, ORGANIZATION_KIND_LABEL);
  assert.equal(display?.href, null);
});
