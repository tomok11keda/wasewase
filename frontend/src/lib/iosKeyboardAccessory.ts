/**
 * iOS WKWebView Input Accessory Bar (prev/next/done).
 *
 * Capacitor 7 iOS injects plugin methods onto window.Capacitor.Plugins
 * at document start (JSExport). There is no Capacitor.getPlugin() in
 * @capacitor/core 7. Do not import @capacitor/keyboard here — bundling
 * @capacitor/core into the remote SPA would rewrite window.Capacitor.
 *
 * Do not change chat viewport math from here.
 */

import { useEffect } from "react";
import { isNativeCapacitorApp } from "./nativeApp.ts";

export const ACCESSORY_BAR_RETRY_MS = [0, 300, 1000] as const;

export type AccessoryBarBridge = {
  isNativePlatform: boolean;
  platform: string | null;
  setAccessoryBarVisible?: (options: { isVisible: boolean }) => Promise<void>;
};

type KeyboardPlugin = {
  setAccessoryBarVisible?: (options: { isVisible: boolean }) => Promise<void>;
};

type CapacitorHost = {
  Capacitor?: {
    isNativePlatform?: () => boolean;
    getPlatform?: () => string;
    getPlugin?: (name: string) => KeyboardPlugin | undefined;
    registerPlugin?: (name: string) => KeyboardPlugin | undefined;
    Plugins?: {
      Keyboard?: KeyboardPlugin;
    };
  };
};

/** Conversation chrome hides the bar; every other screen restores it. */
export function accessoryBarShouldBeVisible(isConversation: boolean): boolean {
  return !isConversation;
}

export function canControlIosAccessoryBar(bridge: {
  isNativePlatform: boolean;
  platform: string | null;
}): boolean {
  return bridge.isNativePlatform && bridge.platform === "ios";
}

function pluginHasAccessoryApi(
  plugin: KeyboardPlugin | null | undefined
): plugin is KeyboardPlugin {
  return typeof plugin?.setAccessoryBarVisible === "function";
}

/**
 * Capacitor 7 lookup order:
 * 1. Plugins.Keyboard — native iOS JSExport (Camera/AdMob already use this)
 * 2. getPlugin("Keyboard") — older comment in capacitor_native.js, not in core 7
 * 3. registerPlugin("Keyboard") — official Capacitor 7 proxy, if the shell exposes it
 */
export function resolveKeyboardPlugin(
  cap: CapacitorHost["Capacitor"] | null | undefined
): KeyboardPlugin | undefined {
  const fromPlugins = cap?.Plugins?.Keyboard;
  if (pluginHasAccessoryApi(fromPlugins)) return fromPlugins;

  if (typeof cap?.getPlugin === "function") {
    try {
      const viaGet = cap.getPlugin("Keyboard");
      if (pluginHasAccessoryApi(viaGet)) return viaGet;
    } catch {
      /* Capacitor 7 has no getPlugin */
    }
  }

  if (typeof cap?.registerPlugin === "function") {
    try {
      const viaRegister = cap.registerPlugin("Keyboard");
      if (pluginHasAccessoryApi(viaRegister)) return viaRegister;
    } catch {
      /* old binary / unimplemented */
    }
  }

  return fromPlugins;
}

export function readCapacitorKeyboardBridge(
  host: CapacitorHost | null | undefined
): AccessoryBarBridge {
  try {
    const cap = host?.Capacitor;
    const isNativePlatform =
      typeof cap?.isNativePlatform === "function"
        ? Boolean(cap.isNativePlatform())
        : false;
    const platform =
      typeof cap?.getPlatform === "function" ? cap.getPlatform() : null;
    const plugin = resolveKeyboardPlugin(cap);
    const setAccessoryBarVisible = plugin?.setAccessoryBarVisible?.bind(plugin);
    return { isNativePlatform, platform, setAccessoryBarVisible };
  } catch {
    return { isNativePlatform: false, platform: null };
  }
}

export function shouldRetryIosAccessoryBar(
  bridge: AccessoryBarBridge,
  isNativeApp: boolean
): boolean {
  if (!isNativeApp && !bridge.isNativePlatform) return false;
  if (bridge.platform === "android") return false;
  if (bridge.platform === "web" && !isNativeApp) return false;
  if (
    canControlIosAccessoryBar(bridge) &&
    typeof bridge.setAccessoryBarVisible === "function"
  ) {
    return false;
  }
  return true;
}

type ApplyVisible = (isVisible: boolean) => Promise<void>;

/**
 * Serialize accessory-bar writes so StrictMode remounts and fast
 * conversation ↔ inbox navigations cannot finish out of order.
 * Only the latest requested value is applied.
 */
export function createAccessoryBarController(apply: ApplyVisible) {
  let desired: boolean | null = null;
  let lastApplied: boolean | null = null;
  let looping = false;
  let chain: Promise<void> = Promise.resolve();

  const pump = (): Promise<void> => {
    if (looping) return chain;
    looping = true;
    chain = chain
      .then(async () => {
        while (desired !== null && desired !== lastApplied) {
          const next = desired;
          try {
            await apply(next);
          } catch {
            /* plugin missing / unimplemented */
          }
          lastApplied = next;
        }
      })
      .finally(() => {
        looping = false;
      });
    return chain.then(() => {
      if (desired !== null && desired !== lastApplied) {
        return pump();
      }
    });
  };

  return {
    request(isVisible: boolean): Promise<void> {
      desired = isVisible;
      return pump();
    },
  };
}

function hostFromWindow(): CapacitorHost | null {
  if (typeof window === "undefined") return null;
  return window as unknown as CapacitorHost;
}

const liveController = createAccessoryBarController(async (isVisible) => {
  const bridge = readCapacitorKeyboardBridge(hostFromWindow());
  if (!canControlIosAccessoryBar(bridge) || !bridge.setAccessoryBarVisible) {
    return;
  }
  await bridge.setAccessoryBarVisible({ isVisible });
});

export function syncIosAccessoryBarForConversation(
  isConversation: boolean,
  bridge: AccessoryBarBridge = readCapacitorKeyboardBridge(hostFromWindow()),
  controller = liveController
): Promise<void> {
  if (!canControlIosAccessoryBar(bridge)) {
    return Promise.resolve();
  }
  if (typeof bridge.setAccessoryBarVisible !== "function") {
    return Promise.resolve();
  }
  return controller.request(accessoryBarShouldBeVisible(isConversation));
}

/** Conversation screens hide the bar; leaving restores it for other forms. */
export function useIosConversationAccessoryBar(isConversation: boolean): void {
  useEffect(() => {
    let cancelled = false;
    const timers: number[] = [];

    const attempt = () => {
      if (cancelled) return;
      void syncIosAccessoryBarForConversation(isConversation);
    };

    attempt();

    const host = hostFromWindow();
    const bridge = readCapacitorKeyboardBridge(host);
    const nativeApp = isNativeCapacitorApp();
    if (!shouldRetryIosAccessoryBar(bridge, nativeApp)) {
      return () => {
        cancelled = true;
      };
    }

    const onReady = () => attempt();
    window.addEventListener("capacitor:ready", onReady);
    for (const ms of ACCESSORY_BAR_RETRY_MS) {
      timers.push(window.setTimeout(attempt, ms));
    }
    return () => {
      cancelled = true;
      window.removeEventListener("capacitor:ready", onReady);
      for (const id of timers) window.clearTimeout(id);
    };
  }, [isConversation]);
}
