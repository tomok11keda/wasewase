import assert from "node:assert/strict";
import test from "node:test";
import {
  markOrgGrantPromptSeen,
  managedOrganizationForGrantSlug,
  ORG_GRANT_LATER_LABEL,
  ORG_GRANT_MISSING_GUIDANCE,
  ORG_GRANT_PROMPT_STORAGE_PREFIX,
  ORG_GRANT_PROMPT_TITLE,
  ORG_GRANT_SWITCH_LABEL,
  ORG_GRANT_SWITCHER_GUIDANCE,
  orgGrantGuidanceMessage,
  orgGrantPromptStorageKey,
  orgGrantSlugFromNotification,
  parseOrgGrantLocation,
  pickUnseenOrgGrantNotification,
  readSeenOrgGrantNotificationIds,
  shouldShowOrganizationGrantPrompt,
  stripOrgGrantSearch,
} from "./orgGrantPrompt.ts";

const org = { slug: "wase-circle", can_manage: true };

test("grant query is read from org profile paths only", () => {
  assert.deepEqual(parseOrgGrantLocation("/orgs/wase-circle", "?org_grant=1"), {
    slug: "wase-circle",
  });
  assert.deepEqual(
    parseOrgGrantLocation("/organizations/wase-circle/", "org_grant=1"),
    { slug: "wase-circle" }
  );
  assert.equal(parseOrgGrantLocation("/orgs/wase-circle", ""), null);
  assert.equal(
    parseOrgGrantLocation("/orgs/wase-circle/edit", "?org_grant=1"),
    null
  );
  assert.equal(parseOrgGrantLocation("/", "?org_grant=1"), null);
});

test("notification links keep the org slug even with /app prefix", () => {
  assert.equal(
    orgGrantSlugFromNotification({
      spa_path: "/orgs/wase-circle?org_grant=1",
      link: "",
    }),
    "wase-circle"
  );
  assert.equal(
    orgGrantSlugFromNotification({
      spa_path: "",
      link: "/app/orgs/wase-circle?org_grant=1",
    }),
    "wase-circle"
  );
  assert.equal(
    orgGrantSlugFromNotification({
      spa_path: "/orgs/wase-circle",
      link: "/orgs/wase-circle",
    }),
    null
  );
});

test("unseen grant picker skips already prompted ids and non-grant rows", () => {
  const picked = pickUnseenOrgGrantNotification(
    [
      {
        id: 4,
        spa_path: "/posts/1",
        link: "/posts/1",
      },
      {
        id: 5,
        spa_path: "/orgs/old?org_grant=1",
        link: "/orgs/old?org_grant=1",
      },
      {
        id: 6,
        spa_path: "/orgs/new?org_grant=1",
        link: "/orgs/new?org_grant=1",
      },
    ],
    [5]
  );
  assert.deepEqual(picked, { id: 6, slug: "new" });
});

test("あとで persists across restart and does not switch a revoked org", () => {
  const items = [
    {
      id: 5,
      spa_path: "/orgs/wase-circle?org_grant=1",
      link: "/orgs/wase-circle?org_grant=1",
    },
  ];
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
    markOrgGrantPromptSeen(11, 5);
    const seenAfterRestart = readSeenOrgGrantNotificationIds(11);
    assert.deepEqual(seenAfterRestart, [5]);
    assert.deepEqual(
      pickUnseenOrgGrantNotification(items, seenAfterRestart),
      null
    );
  } finally {
    Object.defineProperty(globalThis, "localStorage", {
      configurable: true,
      value: previous,
    });
  }
  assert.equal(
    managedOrganizationForGrantSlug(
      [{ slug: "wase-circle", can_manage: false }],
      "wase-circle"
    ),
    null
  );
  assert.equal(managedOrganizationForGrantSlug([], "wase-circle"), null);
  assert.equal(orgGrantGuidanceMessage(false), ORG_GRANT_MISSING_GUIDANCE);
});

test("prompt stays off until a managed org matches and the user is in-app", () => {
  const unseen = { id: 9, slug: "wase-circle" };
  const base = {
    authenticated: true,
    onboardingRequired: false,
    pathname: "/",
    organizationsLoading: false,
    organizations: [org],
    activeOrganizationSlug: null,
    unseen,
    handlingGrantLocation: false,
  };
  assert.equal(shouldShowOrganizationGrantPrompt(base), true);
  assert.equal(
    shouldShowOrganizationGrantPrompt({ ...base, authenticated: false }),
    false
  );
  assert.equal(
    shouldShowOrganizationGrantPrompt({ ...base, pathname: "/login" }),
    false
  );
  assert.equal(
    shouldShowOrganizationGrantPrompt({ ...base, organizationsLoading: true }),
    false
  );
  assert.equal(
    shouldShowOrganizationGrantPrompt({
      ...base,
      activeOrganizationSlug: "wase-circle",
    }),
    false
  );
  assert.equal(
    shouldShowOrganizationGrantPrompt({
      ...base,
      organizations: [{ slug: "wase-circle", can_manage: false }],
    }),
    false
  );
  assert.equal(
    shouldShowOrganizationGrantPrompt({ ...base, handlingGrantLocation: true }),
    false
  );
  assert.equal(
    managedOrganizationForGrantSlug([org], "missing"),
    null
  );
});

test("popup copy and tap guidance stay on the existing switcher", () => {
  assert.equal(ORG_GRANT_PROMPT_TITLE, "団体アカウントが追加されました！");
  assert.equal(ORG_GRANT_SWITCH_LABEL, "団体アカウントに切り替える");
  assert.equal(ORG_GRANT_LATER_LABEL, "あとで");
  assert.equal(orgGrantGuidanceMessage(true), ORG_GRANT_SWITCHER_GUIDANCE);
  assert.equal(orgGrantGuidanceMessage(false), ORG_GRANT_MISSING_GUIDANCE);
  assert.equal(stripOrgGrantSearch("?org_grant=1&x=1"), "?x=1");
  assert.equal(stripOrgGrantSearch("?org_grant=1"), "");
});

test("prompt seen ids are stored per user and do not mark notifications read", () => {
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
    markOrgGrantPromptSeen(11, 5);
    markOrgGrantPromptSeen(11, 5);
    markOrgGrantPromptSeen(22, 8);
    assert.deepEqual(readSeenOrgGrantNotificationIds(11), [5]);
    assert.deepEqual(readSeenOrgGrantNotificationIds(22), [8]);
    assert.equal(
      orgGrantPromptStorageKey(11),
      `${ORG_GRANT_PROMPT_STORAGE_PREFIX}11`
    );
  } finally {
    Object.defineProperty(globalThis, "localStorage", {
      configurable: true,
      value: previous,
    });
  }
});
