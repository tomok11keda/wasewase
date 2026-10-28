import assert from "node:assert/strict";
import test from "node:test";
import { createElement } from "react";
import { createMemoryRouter, type NavigateFunction } from "react-router-dom";
import {
  CONVERSATION_BACK_STATE_KEY,
  createConversationBackController,
  isSafeConversationBackOrigin,
} from "./conversationBack.ts";

function Blank() {
  return createElement("div");
}

function routes() {
  return [
    { path: "/", Component: Blank },
    { path: "/dm", Component: Blank },
    { path: "/dm/:id", Component: Blank },
    { path: "/dm/groups/:id", Component: Blank },
    { path: "/notifications", Component: Blank },
    { path: "/courses/:id", Component: Blank },
    { path: "/courses/:id/talk", Component: Blank },
    { path: "/flea/chats/:id", Component: Blank },
    { path: "/organizations/:slug/recruiting-chat", Component: Blank },
    { path: "/login", Component: Blank },
  ];
}

function routerAt(path: string) {
  return createMemoryRouter(routes(), { initialEntries: [path] });
}

async function push(
  router: ReturnType<typeof createMemoryRouter>,
  to: string,
  session: ReturnType<typeof createConversationBackController>
) {
  const from = router.state.location;
  await router.navigate(to, { state: session.withState(from) });
}

async function conversationBack(
  router: ReturnType<typeof createMemoryRouter>,
  session: ReturnType<typeof createConversationBackController>,
  fallback: string
) {
  const dest = session.resolve(router.state.location.state, fallback);
  if (dest.mode === "history") {
    await router.navigate(-1);
    return dest;
  }
  await router.navigate(dest.to, { replace: true });
  return dest;
}

test("safe origins exclude login and onboarding, keep tabs and inbox", () => {
  assert.equal(isSafeConversationBackOrigin("/"), true);
  assert.equal(isSafeConversationBackOrigin("/dm"), true);
  assert.equal(isSafeConversationBackOrigin("/dm?tab=course"), true);
  assert.equal(isSafeConversationBackOrigin("/notifications"), true);
  assert.equal(isSafeConversationBackOrigin("/courses/8"), true);
  assert.equal(isSafeConversationBackOrigin("/login"), false);
  assert.equal(isSafeConversationBackOrigin("/login?next=%2Fapp%2Fdm%2F1"), false);
  assert.equal(isSafeConversationBackOrigin("/onboarding"), false);
  assert.equal(isSafeConversationBackOrigin("/signup"), false);
});

test("missing, stale, or auth origin metadata cannot pop", () => {
  const live = createConversationBackController("live");
  const stale = createConversationBackController("stale");
  const fromInbox = { pathname: "/dm", search: "", key: "abc" };

  assert.equal(live.canPop(undefined), false);
  assert.equal(live.canPop({}), false);
  assert.equal(live.canPop(stale.withState(fromInbox)), false);
  assert.equal(
    live.canPop({
      [CONVERSATION_BACK_STATE_KEY]: {
        sessionId: "live",
        fromPath: "/login",
        fromKey: "abc",
      },
    }),
    false
  );
  assert.equal(
    live.canPop({
      [CONVERSATION_BACK_STATE_KEY]: {
        sessionId: "live",
        fromPath: "/dm",
        fromKey: "",
      },
    }),
    false
  );
  assert.equal(live.canPop(live.withState(fromInbox)), true);
});

test("reload leftover state from another session replaces to fallback", () => {
  const previous = createConversationBackController("boot-1");
  const reloaded = createConversationBackController("boot-2");
  const leftover = previous.withState({
    pathname: "/dm",
    key: "inbox-key",
  });
  assert.deepEqual(reloaded.resolve(leftover, "/dm"), {
    mode: "path",
    to: "/dm",
    replace: true,
  });
});

test("tab → inbox → personal DM → back → back returns to the tab", async () => {
  const session = createConversationBackController("flow-a");
  const router = routerAt("/");
  await push(router, "/dm", session);
  await push(router, "/dm/4", session);

  const first = await conversationBack(router, session, "/dm");
  assert.equal(first.mode, "history");
  assert.equal(router.state.location.pathname, "/dm");
  assert.equal(router.state.historyAction, "POP");

  await router.navigate(-1);
  assert.equal(router.state.location.pathname, "/");
});

