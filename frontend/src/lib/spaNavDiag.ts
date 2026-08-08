/**
 * TestFlight 白フラッシュ切り分け用フラグ。
 * 通常時（フラグなし）はすべて false = 本番挙動のまま。
 *
 * URL: /app/?spa_nav_diag=off|no_banner|no_ads|no_analytics|no_bridge|no_keepalive|no_transition
 * 複数可: ?spa_nav_diag=no_banner,no_analytics
 * 解除: ?spa_nav_diag=clear
 *
 * 値は localStorage.wase_spa_nav_diag に保存され、タブ切替後も維持される。
 */

import { useMemo } from "react";
import { useLocation } from "react-router-dom";

export type SpaNavDiagFlags = {
  /** notifySpaNavigation 全体を無効化 */
  disableAll: boolean;
  disableAnalytics: boolean;
  /** creation AdMob trigger (handlePageTriggers) */
  disableAds: boolean;
  /** AdMob banner reposition のみ */
  disableBannerReposition: boolean;
  /** NativeSpaBridge が bridge を呼ばない */
  disableBridge: boolean;
  /** Keep-Alive を使わず通常の Outlet remount */
  disableKeepAlive: boolean;
  /** Keep-Alive は維持、opacity crossfade のみオフ */
  disableTransition: boolean;
  /** 生の diag 文字列（デバッグ表示用） */
  raw: string;
};

export type SpaDiagModeId =
  | "normal"
  | "no_banner"
  | "off"
  | "no_bridge"
  | "no_analytics"
  | "no_keepalive"
  | "no_transition"
  | "clear";

export type SpaDiagModeOption = {
  id: SpaDiagModeId;
  label: string;
  /** spa_nav_diag に書く値（normal/clear は空扱いでクリア） */
  navDiag: string;
  /** spa_flash_diag を付けるか */
  flashDiag: boolean;
  description: string;
};

/** TestFlight 診断パネル用プリセット（本番挙動は normal/clear のみ） */
export const SPA_DIAG_MODE_OPTIONS: SpaDiagModeOption[] = [
  {
    id: "normal",
    label: "Normal",
    navDiag: "",
    flashDiag: false,
    description: "診断オフ・通常の本番挙動",
  },
  {
    id: "no_banner",
    label: "no_banner",
    navDiag: "no_banner",
    flashDiag: true,
    description: "AdMob banner reposition のみ無効",
  },
  {
    id: "off",
    label: "off",
    navDiag: "off",
    flashDiag: true,
    description: "notifySpaNavigation 全体オフ",
  },
  {
    id: "no_bridge",
    label: "no_bridge",
    navDiag: "no_bridge",
    flashDiag: true,
    description: "NativeSpaBridge 呼び出しオフ",
  },
  {
    id: "no_analytics",
    label: "no_analytics",
    navDiag: "no_analytics",
    flashDiag: true,
    description: "Analytics のみオフ",
  },
  {
    id: "no_keepalive",
    label: "no_keepalive",
    navDiag: "no_keepalive",
    flashDiag: true,
    description: "Keep-Alive オフ（通常 remount）",
  },
  {
    id: "no_transition",
    label: "no_transition",
    navDiag: "no_transition",
    flashDiag: true,
    description: "タブ crossfade のみオフ",
  },
  {
    id: "clear",
    label: "Clear",
    navDiag: "clear",
    flashDiag: false,
    description: "診断フラグを消去して通常に戻す",
  },
];

const STORAGE_KEY = "wase_spa_nav_diag";
const FLASH_STORAGE_KEY = "wase_flash_diag";

function emptyFlags(raw = ""): SpaNavDiagFlags {
  return {
    disableAll: false,
    disableAnalytics: false,
    disableAds: false,
    disableBannerReposition: false,
    disableBridge: false,
    disableKeepAlive: false,
    disableTransition: false,
    raw,
  };
}

