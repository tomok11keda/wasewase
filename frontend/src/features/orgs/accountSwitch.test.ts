import assert from "node:assert/strict";
import test from "node:test";
import {
  accountSwitchMessage,
  organizationEditSlug,
  shouldLeaveOrganizationEdit,
} from "./accountSwitch.ts";

test("detects organization edit paths only", () => {
  assert.equal(organizationEditSlug("/orgs/team-wasewase/edit"), "team-wasewase");
  assert.equal(organizationEditSlug("/orgs/team-wasewase/edit/"), "team-wasewase");
  assert.equal(organizationEditSlug("/orgs/team-wasewase"), null);
  assert.equal(organizationEditSlug("/"), null);
  assert.equal(organizationEditSlug("/search"), null);
  assert.equal(organizationEditSlug("/users/1/posts"), null);
});

test("leaves edit page when switching away from that organization", () => {
  assert.equal(
    shouldLeaveOrganizationEdit("/orgs/team-wasewase/edit", null),
    true
  );
  assert.equal(
    shouldLeaveOrganizationEdit("/orgs/team-wasewase/edit", "other-org"),
    true
  );
  assert.equal(
    shouldLeaveOrganizationEdit("/orgs/team-wasewase/edit", "team-wasewase"),
    false
  );
  assert.equal(shouldLeaveOrganizationEdit("/", "team-wasewase"), false);
  assert.equal(shouldLeaveOrganizationEdit("/search", null), false);
});

test("toast copy names the selected account", () => {
  assert.equal(
    accountSwitchMessage("チームわせわせ"),
    "チームわせわせに切り替えました"
  );
  assert.equal(
    accountSwitchMessage("個人アカウント"),
    "個人アカウントに切り替えました"
  );
});