test("tab → inbox → group DM → back → back returns to the tab", async () => {
  const session = createConversationBackController("flow-b");
  const router = routerAt("/");
  await push(router, "/dm", session);
  await push(router, "/dm/groups/12", session);

  await conversationBack(router, session, "/dm");
  assert.equal(router.state.location.pathname, "/dm");
  await router.navigate(-1);
  assert.equal(router.state.location.pathname, "/");
});

test("tab → inbox → recruiting chat → back → back returns to the tab", async () => {
  const session = createConversationBackController("flow-c");
  const router = routerAt("/");
  await push(router, "/dm", session);
  await push(router, "/organizations/circle/recruiting-chat", session);

  await conversationBack(router, session, "/dm");
  assert.equal(router.state.location.pathname, "/dm");
  await router.navigate(-1);
  assert.equal(router.state.location.pathname, "/");
});

test("notifications → room → back returns to notifications, not the inbox", async () => {
  const session = createConversationBackController("flow-d");
  const router = routerAt("/");
  await push(router, "/notifications", session);
  await push(router, "/dm/4", session);

  const dest = await conversationBack(router, session, "/dm");
  assert.equal(dest.mode, "history");
  assert.equal(router.state.location.pathname, "/notifications");
});

test("cold start / URL open of a room replaces to the inbox fallback", async () => {
  const session = createConversationBackController("flow-f");
  const router = routerAt("/dm/4");
  const dest = await conversationBack(router, session, "/dm");
  assert.equal(dest.mode, "path");
  assert.equal(dest.replace, true);
  assert.equal(router.state.location.pathname, "/dm");
  await router.navigate(-1);
  assert.equal(router.state.location.pathname, "/dm");
});

test("native-push style replace into a room then back lands on inbox, not the tab", async () => {
  const session = createConversationBackController("flow-e");
  const router = routerAt("/");
  await router.navigate("/dm/4", { replace: true });
  const dest = await conversationBack(router, session, "/dm");
  assert.equal(dest.mode, "path");
  assert.equal(router.state.location.pathname, "/dm");
});

test("inbox → room A → back → room B → back → back does not reopen A or B", async () => {
  const session = createConversationBackController("flow-h");
  const router = routerAt("/");
  await push(router, "/dm", session);
  await push(router, "/dm/1", session);
  await conversationBack(router, session, "/dm");
  assert.equal(router.state.location.pathname, "/dm");

  await push(router, "/dm/2", session);
  await conversationBack(router, session, "/dm");
  assert.equal(router.state.location.pathname, "/dm");

  await router.navigate(-1);
  assert.equal(router.state.location.pathname, "/");
  assert.notEqual(router.state.location.pathname, "/dm/1");
  assert.notEqual(router.state.location.pathname, "/dm/2");
});

test("course detail → talk → back returns to the course, not a pushed inbox", async () => {
  const session = createConversationBackController("flow-g-course");
  const router = routerAt("/courses/8");
  await push(router, "/courses/8/talk", session);
  await conversationBack(router, session, "/dm?tab=course");
  assert.equal(router.state.location.pathname, "/courses/8");
});

test("header back never PUSHes a new inbox entry", async () => {
  const session = createConversationBackController("no-push");
  const router = routerAt("/");
  await push(router, "/dm", session);
  await push(router, "/dm/4", session);
  await conversationBack(router, session, "/dm");
  assert.equal(router.state.historyAction, "POP");
  assert.equal(router.state.location.pathname, "/dm");

  const coldSession = createConversationBackController("cold");
  const coldRouter = routerAt("/dm/9");
  await conversationBack(coldRouter, coldSession, "/dm");
  assert.equal(coldRouter.state.historyAction, "REPLACE");
  assert.equal(coldRouter.state.location.pathname, "/dm");
});

test("iOS edge-swipe POP matches in-app conversation back after a stamped push", async () => {
  const session = createConversationBackController("swipe");
  const router = routerAt("/");
  await push(router, "/dm", session);
  await push(router, "/dm/4", session);
  await router.navigate(-1);
  assert.equal(router.state.location.pathname, "/dm");
});

test("execute pops when stamped and replaces when not, never pushing fallback", () => {
  const session = createConversationBackController("exec");
  const calls: unknown[] = [];
  const navigate = ((to: unknown, opts?: unknown) => {
    calls.push([to, opts]);
  }) as NavigateFunction;

  session.execute(navigate, "/dm", session.withState({ pathname: "/dm", key: "k1" }));
  assert.deepEqual(calls, [[-1, undefined]]);

  calls.length = 0;
  session.execute(navigate, "/dm", undefined);
  assert.deepEqual(calls, [["/dm", { replace: true }]]);
});
