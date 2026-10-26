import assert from "node:assert/strict";
import test from "node:test";
import {
  bindChatKeyboardDiagListeners,
  captureChatKeyboardDiagSnapshot,
  chatKeyboardDiagOverlayPins,
  collectChatKeyboardDiagRects,
  formatChatKeyboardDiagLines,
  isChatKeyboardDiagEnabled,
  isChatKeyboardDiagRequested,
  readChatKeyboardDiagSnapshot,
  shouldShowChatKeyboardDiag,
  syncChatKeyboardDiagRequest,
} from "./chatKeyboardDiag.ts";

test("keyboard diag is off unless the query flag is exactly 1", () => {
  assert.equal(isChatKeyboardDiagEnabled(""), false);
  assert.equal(isChatKeyboardDiagEnabled("?tab=latest"), false);
  assert.equal(isChatKeyboardDiagEnabled("?chat_kb_diag=0"), false);
  assert.equal(isChatKeyboardDiagEnabled("?chat_kb_diag=1"), true);
  assert.equal(isChatKeyboardDiagEnabled("?q=hi&chat_kb_diag=1"), true);
});

test("diag request also honors sessionStorage for in-app navigation", () => {
  const storage = new Map<string, string>();
  const bag = {
    getItem: (key: string) => storage.get(key) ?? null,
    setItem: (key: string, value: string) => {
      storage.set(key, value);
    },
    removeItem: (key: string) => {
      storage.delete(key);
    },
  };
  assert.equal(
    isChatKeyboardDiagRequested({ search: "", storage: bag }),
    false
  );
  assert.equal(
    syncChatKeyboardDiagRequest({ search: "?chat_kb_diag=1", storage: bag }),
    true
  );
  assert.equal(storage.get("wase_chat_kb_diag"), "1");
  assert.equal(
    isChatKeyboardDiagRequested({ search: "/dm/4", storage: bag }),
    true
  );
  assert.equal(
    syncChatKeyboardDiagRequest({ search: "?chat_kb_diag=0", storage: bag }),
    false
  );
  assert.equal(storage.has("wase_chat_kb_diag"), false);
});

test("diag overlay stays off for normal users and non-conversation screens", () => {
  assert.equal(
    shouldShowChatKeyboardDiag({
      requested: false,
      isConversation: true,
      isDev: true,
    }),
    false
  );
  assert.equal(
    shouldShowChatKeyboardDiag({
      requested: true,
      isConversation: false,
      isDev: true,
    }),
    false
  );
  assert.equal(
    shouldShowChatKeyboardDiag({
      requested: true,
      isConversation: true,
      isDev: false,
      isStaff: false,
      isSuperuser: false,
    }),
    false
  );
  assert.equal(
    shouldShowChatKeyboardDiag({
      requested: true,
      isConversation: true,
      isDev: true,
    }),
    true
  );
  assert.equal(
    shouldShowChatKeyboardDiag({
      requested: true,
      isConversation: true,
      isDev: false,
      isStaff: true,
    }),
    true
  );
});

test("diag snapshot is geometry-only and never copies message text", () => {
  const snap = readChatKeyboardDiagSnapshot({
    innerHeight: 844,
    outerHeight: 844,
    scrollY: 12,
    visualViewport: {
      height: 508,
      offsetTop: 336,
      pageTop: 336,
      scale: 1,
    },
    frame: { height: 508, offsetTop: 336 },
    rects: {
      page: { top: 336, bottom: 844, height: 508 },
      messages: { top: 390, bottom: 780, height: 390 },
      compose: { top: 780, bottom: 844, height: 64 },
      input: { top: 790, bottom: 830, height: 40 },
      send: { top: 792, bottom: 832, height: 40 },
    },
    css: {
      getPropertyValue(name: string) {
        const map: Record<string, string> = {
          "--chat-visible-h": "508px",
          "--chat-vv-offset": "336px",
          "--wase-sat": "59px",
          "--wase-chrome-offset": "59px",
          "--wase-header-h": "103px",
        };
        return map[name] ?? "";
      },
    },
    sai: { top: 59, bottom: 34 },
    lastEvent: "focusin",
  });
  assert.equal(snap.vvHeight, 508);
  assert.equal(snap.vvPageTop, 336);
  assert.equal(snap.vvScale, 1);
  assert.equal(snap.outerHeight, 844);
  assert.equal(snap.composeBottom, 844);
  assert.equal(snap.sendTop, 792);
  assert.equal(snap.messagesTop, 390);
  assert.equal(snap.cssVisibleH, 508);
  assert.equal(snap.cssSaiTop, 59);
  assert.equal(snap.lastEvent, "focusin");
  const keys = Object.keys(snap);
  for (const forbidden of [
    "body",
    "email",
    "text",
    "content",
    "user",
    "userId",
    "user_id",
    "message",
  ]) {
    assert.equal(keys.includes(forbidden), false);
  }
  assert.equal("messagesTop" in snap, true);
  assert.equal(JSON.stringify(snap).includes("@"), false);
});

test("formatted overlay lines stay compact and omit user content", () => {
  const snap = captureChatKeyboardDiagSnapshot(
    {
      innerHeight: 844,
      outerHeight: 900,
      scrollY: 0,
      visualViewport: { height: 508, offsetTop: 0, pageTop: 0, scale: 1 },
      css: {
        getPropertyValue(name: string) {
          return name === "--chat-visible-h" ? "508px" : "";
        },
      },
    },
    "vv.resize"
  );
  const lines = formatChatKeyboardDiagLines(snap);
  assert.equal(lines[0], "KB vv.resize");
  assert.ok(lines.some((line) => line.includes("inH 844")));
  assert.ok(lines.some((line) => line.includes("vvH 508")));
  assert.ok(lines.some((line) => line.includes("cssH 508")));
  assert.ok(lines.join("\n").includes("bar"));
  assert.equal(lines.join(" ").toLowerCase().includes("hello"), false);
  assert.ok(lines.length <= 12);
});

