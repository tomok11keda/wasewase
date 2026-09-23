/** Capacitor native FCM token ↔ Django session sync. */

import { getCsrfToken } from "../features/timeline/api";

type WaseCapacitorPushBridge = {
  getPushToken?: () => string | null;
  getPushStatus?: () => {
    permission?: string;
    apns?: boolean;
    fcm?: boolean;
    fcmPrefix?: string;
    backend?: boolean;
    error?: string;
  };
  registerPushToken?: (token: string) => Promise<boolean | void>;
  unregisterPushToken?: (token?: string | null) => Promise<boolean | void>;
  requestPushPermissionFromUser?: () => Promise<{ receive?: string } | void>;
  consumePendingPushOpenLink?: () => string | null;
};

declare global {
  interface Window {
    WASE_PUSH_TOKEN?: string;
    WASE_PENDING_PUSH_OPEN_LINK?: string | null;
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
  if (/^[0-9a-fA-F]{64}$/.test(token) || /^[0-9a-fA-F]{128}$/.test(token)) {
    return false;
  }
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

/** User-tapped CTA only. Native bootstrap never calls this. */
export async function requestPushPermissionFromUser(): Promise<{
  receive: string;
}> {
  const bridge = getBridge();
  if (typeof bridge?.requestPushPermissionFromUser === "function") {
    const result = await bridge.requestPushPermissionFromUser();
    const receive =
      result && typeof result.receive === "string" ? result.receive : "";
    return { receive };
  }
  return { receive: "" };
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

/** Convert FCM data.link (/app/...) to a React Router path (basename=/app). */
export function pushLinkToRouterPath(link: string | null | undefined): string | null {
  if (!link || typeof link !== "string") return null;
  let path = link.trim();
  if (!path) return null;
  if (/^https?:\/\//i.test(path)) {
    try {
      const url = new URL(path);
      path = `${url.pathname}${url.search}${url.hash}`;
    } catch {
      return null;
    }
  }
  if (path.startsWith("/app/") || path === "/app") {
    path = path === "/app" ? "/" : path.slice(4) || "/";
  }
  if (!path.startsWith("/")) {
    path = `/${path}`;
  }
  if (path.startsWith("//") || /[\s<>]/.test(path)) {
    return null;
  }
  return path;
}

export function consumePendingPushOpenLink(): string | null {
  const bridge = getBridge();
  const fromBridge = bridge?.consumePendingPushOpenLink?.() || null;
  const fromWindow =
    typeof window.WASE_PENDING_PUSH_OPEN_LINK === "string"
      ? window.WASE_PENDING_PUSH_OPEN_LINK
      : null;
  window.WASE_PENDING_PUSH_OPEN_LINK = null;
  return fromBridge || fromWindow;
}

const ALLOWED_PUSH_DIAG_ERRORS = new Set([
  "plugin_missing",
  "permission_request_failed",
  "permission_denied",
  "fcm_token_missing",
  "fcm_token_failed",
  "init_failed",
  "apns_token_not_supported",
  "backend_network",
]);

export function sanitizePushDiagError(raw: unknown): string {
  if (typeof raw !== "string") return "";
  const error = raw.trim();
  if (!error) return "";
  if (ALLOWED_PUSH_DIAG_ERRORS.has(error)) return error;
  if (/^backend_\d{3}$/.test(error)) return error;
  return "sanitized";
}

type CapacitorLike = {
  isNativePlatform?: () => boolean;
  getPlugin?: (name: string) => unknown;
  Plugins?: Record<string, unknown>;
};

function getCapacitor(): CapacitorLike | null {
  const cap = window.Capacitor;
  if (!cap || typeof cap !== "object") return null;
  return cap as CapacitorLike;
}

export function isFirebaseMessagingPluginAvailable(): boolean {
  const cap = getCapacitor();
  if (!cap) return false;
  try {
    if (typeof cap.getPlugin === "function" && cap.getPlugin("FirebaseMessaging")) {
      return true;
    }
  } catch {
    /* ignore */
  }
  const plugins = cap.Plugins;
  return Boolean(plugins && plugins.FirebaseMessaging);
}

export type SafePushDiagnostics = {
  native_bridge: boolean;
  native_platform: boolean;
  firebase_messaging_plugin: boolean;
  permission: string;
  fcm_token_acquired: boolean;
  backend_registered: boolean;
  fcm_inferred_apns_flag: boolean;
  error: string;
};

/**
 * Staff diagnostics only. Never returns tokens or fcmPrefix.
 * Do not call getPushToken() from diagnostic UI.
 */
export function readSafePushDiagnostics(): SafePushDiagnostics {
  const cap = getCapacitor();
  const bridge = getBridge();
  const nativeBridge = Boolean(bridge && typeof bridge.getPushStatus === "function");
  let permission = "";
  let fcm = false;
  let backend = false;
  let inferredApns = false;
  let error = "";
  if (nativeBridge && bridge?.getPushStatus) {
    const status = bridge.getPushStatus();
    permission = typeof status.permission === "string" ? status.permission : "";
    fcm = Boolean(status.fcm);
    backend = Boolean(status.backend);
    inferredApns = Boolean(status.apns);
    error = sanitizePushDiagError(status.error);
  }
  return {
    native_bridge: nativeBridge,
    native_platform: Boolean(cap?.isNativePlatform?.()),
    firebase_messaging_plugin: isFirebaseMessagingPluginAvailable(),
    permission,
    fcm_token_acquired: fcm,
    backend_registered: backend,
    fcm_inferred_apns_flag: inferredApns,
    error,
  };
}

export async function readNativeAppInfo(): Promise<{
  version: string;
  build: string;
}> {
  const cap = getCapacitor();
  const plugin =
    (typeof cap?.getPlugin === "function" ? cap.getPlugin("App") : null) ||
    cap?.Plugins?.App ||
    null;
  if (!plugin || typeof plugin !== "object") {
    return { version: "", build: "" };
  }
  const getInfo = (plugin as { getInfo?: () => Promise<{ version?: string; build?: string }> })
    .getInfo;
  if (typeof getInfo !== "function") {
    return { version: "", build: "" };
  }
  try {
    const info = await getInfo();
    return {
      version: typeof info?.version === "string" ? info.version : "",
      build: typeof info?.build === "string" ? info.build : "",
    };
  } catch {
    return { version: "", build: "" };
  }
}
