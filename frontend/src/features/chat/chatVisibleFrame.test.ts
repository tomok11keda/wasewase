import assert from "node:assert/strict";
import test from "node:test";
import {
  applyChatVisibleFrame,
  bindChatVisibleFrame,
  chatOverlayPadTop,
  clearChatVisibleFrame,
  readChatVisibleFrame,
  shouldResetDocumentScroll,
  syncChatVisibleFrame,
  type ChatVisibleFrameHost,
} from "./chatVisibleFrame.ts";

function styleStore() {
  const props = new Map<string, string>();
  return {
    props,
    setProperty(name: string, value: string) {
      props.set(name, value);
    },
    removeProperty(name: string) {
      props.delete(name);
    },
  };
}

test("usual viewport uses visual height and zero offset", () => {
  assert.deepEqual(
    readChatVisibleFrame({
      visualViewport: { height: 844, offsetTop: 0 },
      innerHeight: 844,
    }),
    { height: 844, offsetTop: 0 }
  );
  assert.equal(chatOverlayPadTop(59, 0), 59);
});

test("keyboard shrinks height without subtracting keyboard again", () => {
  assert.deepEqual(
    readChatVisibleFrame({
      visualViewport: { height: 508, offsetTop: 0 },
      innerHeight: 508,
    }),
    { height: 508, offsetTop: 0 }
  );
});

test("offsetTop greater than zero is rounded and kept", () => {
  assert.deepEqual(
    readChatVisibleFrame({
      visualViewport: { height: 508.4, offsetTop: 336.4 },
      innerHeight: 844,
    }),
    { height: 508, offsetTop: 336 }
  );
});

test("Capacitor pan without shrinking height keeps the compose bar in the window", () => {
  const frame = readChatVisibleFrame({
    visualViewport: { height: 844, offsetTop: 336 },
    innerHeight: 844,
  });
  assert.deepEqual(frame, { height: 508, offsetTop: 336 });
  assert.equal(frame.offsetTop + frame.height, 844);
});

test("clipped frame never extends past innerHeight", () => {
  const frame = readChatVisibleFrame({
    visualViewport: { height: 900, offsetTop: 400 },
    innerHeight: 844,
  });
  assert.equal(frame.offsetTop, 400);
  assert.equal(frame.height, 444);
  assert.equal(frame.offsetTop + frame.height <= 844, true);
});

test("keyboard hide restores the full frame", () => {
  const open = readChatVisibleFrame({
    visualViewport: { height: 500, offsetTop: 340 },
    innerHeight: 844,
  });
  const closed = readChatVisibleFrame({
    visualViewport: { height: 844, offsetTop: 0 },
    innerHeight: 844,
  });
  assert.equal(open.height < closed.height, true);
  assert.equal(open.offsetTop > 0, true);
  assert.deepEqual(closed, { height: 844, offsetTop: 0 });
});

test("safe-area pad shrinks as offsetTop consumes the notch", () => {
  assert.equal(chatOverlayPadTop(59, 0), 59);
  assert.equal(chatOverlayPadTop(59, 20), 39);
  assert.equal(chatOverlayPadTop(59, 59), 0);
  assert.equal(chatOverlayPadTop(59, 336), 0);
  assert.equal(chatOverlayPadTop(-8, 10), 0);
});

test("missing visualViewport falls back to innerHeight", () => {
  assert.deepEqual(
    readChatVisibleFrame({ visualViewport: null, innerHeight: 720 }),
    { height: 720, offsetTop: 0 }
  );
  assert.deepEqual(
    readChatVisibleFrame({
      visualViewport: { height: 0, offsetTop: -12 },
      innerHeight: 640,
    }),
    { height: 640, offsetTop: 0 }
  );
});

test("document scroll reset is only when the page actually moved", () => {
  assert.equal(shouldResetDocumentScroll(0, 0), false);
  assert.equal(shouldResetDocumentScroll(0, 40), true);
  assert.equal(shouldResetDocumentScroll(12, 0), true);
});

test("desktop-sized viewport with no offset stays a simple full frame", () => {
  assert.deepEqual(
    readChatVisibleFrame({
      visualViewport: { height: 1024, offsetTop: 0 },
      innerHeight: 1024,
    }),
    { height: 1024, offsetTop: 0 }
  );
});

test("apply and clear write only the chat CSS variables", () => {
  const style = styleStore();
  applyChatVisibleFrame(style, { height: 500, offsetTop: 80 });
  assert.equal(style.props.get("--chat-visible-h"), "500px");
  assert.equal(style.props.get("--chat-vv-offset"), "80px");
  clearChatVisibleFrame(style);
  assert.equal(style.props.has("--chat-visible-h"), false);
  assert.equal(style.props.has("--chat-vv-offset"), false);
});

test("sync applies the frame and resets document scroll when needed", () => {
  const style = styleStore();
  let scrolledTo: [number, number] | null = null;
  const frame = syncChatVisibleFrame(
    {
      visualViewport: { height: 510, offsetTop: 300 },
      innerHeight: 844,
      scrollX: 0,
      scrollY: 48,
      scrollTo(x, y) {
        scrolledTo = [x, y];
      },
    },
    style
  );
  assert.deepEqual(frame, { height: 510, offsetTop: 300 });
  assert.deepEqual(scrolledTo, [0, 0]);
  assert.equal(style.props.get("--chat-visible-h"), "510px");
  assert.equal(style.props.get("--chat-vv-offset"), "300px");
});