test("viewport change updates snapshot numbers", () => {
  const closed = captureChatKeyboardDiagSnapshot(
    {
      innerHeight: 844,
      scrollY: 0,
      visualViewport: { height: 844, offsetTop: 0 },
    },
    "init"
  );
  const open = captureChatKeyboardDiagSnapshot(
    {
      innerHeight: 844,
      scrollY: 0,
      visualViewport: { height: 508, offsetTop: 336, pageTop: 336 },
    },
    "vv.resize"
  );
  assert.equal(closed.vvHeight, 844);
  assert.equal(closed.vvOffsetTop, 0);
  assert.equal(open.vvHeight, 508);
  assert.equal(open.vvOffsetTop, 336);
  assert.equal(open.frameHeight, 508);
  assert.equal(open.lastEvent, "vv.resize");
  assert.notEqual(closed.vvHeight, open.vvHeight);
});

test("keyboard open vs closed keeps compose geometry measurable", () => {
  const rects = {
    page: { top: 0, bottom: 844, height: 844 },
    messages: { top: 100, bottom: 780, height: 680 },
    compose: { top: 780, bottom: 844, height: 64 },
    input: { top: 790, bottom: 830, height: 40 },
    send: { top: 792, bottom: 832, height: 40 },
  };
  const closed = readChatKeyboardDiagSnapshot({
    innerHeight: 844,
    scrollY: 0,
    visualViewport: { height: 844, offsetTop: 0 },
    frame: { height: 844, offsetTop: 0 },
    rects,
    lastEvent: "focusout",
  });
  const open = readChatKeyboardDiagSnapshot({
    innerHeight: 844,
    scrollY: 0,
    visualViewport: { height: 844, offsetTop: 336 },
    frame: { height: 508, offsetTop: 336 },
    rects,
    lastEvent: "focusin",
  });
  assert.equal(closed.lastEvent, "focusout");
  assert.equal(open.lastEvent, "focusin");
  assert.equal(closed.composeTop, 780);
  assert.equal(open.composeTop, 780);
  assert.equal(open.sendBottom, 832);
  assert.ok(open.composeBottom > (open.vvOffsetTop ?? 0));
});

test("collects room / message / compose / send rects without reading text", () => {
  const makeEl = (rect: { top: number; bottom: number; height: number }) => ({
    getBoundingClientRect() {
      return rect;
    },
    querySelector() {
      return null;
    },
  });
  const input = makeEl({ top: 790, bottom: 830, height: 40 });
  const send = makeEl({ top: 792, bottom: 832, height: 40 });
  const compose = {
    ...makeEl({ top: 780, bottom: 844, height: 64 }),
    querySelector(sel: string) {
      if (sel === ".chat-compose-bar__input") return input;
      if (sel === ".chat-compose-bar__send") return send;
      return null;
    },
  };
  const root = {
    querySelector(sel: string) {
      if (sel === ".dm-room-page")
        return makeEl({ top: 0, bottom: 844, height: 844 });
      if (sel === ".dm-message-area")
        return makeEl({ top: 100, bottom: 780, height: 680 });
      if (sel === ".chat-compose-bar") return compose;
      return null;
    },
  };
  const rects = collectChatKeyboardDiagRects(root as unknown as ParentNode);
  assert.equal(rects.page?.top, 0);
  assert.equal(rects.messages?.bottom, 780);
  assert.equal(rects.compose?.height, 64);
  assert.equal(rects.input?.top, 790);
  assert.equal(rects.send?.bottom, 832);
});

test("overlay pins keep a layout-top copy so keyboard cannot hide every card", () => {
  assert.deepEqual(chatKeyboardDiagOverlayPins(0), [{ id: "A", top: 0 }]);
  assert.deepEqual(chatKeyboardDiagOverlayPins(336), [
    { id: "A", top: 0 },
    { id: "B", top: 336 },
  ]);
});

test("listeners fire viewport and focus events then clean up", () => {
  const vv = new Map<string, Set<() => void>>();
  const win = new Map<string, Set<() => void>>();
  const doc = new Map<string, Set<() => void>>();
  const events: string[] = [];
  const target = (bag: Map<string, Set<() => void>>) => ({
    addEventListener(type: string, listener: () => void) {
      const set = bag.get(type) ?? new Set();
      set.add(listener);
      bag.set(type, set);
    },
    removeEventListener(type: string, listener: () => void) {
      bag.get(type)?.delete(listener);
    },
  });
  const unbind = bindChatKeyboardDiagListeners(
    {
      ...target(win),
      visualViewport: target(vv),
      document: target(doc),
    },
    (name) => events.push(name)
  );
  assert.deepEqual(events, ["init"]);
  for (const listener of vv.get("resize") ?? []) listener();
  for (const listener of vv.get("scroll") ?? []) listener();
  for (const listener of doc.get("focusin") ?? []) listener();
  for (const listener of doc.get("focusout") ?? []) listener();
  assert.deepEqual(events, [
    "init",
    "vv.resize",
    "vv.scroll",
    "focusin",
    "focusout",
  ]);
  unbind();
  assert.equal(vv.get("resize")?.size, 0);
  assert.equal(vv.get("scroll")?.size, 0);
  assert.equal(doc.get("focusin")?.size, 0);
  assert.equal(doc.get("focusout")?.size, 0);
  for (const listener of vv.get("resize") ?? []) listener();
  assert.deepEqual(events, [
    "init",
    "vv.resize",
    "vv.scroll",
    "focusin",
    "focusout",
  ]);
});
