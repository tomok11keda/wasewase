import assert from "node:assert/strict";
import test from "node:test";
import { matchChromeMode } from "./chrome.ts";
import {
  accessoryBarShouldBeVisible,
  canControlIosAccessoryBar,
  createAccessoryBarController,
  readCapacitorKeyboardBridge,
  resolveKeyboardPlugin,
  shouldRetryIosAccessoryBar,
  syncIosAccessoryBarForConversation,
} from "./iosKeyboardAccessory.ts";

test("web and Android never control the iOS accessory bar", () => {
  assert.equal(
    canControlIosAccessoryBar({ isNativePlatform: false, platform: "web" }),
    false
  );
  assert.equal(
    canControlIosAccessoryBar({ isNativePlatform: true, platform: "android" }),
    false
  );
  assert.equal(
    canControlIosAccessoryBar({ isNativePlatform: true, platform: "ios" }),
    true
  );
});

test("conversation hides the bar and leaving shows it again", () => {
  assert.equal(accessoryBarShouldBeVisible(true), false);
  assert.equal(accessoryBarShouldBeVisible(false), true);
});

test("chat rooms hide the bar; login and profile forms restore it", () => {
  const rooms = [
    "/dm/4",
    "/dm/groups/12",
    "/organizations/circle/recruiting-chat",
    "/courses/8/talk",
    "/flea/chats/3",
  ];
  for (const path of rooms) {
    assert.equal(matchChromeMode(path), "conversation");
    assert.equal(
      accessoryBarShouldBeVisible(matchChromeMode(path) === "conversation"),
      false
    );
  }
  for (const path of ["/login", "/settings/profile", "/dm", "/"]) {
    assert.notEqual(matchChromeMode(path), "conversation");
    assert.equal(
      accessoryBarShouldBeVisible(matchChromeMode(path) === "conversation"),
      true
    );
  }
});

test("missing Capacitor or Keyboard plugin is a no-op", async () => {
  assert.deepEqual(readCapacitorKeyboardBridge({}), {
    isNativePlatform: false,
    platform: null,
    setAccessoryBarVisible: undefined,
  });
  await syncIosAccessoryBarForConversation(true, {
    isNativePlatform: true,
    platform: "ios",
  });
});

test("plugin throws are swallowed so chat cannot crash", async () => {
  await syncIosAccessoryBarForConversation(
    true,
    {
      isNativePlatform: true,
      platform: "ios",
      async setAccessoryBarVisible() {
        throw new Error("unimplemented");
      },
    },
    createAccessoryBarController(async () => {
      throw new Error("unimplemented");
    })
  );
});

test("latest requested visibility wins when navigations overlap", async () => {
  const applied: boolean[] = [];
  let releaseFirst: () => void = () => {};
  const firstGate = new Promise<void>((resolve) => {
    releaseFirst = resolve;
  });
  let calls = 0;
  const controller = createAccessoryBarController(async (isVisible) => {
    calls += 1;
    if (calls === 1) await firstGate;
    applied.push(isVisible);
  });

  const first = controller.request(true);
  const second = controller.request(false);
  releaseFirst();
  await first;
  await second;
  assert.equal(applied[applied.length - 1], false);
  assert.equal(applied.includes(false), true);
});

test("inbox then room then inbox ends visible for other forms", async () => {
  const applied: boolean[] = [];
  const controller = createAccessoryBarController(async (isVisible) => {
    applied.push(isVisible);
  });
  const ios = {
    isNativePlatform: true,
    platform: "ios",
    async setAccessoryBarVisible() {},
  };
  await syncIosAccessoryBarForConversation(false, ios, controller);
  await syncIosAccessoryBarForConversation(true, ios, controller);
  await syncIosAccessoryBarForConversation(false, ios, controller);
  assert.deepEqual(applied, [true, false, true]);
});

test("Capacitor 7 uses injected Plugins.Keyboard without getPlugin", () => {
  const bridge = readCapacitorKeyboardBridge({
    Capacitor: {
      isNativePlatform: () => true,
      getPlatform: () => "ios",
      Plugins: {
        Keyboard: {
          async setAccessoryBarVisible() {},
        },
      },
    },
  });
  assert.equal(bridge.isNativePlatform, true);
  assert.equal(bridge.platform, "ios");
  assert.equal(typeof bridge.setAccessoryBarVisible, "function");
});

test("getPlugin throwing still falls back to Plugins.Keyboard", () => {
  const plugin = resolveKeyboardPlugin({
    getPlugin() {
      throw new Error("no getPlugin");
    },
    Plugins: {
      Keyboard: {
        async setAccessoryBarVisible() {},
      },
    },
  });
  assert.equal(typeof plugin?.setAccessoryBarVisible, "function");
});

test("registerPlugin is used when Plugins is empty on a Capacitor 7 shell", () => {
  let registered = "";
  const plugin = resolveKeyboardPlugin({
    registerPlugin(name: string) {
      registered = name;
      return {
        async setAccessoryBarVisible() {},
      };
    },
  });
  assert.equal(registered, "Keyboard");
  assert.equal(typeof plugin?.setAccessoryBarVisible, "function");
});

test("native iOS retries until the injected plugin appears", () => {
  assert.equal(
    shouldRetryIosAccessoryBar(
      { isNativePlatform: true, platform: "ios" },
      true
    ),
    true
  );
  assert.equal(
    shouldRetryIosAccessoryBar(
      {
        isNativePlatform: true,
        platform: "ios",
        async setAccessoryBarVisible() {},
      },
      true
    ),
    false
  );
  assert.equal(
    shouldRetryIosAccessoryBar(
      { isNativePlatform: false, platform: "web" },
      false
    ),
    false
  );
});

test("web host never calls the native plugin", async () => {
  let called = false;
  await syncIosAccessoryBarForConversation(
    true,
    {
      isNativePlatform: false,
      platform: "web",
      async setAccessoryBarVisible() {
        called = true;
      },
    },
    createAccessoryBarController(async () => {
      called = true;
    })
  );
  assert.equal(called, false);
});
