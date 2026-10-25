import assert from "node:assert/strict";
import test from "node:test";
import {
  composeNoticeForOrganizationPost,
  DEFAULT_ORGANIZATION_COMPOSE_VISIBILITY,
  isPublicOrganizationPost,
  isUnpublishedOrganizationPost,
  organizationPostVisibilityLabel,
} from "./organizationPostVisibility.ts";

const orgPost = {
  actor_type: "organization" as const,
  organization: { id: 7, name: "チームわせわせ" },
};

test("new organization compose defaults to draft", () => {
  assert.equal(DEFAULT_ORGANIZATION_COMPOSE_VISIBILITY, "draft");
  assert.notEqual(DEFAULT_ORGANIZATION_COMPOSE_VISIBILITY, "public");
});

test("public organization posts are listed, drafts are not", () => {
  assert.equal(
    isPublicOrganizationPost({ ...orgPost, visibility: "public" }),
    true
  );
  assert.equal(
    isUnpublishedOrganizationPost({ ...orgPost, visibility: "draft" }),
    true
  );
  assert.equal(
    isUnpublishedOrganizationPost({ ...orgPost, visibility: "unlisted" }),
    true
  );
  assert.equal(
    isUnpublishedOrganizationPost({
      ...orgPost,
      visibility: "organization_preview",
    }),
    true
  );
  assert.equal(
    isUnpublishedOrganizationPost({
      author: { id: 1, username: "taro", display_name: "太郎" },
      visibility: "draft",
    }),
    false
  );
});

test("visibility labels stay explicit for managers", () => {
  assert.equal(organizationPostVisibilityLabel("public"), "公開");
  assert.equal(organizationPostVisibilityLabel("draft"), "下書き");
  assert.equal(organizationPostVisibilityLabel("unlisted"), "非公開");
});

test("compose success copy distinguishes public and draft", () => {
  assert.match(
    composeNoticeForOrganizationPost({
      unpublished: true,
      organizationName: "チームわせわせ",
    }),
    /下書き/
  );
  assert.match(
    composeNoticeForOrganizationPost({
      unpublished: false,
      organizationName: "チームわせわせ",
    }),
    /公開/
  );
});