function parseRaw(raw: string): SpaNavDiagFlags {
  const flags = emptyFlags(raw);
  if (!raw || raw === "clear" || raw === "default" || raw === "reset") {
    return emptyFlags("");
  }
  const parts = raw
    .toLowerCase()
    .split(/[,+\s]+/)
    .filter(Boolean);
  for (const p of parts) {
    if (p === "off" || p === "no_all" || p === "all") flags.disableAll = true;
    if (p === "no_analytics" || p === "analytics") flags.disableAnalytics = true;
    if (p === "no_ads" || p === "ads") flags.disableAds = true;
    if (p === "no_banner" || p === "banner") flags.disableBannerReposition = true;
    if (p === "no_bridge" || p === "bridge") flags.disableBridge = true;
    if (p === "no_keepalive" || p === "keepalive") flags.disableKeepAlive = true;
    if (p === "no_transition" || p === "transition") flags.disableTransition = true;
  }
  if (flags.disableAll) {
    flags.disableAnalytics = true;
    flags.disableAds = true;
    flags.disableBannerReposition = true;
    flags.disableBridge = true;
  }
  return flags;
}

function readStoredRaw(): string {
  try {
    return window.localStorage.getItem(STORAGE_KEY) || "";
  } catch {
    return "";
  }
}

function writeStoredRaw(raw: string): void {
  try {
    if (!raw || raw === "clear" || raw === "default" || raw === "reset") {
      window.localStorage.removeItem(STORAGE_KEY);
      return;
    }
    window.localStorage.setItem(STORAGE_KEY, raw);
  } catch {
    /* ignore */
  }
}

function writeFlashDiag(enabled: boolean): void {
  try {
    if (enabled) {
      window.localStorage.setItem(FLASH_STORAGE_KEY, "1");
    } else {
      window.localStorage.removeItem(FLASH_STORAGE_KEY);
    }
  } catch {
    /* ignore */
  }
}

/** URL search を優先。あれば localStorage へ同期。 */
export function readSpaNavDiag(search?: string): SpaNavDiagFlags {
  let raw = "";
  try {
    const params = new URLSearchParams(
      search ?? window.location.search ?? ""
    );
    if (params.has("spa_nav_diag")) {
      raw = params.get("spa_nav_diag") || "";
      writeStoredRaw(raw);
    } else {
      raw = readStoredRaw();
    }
  } catch {
    raw = readStoredRaw();
  }
  return parseRaw(raw);
}

/** BottomNav など: 既存 path に diag query を付与（維持用） */
export function withSpaNavDiagSearch(
  path: string,
  flags?: SpaNavDiagFlags
): string {
  const diag = flags ?? readSpaNavDiag();
  if (!diag.raw) return path;
  const [pathname, existing = ""] = path.split("?");
  const params = new URLSearchParams(existing);
  params.set("spa_nav_diag", diag.raw);
  const q = params.toString();
  return q ? `${pathname}?${q}` : pathname;
}

export function spaNavDiagActive(flags: SpaNavDiagFlags): boolean {
  return Boolean(
    flags.disableAll ||
      flags.disableAnalytics ||
      flags.disableAds ||
      flags.disableBannerReposition ||
      flags.disableBridge ||
      flags.disableKeepAlive ||
      flags.disableTransition
  );
}

export function useSpaNavDiag(): SpaNavDiagFlags {
  const { search } = useLocation();
  return useMemo(() => readSpaNavDiag(search), [search]);
}

/**
 * 診断モードを localStorage に書き、/app/?… へフルリロードして反映。
 * Capacitor WKWebView / capacitor_native.js の既存機構と整合。
 */
export function applySpaDiagMode(modeId: SpaDiagModeId): void {
  const mode =
    SPA_DIAG_MODE_OPTIONS.find((m) => m.id === modeId) ||
    SPA_DIAG_MODE_OPTIONS[0];

  writeFlashDiag(mode.flashDiag);
  if (!mode.navDiag || mode.navDiag === "clear") {
    writeStoredRaw("clear");
  } else {
    writeStoredRaw(mode.navDiag);
  }

  const params = new URLSearchParams();
  if (mode.flashDiag) {
    params.set("spa_flash_diag", "1");
  } else {
    params.set("spa_flash_diag", "0");
  }
  params.set("spa_nav_diag", mode.navDiag || "clear");

  window.location.assign(`/app/?${params.toString()}`);
}

export function buildSpaDiagAppPath(modeId: SpaDiagModeId): string {
  const mode =
    SPA_DIAG_MODE_OPTIONS.find((m) => m.id === modeId) ||
    SPA_DIAG_MODE_OPTIONS[0];
  const params = new URLSearchParams();
  if (mode.flashDiag) params.set("spa_flash_diag", "1");
  else params.set("spa_flash_diag", "0");
  params.set("spa_nav_diag", mode.navDiag || "clear");
  return `/app/?${params.toString()}`;
}
