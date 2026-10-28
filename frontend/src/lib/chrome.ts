import {
  isConversationPath,
  matchMainTab,
  normalizeSpaPath,
} from "./tabs.ts";

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

function recruitingChatQuery(search: string): string {
  const params = new URLSearchParams(
    search.startsWith("?") ? search.slice(1) : search
  );
  const raw = params.get("chat") || params.get("chat_id") || "";
  const chatId = Number(raw);
  return Number.isInteger(chatId) && chatId > 0 ? `?chat=${chatId}` : "";
}

function withRecruitingChatQuery(path: string, search: string): string {
  return `${path}${recruitingChatQuery(search)}`;
}

function recruitingChatSafeBack(orgSlug: string, search: string): string {
  const query = recruitingChatQuery(search);
  if (query) return `/organizations/${orgSlug}/recruiting-chat${query}`;
  return `/orgs/${orgSlug}`;
}

export function matchDetailChrome(
  pathname: string,
  search = ""
): DetailChrome | null {
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
  if (/^\/users\/(\d+)\/(followers|following|mutuals)$/.test(p)) {
    const userPk = p.split("/")[2];
    const kind = p.split("/")[3];
    const title =
      kind === "following"
        ? "フォロー中"
        : kind === "mutuals"
          ? "共通の友達"
          : "フォロワー";
    return {
      title,
      back: { kind: "fallback", to: `/users/${userPk}/posts` },
    };
  }
  if (/^\/(?:organizations|orgs)\/[^/]+\/events\/new$/.test(p)) {
    const orgSlug = p.split("/")[2];
    return {
      title: "イベントを作成",
      back: { kind: "fallback", to: `/organizations/${orgSlug}/events/manage` },
    };
  }
  if (/^\/(?:organizations|orgs)\/[^/]+\/events\/manage$/.test(p)) {
    const orgSlug = p.split("/")[2];
    return {
      title: "イベント管理",
      back: { kind: "fallback", to: `/orgs/${orgSlug}` },
    };
  }
  if (/^\/(?:organizations|orgs)\/[^/]+\/events\/\d+\/edit$/.test(p)) {
    const orgSlug = p.split("/")[2];
    const eventId = p.split("/")[4];
    return {
      title: "イベントを編集",
      back: {
        kind: "fallback",
        to: `/organizations/${orgSlug}/events/${eventId}`,
      },
    };
  }
  if (/^\/(?:organizations|orgs)\/[^/]+\/events\/\d+\/registrations$/.test(p)) {
    const orgSlug = p.split("/")[2];
    const eventId = p.split("/")[4];
    return {
      title: "申込者",
      back: {
        kind: "fallback",
        to: `/organizations/${orgSlug}/events/${eventId}`,
      },
    };
  }
  if (/^\/(?:organizations|orgs)\/[^/]+\/events\/\d+\/lottery$/.test(p)) {
    const orgSlug = p.split("/")[2];
    const eventId = p.split("/")[4];
    return {
      title: "抽選",
      back: {
        kind: "fallback",
        to: `/organizations/${orgSlug}/events/${eventId}`,
      },
    };
  }
  if (/^\/(?:organizations|orgs)\/[^/]+\/events\/\d+$/.test(p)) {
    const orgSlug = p.split("/")[2];
    return {
      title: "イベント",
      back: { kind: "fallback", to: `/orgs/${orgSlug}` },
    };
  }
  if (/^\/(?:organizations|orgs)\/[^/]+\/recruiting-chat\/events\/new$/.test(p)) {
    const orgSlug = p.split("/")[2];
    return {
      title: "チャット内イベント",
      back: {
        kind: "history-or-fallback",
        to: withRecruitingChatQuery(
          `/organizations/${orgSlug}/recruiting-chat/events`,
          search
        ),
      },
    };
  }
  if (/^\/(?:organizations|orgs)\/[^/]+\/recruiting-chat\/events\/\d+\/edit$/.test(p)) {
    const orgSlug = p.split("/")[2];
    const eventId = p.split("/")[5];
    return {
      title: "チャット内イベントを編集",
      back: {
        kind: "history-or-fallback",
        to: withRecruitingChatQuery(
          `/organizations/${orgSlug}/recruiting-chat/events/${eventId}`,
          search
        ),
      },
    };
  }
  if (/^\/(?:organizations|orgs)\/[^/]+\/recruiting-chat\/events\/\d+$/.test(p)) {
    const orgSlug = p.split("/")[2];
    return {
      title: "チャット内イベント",
      back: {
        kind: "history-or-fallback",
        to: withRecruitingChatQuery(
          `/organizations/${orgSlug}/recruiting-chat/events`,
          search
        ),
      },
    };
  }
  if (/^\/(?:organizations|orgs)\/[^/]+\/recruiting-chat\/events$/.test(p)) {
    const orgSlug = p.split("/")[2];
    return {
      title: "チャット内イベント",
      back: {
        kind: "history-or-fallback",
        to: recruitingChatSafeBack(orgSlug, search),
      },
    };
  }
  if (/^\/(?:organizations|orgs)\/[^/]+\/recruiting-chat\/info$/.test(p)) {
    const orgSlug = p.split("/")[2];
    return {
      title: "チャット詳細",
      back: { kind: "fallback", to: `/organizations/${orgSlug}/recruiting-chat` },
    };
  }
  if (/^\/(?:organizations|orgs)\/[^/]+\/recruiting-chat\/settings$/.test(p)) {
    const orgSlug = p.split("/")[2];
    return {
      title: "団体チャット設定",
      back: { kind: "fallback", to: `/organizations/${orgSlug}/recruiting-chat/info` },
    };
  }
  if (/^\/(?:organizations|orgs)\/[^/]+\/recruiting-chat\/applications$/.test(p)) {
    const orgSlug = p.split("/")[2];
    return {
      title: "参加申請",
      back: { kind: "fallback", to: `/organizations/${orgSlug}/recruiting-chat/info` },
    };
  }
  if (/^\/(?:organizations|orgs)\/[^/]+\/recruiting-chat\/members$/.test(p)) {
    const orgSlug = p.split("/")[2];
    return {
      title: "参加者管理",
      back: { kind: "fallback", to: `/organizations/${orgSlug}/recruiting-chat/info` },
    };
  }
  if (/^\/(?:organizations|orgs)\/[^/]+\/recruiting-chat\/invites$/.test(p)) {
    const orgSlug = p.split("/")[2];
    return {
      title: "学生を招待",
      back: { kind: "fallback", to: `/organizations/${orgSlug}/recruiting-chat/info` },
    };
  }
  if (/^\/(?:organizations|orgs)\/[^/]+\/recruiting-chat\/invite$/.test(p)) {
    const orgSlug = p.split("/")[2];
    return {
      title: "団体チャット招待",
      back: { kind: "fallback", to: `/orgs/${orgSlug}` },
    };
  }
  if (/^\/dm\/groups\/\d+\/info$/.test(p)) {
    const roomPk = p.split("/")[3];
    return {
      title: "グループ情報",
      back: { kind: "fallback", to: `/dm/groups/${roomPk}` },
    };
  }
  if (/^\/orgs\/[^/]+\/edit$/.test(p)) {
    const orgSlug = p.split("/")[2];
    return {
      title: "団体を編集",
      back: { kind: "fallback", to: `/orgs/${orgSlug}` },
    };
  }
  if (/^\/orgs\/[^/]+$/.test(p)) {
    return { title: "団体", back: { kind: "fallback", to: "/" } };
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
  if (p === "/settings/profile") {
    return {
      title: "プロフィール設定",
      back: { kind: "history-or-fallback", to: "/" },
    };
  }
  if (p === "/settings/linked-account") {
    return {
      title: "アカウントを追加",
      back: { kind: "history-or-fallback", to: "/more" },
    };
  }
  if (p.startsWith("/settings")) {
    return {
      title: "設定",
      back: { kind: "history-or-fallback", to: "/" },
    };
  }
  if (p === "/dm/requests") {
    return { title: "リクエスト", back: { kind: "fallback", to: "/dm" } };
  }
  if (p === "/dm/new") {
    return {
      title: "新しいチャット",
      back: { kind: "history-or-fallback", to: "/dm" },
    };
  }
  if (p === "/dm/new/direct") {
    return {
      title: "個人チャット",
      back: { kind: "history-or-fallback", to: "/dm/new" },
    };
  }
  if (p === "/dm/new/org-chat") {
    return {
      title: "団体チャット",
      back: { kind: "history-or-fallback", to: "/dm/new" },
    };
  }
  if (p === "/dm/groups/new") {
    return {
      title: "グループ作成",
      back: { kind: "history-or-fallback", to: "/dm/new" },
    };
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
  state?: unknown,
  search = ""
): DetailBackTarget {
  const chrome = matchDetailChrome(pathname, search);
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
    return { mode: "path", to: chrome.back.to, replace: true };
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
