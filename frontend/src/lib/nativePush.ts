/** Capacitor native push token ↔ Django session sync. */

import { getCsrfToken } from "../features/timeline/api";

type WaseCapacitorPushBridge = {
  getPushToken?: () => string | null;
  registerPushToken?: (token: string) => Promise<boolean | void>;
  unregisterPushToken?: (token?: string | null) => Promise<boolean | void>;
};

declare global {
  interface Window {
    WASE_PUSH_TOKEN?: string;
    WaseCapacitor?: WaseCapacitorPushBridge;
    Capacitor?: unknown;
  }
}

let lastSyncedUserId: number | null = null;
let syncInFlight: Promise<void> | null = null;

function getBridge(): WaseCapacitorPushBridge | null {
  return window.WaseCapacitor || null;
}

function isLikelyNativeShell(): boolean {
  return Boolean(window.Capacitor || getBridge()?.getPushToken || window.WASE_PUSH_TOKEN);
}

function readPushToken(): string | null {
  const bridge = getBridge();
  return bridge?.getPushToken?.() || window.WASE_PUSH_TOKEN || null;
}

function waitForPushToken(timeoutMs = 10000): Promise<string | null> {
  const existing = readPushToken();
  if (existing) {
    return Promise.resolve(existing);
  }

  return new Promise((resolve) => {
    let settled = false;
    const finish = (token: string | null) => {
      if (settled) return;
      settled = true;
      window.clearTimeout(timer);
      window.removeEventListener("wase:push-token", onToken);
      resolve(token);
    };
    const onToken = (event: Event) => {
      const detail = (event as CustomEvent<string>).detail;
      finish(typeof detail === "string" && detail ? detail : readPushToken());
    };
    const timer = window.setTimeout(() => {
      finish(readPushToken());
    }, timeoutMs);
    window.addEventListener("wase:push-token", onToken);
  });
}

function guessPlatform(): string {
  const ua = navigator.userAgent || "";
  if (/android/i.test(ua)) return "android";
  return "ios";
}

async function registerTokenViaFetch(token: string): Promise<boolean> {
  try {
    const res = await fetch("/api/push-token/", {
      method: "POST",
      credentials: "same-origin",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
        "X-CSRFToken": getCsrfToken(),
      },
      body: JSON.stringify({ token, platform: guessPlatform() }),
    });
    return res.ok;
  } catch {
    return false;
  }
}

async function unregisterTokenViaFetch(token: string): Promise<boolean> {
  try {
    const res = await fetch("/api/push-token/", {
      method: "POST",
      credentials: "same-origin",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
        "X-CSRFToken": getCsrfToken(),
      },
      body: JSON.stringify({ token, unregister: true }),
    });
    return res.ok;
  } catch {
    return false;
  }
}

/**
 * ログイン成功 / セッション復元時にトークンを現ユーザーへ紐付ける。
 * 別アカウント所有トークンも Backend が付け替える。
 */
export async function registerNativePushForSession(): Promise<void> {
  if (!isLikelyNativeShell()) {
    return;
  }

  const bridge = getBridge();
  const token = (await waitForPushToken()) || readPushToken();
  if (!token) return;

  if (bridge?.registerPushToken) {
    await bridge.registerPushToken(token);
    return;
  }
  await registerTokenViaFetch(token);
}

/**
 * ログアウト前に呼ぶ。セッションが残っているうちに自ユーザー紐付けを外す。
 */
export async function unregisterNativePushForSession(): Promise<void> {
  if (!isLikelyNativeShell()) {
    return;
  }

  const token = readPushToken();
  if (!token) return;

  const bridge = getBridge();
  if (bridge?.unregisterPushToken) {
    await bridge.unregisterPushToken(token);
    return;
  }
  await unregisterTokenViaFetch(token);
}

/**
 * Session の user id 変化に追従。
 * - authenticated userId → register（SPA ログイン後の再登録）
 * - null → state リセットのみ（unregister は logout 側で実施済み）
 */
export function syncNativePushWithUserId(userId: number | null): Promise<void> {
  if (syncInFlight) {
    return syncInFlight.then(() => syncNativePushWithUserId(userId));
  }

  syncInFlight = (async () => {
    try {
      if (userId == null) {
        lastSyncedUserId = null;
        return;
      }
      if (lastSyncedUserId === userId) {
        return;
      }
      await registerNativePushForSession();
      lastSyncedUserId = userId;
    } finally {
      syncInFlight = null;
    }
  })();

  return syncInFlight;
}

/** テスト / 強制再同期用 */
export function resetNativePushSyncState(): void {
  lastSyncedUserId = null;
}
