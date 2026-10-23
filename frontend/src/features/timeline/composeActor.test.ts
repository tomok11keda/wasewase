import assert from "node:assert/strict";
import test from "node:test";
import {
  composeActorKey,
  composeActorLabel,
  composeActorsEqual,
  composeModeCaption,
  organizationIdForCompose,
  snapshotComposeActor,
} from "./composeActor.ts";

const org = {
  type: "organization" as const,
  organization: {
    id: 7,
    name: "チームわせわせ",
    slug: "team-wasewase",
    avatar_url: "https://example.com/org.png",
    is_verified: true,
  },
};

test("personal mode never sends organization_id", () => {
  const actor = snapshotComposeActor({ type: "personal" });
  assert.equal(actor.type, "personal");
  assert.equal(organizationIdForCompose(actor), null);
  assert.equal(composeModeCaption(actor), "個人アカウントとして投稿");
  assert.equal(composeActorLabel(actor), "個人アカウント");
});

test("organization mode snapshots name and sends organization_id", () => {
  const actor = snapshotComposeActor(org);
  assert.equal(actor.type, "organization");
  assert.equal(organizationIdForCompose(actor), 7);
  assert.equal(composeModeCaption(actor), "学生団体として投稿");
  assert.equal(composeActorLabel(actor), "チームわせわせ");
  assert.equal(composeActorKey(actor), "organization:7");
});

test("switching accounts is detected without silently changing the send actor", () => {
  const started = snapshotComposeActor(org);
  const live = snapshotComposeActor({ type: "personal" });
  assert.equal(composeActorsEqual(started, live), false);
  assert.equal(organizationIdForCompose(started), 7);
  assert.equal(organizationIdForCompose(live), null);
});

test("failed organization compose must not fall back to a personal organization_id", () => {
  const started = snapshotComposeActor(org);
  assert.notEqual(organizationIdForCompose(started), null);
  assert.equal(organizationIdForCompose({ type: "personal" }), null);
});

test("403/404 and network failure still use the snapped organization_id", () => {
  const started = snapshotComposeActor(org);
  const afterForbidden = started;
  const afterNotFound = started;
  const afterNetworkError = started;
  assert.equal(organizationIdForCompose(afterForbidden), 7);
  assert.equal(organizationIdForCompose(afterNotFound), 7);
  assert.equal(organizationIdForCompose(afterNetworkError), 7);
  assert.equal(organizationIdForCompose({ type: "personal" }), null);
});
