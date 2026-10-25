import assert from "node:assert/strict";
import test from "node:test";
import {
  firstFieldError,
  formFromOwnProfile,
  isOwnProfileFormDirty,
  parseOwnProfilePayload,
  validateOwnProfileForm,
} from "./meProfile.ts";

const profile = {
  id: 7,
  username: "tanaka_taro",
  name: "田中",
  display_name: "田中",
  bio: "こんにちは",
  avatar_url: "",
  initial: "田",
  department: "商学部",
  grade: "3年",
  department_grade: "商学部 3年",
};

test("own profile payload parser keeps editable fields and ignores email", () => {
  const parsed = parseOwnProfilePayload({
    ok: true,
    profile: { ...profile, email: "hidden@waseda.jp" },
    choices: {
      department: [{ value: "商学部", label: "商学部" }],
      grade: [{ value: "3年", label: "3年" }],
    },
  });
  assert.equal(parsed?.profile.name, "田中");
  assert.equal(parsed?.profile.username, "tanaka_taro");
  assert.equal("email" in (parsed?.profile || {}), false);
  assert.equal(parsed?.choices.department[0]?.value, "商学部");
  assert.equal(parseOwnProfilePayload({ ok: false }), null);
});

test("own profile form validation matches handle rules", () => {
  const valid = formFromOwnProfile(profile);
  assert.deepEqual(validateOwnProfileForm(valid), {});
  assert.ok(validateOwnProfileForm({ ...valid, user_id: "ab" }).user_id);
  assert.ok(validateOwnProfileForm({ ...valid, user_id: "" }).user_id);
  assert.ok(validateOwnProfileForm({ ...valid, user_id: "bad name" }).user_id);
});

test("dirty detection keeps drafts across failed saves", () => {
  const original = formFromOwnProfile(profile);
  assert.equal(isOwnProfileFormDirty(original, original, null), false);
  assert.equal(
    isOwnProfileFormDirty({ ...original, bio: "下書き" }, original, null),
    true
  );
  assert.equal(
    isOwnProfileFormDirty(original, original, { name: "x.png" } as File),
    true
  );
});

test("failed save field errors keep the first message", () => {
  assert.deepEqual(
    firstFieldError({
      user_id: ["このユーザー名は使われています。", "二件目"],
      bio: "長すぎます",
    }),
    {
      user_id: "このユーザー名は使われています。",
      bio: "長すぎます",
    }
  );
});
