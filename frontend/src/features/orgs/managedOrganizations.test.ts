import assert from "node:assert/strict";
import test from "node:test";
import {
  clearStoredOrganizationId,
  dedupeManagedOrganizations,
  ORG_CHAT_PICK_LEAD,
  organizationRoleLabel,
  organizationStorageKey,
  organizationsForChatPick,
  parseManagedOrganizationsPayload,
  readStoredOrganizationId,
  resolveActiveOrganization,
  writeStoredOrganizationId,
} from "./managedOrganizations.ts";

const sample = {
  id: 7,
  name: "チームわせわせ",
  slug: "team-wasewase",
  avatar_url: "",
  is_verified: true,
  my_role: "owner",
  can_manage: true,
};

test("parses a minimal managed-organization list", () => {
  const parsed = parseManagedOrganizationsPayload({
    ok: true,
    organizations: [sample],
  });
  assert.deepEqual(parsed, [sample]);
});

test("rejects member-like or unmanageable rows", () => {
  assert.equal(
    parseManagedOrganizationsPayload({
      ok: true,
      organizations: [{ ...sample, my_role: "member" }],
    }),
    null
  );
  assert.equal(
    parseManagedOrganizationsPayload({
      ok: true,
      organizations: [{ ...sample, can_manage: false }],
    }),
    null
  );
});

test("rejects extra fields so personal data cannot sneak in", () => {
  assert.equal(
    parseManagedOrganizationsPayload({
      ok: true,
      organizations: [{ ...sample, email: "owner@waseda.jp" }],
    }),
    null
  );
});

test("role labels distinguish owner and admin", () => {
  assert.equal(organizationRoleLabel("owner"), "代表管理者");
  assert.equal(organizationRoleLabel("admin"), "管理者");
});

test("duplicate organization ids collapse to one row and prefer owner", () => {
  const adminRow = { ...sample, my_role: "admin" };
  const ownerRow = { ...sample, my_role: "owner" };
  const other = {
    ...sample,
    id: 9,
    slug: "other",
    name: "別団体",
    my_role: "admin",
  };
  const parsed = parseManagedOrganizationsPayload({
    ok: true,
    organizations: [adminRow, ownerRow, other, adminRow],
  });
  assert.deepEqual(parsed, [ownerRow, other]);
  assert.deepEqual(
    dedupeManagedOrganizations([adminRow, { ...adminRow, my_role: "owner" }]),
    [ownerRow]
  );
});

test("chat pick list keeps distinct organizations and marks the current one first", () => {
  const other = {
    ...sample,
    id: 9,
    slug: "other",
    name: "あ別団体",
    my_role: "admin",
  };
  const list = organizationsForChatPick(
    [other, { ...sample, my_role: "admin" }, sample],
    sample.id
  );
  assert.equal(list.length, 2);
  assert.equal(list[0]?.id, sample.id);
  assert.equal(list[0]?.my_role, "owner");
  assert.equal(list[1]?.id, other.id);
  assert.equal(ORG_CHAT_PICK_LEAD.includes("複数の団体チャット"), true);
  assert.equal(ORG_CHAT_PICK_LEAD.includes("有効な団体チャットがあれば開きます"), false);
});

test("stored id is restored only when the list confirms can_manage", () => {
  const orgs = [
    sample,
    { ...sample, id: 9, slug: "other", my_role: "admin", name: "別団体" },
  ];
  assert.equal(resolveActiveOrganization(orgs, 9, true)?.slug, "other");
  assert.equal(resolveActiveOrganization(orgs, 9, false), null);
  assert.equal(resolveActiveOrganization(orgs, 99, true), null);
  assert.equal(resolveActiveOrganization([], 7, true), null);
  assert.equal(resolveActiveOrganization(orgs, 7, false), null);
});

test("localStorage keys are scoped per user id", () => {
  const memory = new Map<string, string>();
  const fake = {
    getItem: (key: string) => memory.get(key) ?? null,
    setItem: (key: string, value: string) => {
      memory.set(key, value);
    },
    removeItem: (key: string) => {
      memory.delete(key);
    },
  };
  const previous = globalThis.localStorage;
  Object.defineProperty(globalThis, "localStorage", {
    configurable: true,
    value: fake,
  });
  try {
    writeStoredOrganizationId(1, 7);
    writeStoredOrganizationId(2, 9);
    assert.equal(readStoredOrganizationId(1), 7);
    assert.equal(readStoredOrganizationId(2), 9);
    assert.equal(organizationStorageKey(1), "wase_active_organization:1");
    clearStoredOrganizationId(1);
    assert.equal(readStoredOrganizationId(1), null);
    assert.equal(readStoredOrganizationId(2), 9);
  } finally {
    Object.defineProperty(globalThis, "localStorage", {
      configurable: true,
      value: previous,
    });
  }
});
