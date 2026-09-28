import {
  isConversationPath,
  matchMainTab,
  normalizeSpaPath,
} from "./tabs";

export type ChromeMode = "main" | "detail" | "conversation";

export type DetailBackPolicy =
  | { kind: "fallback"; to: string }
  | { kind: "history-or-fallback"; to: string }
  | { kind: "from-wasewase-or-fallback"; to: string };

export type DetailChrome = {
  title: string;
  back: DetailBackPolicy;
};

export type DetailBackTarget =
  | { mode: "history" }
  | { mode: "path"; to: string; replace?: boolean };

/**
 * Shell chrome is decided from the route, not by each page hiding/padding
 * the header. Conversation rooms keep their own in-page back chrome.
 */
export function matchChromeMode(pathname: string): ChromeMode {
  if (isConversationPath(pathname)) return "conversation";
  if (matchMainTab(pathname) != null) return "main";
  return "detail";
}

function fromWaseWaseState(state: unknown): boolean {
  if (!state || typeof state !== "object") return false;
  return Boolean((state as { fromWaseWase?: unknown }).fromWaseWase);
}

export function matchDetailChrome(pathname: string): DetailChrome | null {
  if (matchChromeMode(pathname) !== "detail") return null;
  const p = normalizeSpaPath(pathname);

  if (/^\/posts\/\d+$/.test(p)) {
    return {
      title: "投稿",
      back: { kind: "from-wasewase-or-fallback", to: "/" },
    };
  }
  if (/^\/communities\/[^/]+\/threads\/\d+$/.test(p)) {
    return {
      title: "コミュニティ",
      back: { kind: "fallback", to: "/communities" },
    };
  }
  if (p === "/flea/exhibit") {
    return { title: "出品", back: { kind: "fallback", to: "/flea" } };
  }
  if (/^\/flea\/products\/\d+$/.test(p)) {
    return { title: "フリマ", back: { kind: "fallback", to: "/flea" } };
  }
  if (/^\/timetable\/user\/(\d+)$/.test(p)) {
    const userPk = p.split("/")[3];
    return {
      title: "時間割",
      back: { kind: "fallback", to: `/users/${userPk}/posts` },
    };
  }
  if (/^\/courses\/\d+$/.test(p)) {
    return {
      title: "授業",
      back: { kind: "history-or-fallback", to: "/timetable" },
    };
  }
  if (/^\/users\/(\d+)\/followers$/.test(p)) {
    const userPk = p.split("/")[2];
    return {
      title: "フォロワー",
      back: { kind: "fallback", to: `/users/${userPk}/posts` },
    };
  }
  if (/^\/users\/(\d+)\/following$/.test(p)) {
    const userPk = p.split("/")[2];
    return {
      title: "フォロー中",
      back: { kind: "fallback", to: `/users/${userPk}/posts` },
    };
  }
  if (/^\/users\/\d+/.test(p)) {
    return { title: "プロフィール", back: { kind: "fallback", to: "/" } };
  }
  if (p === "/notifications") {
    return {
      title: "通知",
      back: { kind: "history-or-fallback", to: "/" },
    };
  }
  if (p === "/settings/follow-requests") {
    return {
      title: "フォローリクエスト",
      back: { kind: "fallback", to: "/notifications" },
    };
  }
  if (p.startsWith("/settings")) {
    return { title: "設定", back: { kind: "fallback", to: "/" } };
  }
  if (p === "/dm/requests") {
    return { title: "リクエスト", back: { kind: "fallback", to: "/dm" } };
  }
  if (p === "/dm/groups/new") {
    return { title: "グループ作成", back: { kind: "fallback", to: "/dm" } };
  }
  if (p === "/dm") {
    return {
      title: "メッセージ",
      back: { kind: "history-or-fallback", to: "/" },
    };
  }
  if (p === "/more") {
    return { title: "メニュー", back: { kind: "fallback", to: "/" } };
  }

  return { title: "わせわせ", back: { kind: "fallback", to: "/" } };
}

/** Preserve existing back semantics; only the chrome host changes. */
export function resolveDetailBack(
  pathname: string,
  state?: unknown
): DetailBackTarget {
  const chrome = matchDetailChrome(pathname);
  if (!chrome) {
    return { mode: "path", to: "/", replace: true };
  }
  if (chrome.back.kind === "from-wasewase-or-fallback") {
    if (fromWaseWaseState(state)) return { mode: "history" };
    return { mode: "path", to: chrome.back.to, replace: true };
  }
  if (chrome.back.kind === "history-or-fallback") {
    if (typeof window !== "undefined" && window.history.length > 1) {
      return { mode: "history" };
    }
    return { mode: "path", to: chrome.back.to };
  }
  return { mode: "path", to: chrome.back.to };
}

const CHROME_CLASSES: ChromeMode[] = ["main", "detail", "conversation"];

export function applyChromeModeClass(
  mode: ChromeMode,
  root: HTMLElement | null
): void {
  if (!root) return;
  for (const name of CHROME_CLASSES) {
    root.classList.toggle(`chrome-${name}`, name === mode);
  }
  root.dataset.chromeMode = mode;
}