test("sync does not call scrollTo when the document is already at origin", () => {
  const style = styleStore();
  let calls = 0;
  syncChatVisibleFrame(
    {
      visualViewport: { height: 844, offsetTop: 0 },
      innerHeight: 844,
      scrollX: 0,
      scrollY: 0,
      scrollTo() {
        calls += 1;
      },
    },
    style
  );
  assert.equal(calls, 0);
});

test("bind updates on resize/scroll and unbind removes listeners and CSS vars", () => {
  const style = styleStore();
  const listeners = new Map<string, Set<() => void>>();
  const vvListeners = new Map<string, Set<() => void>>();
  const host: ChatVisibleFrameHost = {
    innerHeight: 844,
    scrollX: 0,
    scrollY: 0,
    scrollTo() {},
    visualViewport: {
      height: 844,
      offsetTop: 0,
      addEventListener(type, listener) {
        const set = vvListeners.get(type) ?? new Set();
        set.add(listener);
        vvListeners.set(type, set);
      },
      removeEventListener(type, listener) {
        vvListeners.get(type)?.delete(listener);
      },
    },
    addEventListener(type, listener) {
      const set = listeners.get(type) ?? new Set();
      set.add(listener);
      listeners.set(type, set);
    },
    removeEventListener(type, listener) {
      listeners.get(type)?.delete(listener);
    },
  };

  const unbind = bindChatVisibleFrame(host, style);
  assert.equal(style.props.get("--chat-visible-h"), "844px");
  assert.equal(vvListeners.get("resize")?.size, 1);
  assert.equal(vvListeners.get("scroll")?.size, 1);
  assert.equal(listeners.get("resize")?.size, 1);

  host.visualViewport!.height = 500;
  host.visualViewport!.offsetTop = 320;
  for (const listener of vvListeners.get("resize") ?? []) listener();
  assert.equal(style.props.get("--chat-visible-h"), "500px");
  assert.equal(style.props.get("--chat-vv-offset"), "320px");

  host.visualViewport!.height = 844;
  host.visualViewport!.offsetTop = 0;
  for (const listener of vvListeners.get("scroll") ?? []) listener();
  assert.equal(style.props.get("--chat-visible-h"), "844px");
  assert.equal(style.props.get("--chat-vv-offset"), "0px");

  unbind();
  assert.equal(vvListeners.get("resize")?.size, 0);
  assert.equal(vvListeners.get("scroll")?.size, 0);
  assert.equal(listeners.get("resize")?.size, 0);
  assert.equal(style.props.has("--chat-visible-h"), false);
  assert.equal(style.props.has("--chat-vv-offset"), false);

  host.visualViewport!.height = 400;
  for (const listener of vvListeners.get("resize") ?? []) listener();
  assert.equal(style.props.has("--chat-visible-h"), false);
});

test("bind resets document scroll once per offset and does not loop", () => {
  const style = styleStore();
  const vvListeners = new Map<string, Set<() => void>>();
  let scrollCalls = 0;
  const host: ChatVisibleFrameHost = {
    innerHeight: 844,
    scrollX: 0,
    scrollY: 40,
    scrollTo() {
      scrollCalls += 1;
    },
    visualViewport: {
      height: 500,
      offsetTop: 320,
      addEventListener(type, listener) {
        const set = vvListeners.get(type) ?? new Set();
        set.add(listener);
        vvListeners.set(type, set);
      },
      removeEventListener(type, listener) {
        vvListeners.get(type)?.delete(listener);
      },
    },
    addEventListener() {},
    removeEventListener() {},
  };

  const unbind = bindChatVisibleFrame(host, style);
  assert.equal(scrollCalls, 1);
  for (const listener of vvListeners.get("scroll") ?? []) listener();
  assert.equal(scrollCalls, 1);
  host.scrollY = 80;
  for (const listener of vvListeners.get("scroll") ?? []) listener();
  assert.equal(scrollCalls, 2);
  host.scrollY = 0;
  for (const listener of vvListeners.get("scroll") ?? []) listener();
  assert.equal(scrollCalls, 2);
  unbind();
});

test("focusin resyncs the frame without calling scrollTo", () => {
  const style = styleStore();
  const docListeners = new Map<string, Set<() => void>>();
  let scrollCalls = 0;
  const host: ChatVisibleFrameHost = {
    innerHeight: 844,
    scrollX: 0,
    scrollY: 0,
    scrollTo() {
      scrollCalls += 1;
    },
    visualViewport: {
      height: 844,
      offsetTop: 0,
      addEventListener() {},
      removeEventListener() {},
    },
    document: {
      addEventListener(type, listener) {
        const set = docListeners.get(type) ?? new Set();
        set.add(listener);
        docListeners.set(type, set);
      },
      removeEventListener(type, listener) {
        docListeners.get(type)?.delete(listener);
      },
    },
    addEventListener() {},
    removeEventListener() {},
  };
  const unbind = bindChatVisibleFrame(host, style);
  host.visualViewport!.height = 844;
  host.visualViewport!.offsetTop = 336;
  for (const listener of docListeners.get("focusin") ?? []) listener();
  assert.equal(style.props.get("--chat-visible-h"), "508px");
  assert.equal(style.props.get("--chat-vv-offset"), "336px");
  assert.equal(scrollCalls, 0);
  unbind();
  assert.equal(docListeners.get("focusin")?.size, 0);
});
