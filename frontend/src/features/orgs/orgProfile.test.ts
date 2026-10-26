import assert from "node:assert/strict";
import test from "node:test";
import {
  formFromOrganization,
  isSafeHttpUrl,
  organizationCategoryLabel,
  organizationExternalHref,
  organizationInitial,
  parseOrganizationProfilePayload,
  validateOrganizationAvatar,
  validateOrganizationProfileForm,
} from "./orgProfile.ts";

test("category labels stay independent of personal verification", () => {
  assert.equal(organizationCategoryLabel("circle"), "サークル");
  assert.equal(organizationCategoryLabel("project"), "プロジェクト");
});

test("organization initial uses the first character", () => {
  assert.equal(organizationInitial("チームわせわせ"), "チ");
  assert.equal(organizationInitial("  "), "?");
});

test("external links only allow http(s)", () => {
  assert.equal(isSafeHttpUrl("https://example.com"), true);
  assert.equal(isSafeHttpUrl("javascript:alert(1)"), false);
  assert.equal(organizationExternalHref("javascript:alert(1)"), null);
  assert.equal(
    organizationExternalHref("https://instagram.com/wasewase"),
    "https://instagram.com/wasewase"
  );
});

test("form validation rejects empty name and bad urls", () => {
  const errors = validateOrganizationProfileForm({
    name: "   ",
    description: "ok",
    category: "faculty",
    instagram_url: "not-a-url",
    website_url: "javascript:alert(1)",
    links: [],
  });
  assert.ok(errors.name);
  assert.ok(errors.category);
  assert.ok(errors.instagram_url);
  assert.ok(errors.website_url);
});

test("form validation accepts a complete public profile", () => {
  const errors = validateOrganizationProfileForm({
    name: "公開サークル",
    description: "紹介文",
    category: "circle",
    instagram_url: "",
    website_url: "https://example.com",
    links: [],
  });
  assert.deepEqual(errors, {});
});

test("avatar validation rejects oversize and heic", () => {
  const heic = new File(["abc"], "icon.heic", { type: "image/heic" });
  assert.match(String(validateOrganizationAvatar(heic)), /HEIC/);
  const huge = new File([new Uint8Array(5 * 1024 * 1024 + 1)], "big.jpg", {
    type: "image/jpeg",
  });
  assert.match(String(validateOrganizationAvatar(huge)), /5MB/);
});

test("payload parser ignores manager emails and requires public fields", () => {
  const parsed = parseOrganizationProfilePayload({
    ok: true,
    organization: {
      id: 3,
      name: "公開サークル",
      slug: "listed-circle",
      description: "紹介",
      avatar_url: "",
      category: "circle",
      instagram_url: "",
      website_url: "",
      is_verified: true,
    },
    can_manage: true,
    my_role: "owner",
    email: "owner@waseda.jp",
  });
  assert.ok(parsed);
  assert.equal(parsed?.organization.is_verified, true);
  assert.equal(parsed?.can_manage, true);
  assert.equal(parsed?.recruiting_chat, null);
  assert.equal("email" in parsed!.organization, false);
  assert.equal(parseOrganizationProfilePayload({ ok: true }), null);
});

test("payload parser reads recruiting_chat summary without emails", () => {
  const parsed = parseOrganizationProfilePayload({
    ok: true,
    organization: {
      id: 3,
      name: "公開サークル",
      slug: "listed-circle",
      description: "紹介",
      avatar_url: "",
      category: "circle",
      instagram_url: "",
      website_url: "",
      is_verified: true,
    },
    can_manage: false,
    my_role: null,
    recruiting_chat: {
      id: 9,
      name: "2026新歓チャット",
      join_mode: "approval",
      listing_status: "open",
      membership_status: "pending",
      can_join: false,
      can_apply: false,
      can_manage: false,
      room_id: null,
      member_count: 12,
    },
  });
  assert.equal(parsed?.recruiting_chat?.name, "2026新歓チャット");
  assert.equal(parsed?.recruiting_chat?.membership_status, "pending");
  assert.equal(parsed?.recruiting_chat?.room_id, null);
});

test("payload parser does not resurrect leftover columns when links is empty", () => {
  const parsed = parseOrganizationProfilePayload({
    ok: true,
    organization: {
      id: 3,
      name: "公開サークル",
      slug: "listed-circle",
      description: "紹介",
      avatar_url: "",
      category: "circle",
      instagram_url: "https://instagram.com/stale",
      website_url: "https://stale.example",
      is_verified: true,
      links: [],
    },
    can_manage: true,
    my_role: "owner",
  });
  assert.deepEqual(parsed?.organization.links, []);
});

test("payload parser seeds legacy urls only when links key is missing", () => {
  const parsed = parseOrganizationProfilePayload({
    ok: true,
    organization: {
      id: 3,
      name: "公開サークル",
      slug: "listed-circle",
      description: "紹介",
      avatar_url: "",
      category: "circle",
      instagram_url: "https://instagram.com/legacy",
      website_url: "https://legacy.example",
      is_verified: true,
    },
    can_manage: true,
    my_role: "owner",
  });
  assert.equal(parsed?.organization.links.length, 2);
  assert.equal(parsed?.organization.links[0].url, "https://instagram.com/legacy");
  assert.equal(parsed?.organization.links[1].url, "https://legacy.example");
});

test("edit form snapshot does not include slug or status", () => {
  const form = formFromOrganization({
    id: 1,
    name: "公開サークル",
    slug: "listed-circle",
    description: "",
    avatar_url: "",
    category: "circle",
    instagram_url: "",
    website_url: "",
    is_verified: true,
    links: [],
  });
  assert.equal("slug" in form, false);
  assert.equal("status" in form, false);
  assert.equal("is_verified" in form, false);
});
