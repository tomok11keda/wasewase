export const TAB_ROUTES = [
  {
    id: "home",
    path: "/",
    label: "タイムライン",
    title: "タイムライン",
    icon: "M10 20v-6h4v6h5v-8h3L12 3 2 12h3v8h5z",
  },
  {
    id: "communities",
    path: "/communities",
    label: "コミュニティ",
    title: "コミュニティ",
    icon: "M16 11c1.66 0 2.99-1.34 2.99-3S17.66 5 16 5c-1.66 0-3 1.34-3 3s1.34 3 3 3zm-8 0c1.66 0 2.99-1.34 2.99-3S9.66 5 8 5C6.34 5 5 6.34 5 8s1.34 3 3 3zm0 2c-2.33 0-7 1.17-7 3.5V19h14v-2.5c0-2.33-4.67-3.5-7-3.5zm8 0c-.29 0-.62.02-.97.05 1.16.84 1.97 1.97 1.97 3.45V19h6v-2.5c0-2.33-4.67-3.5-7-3.5z",
  },
  {
    id: "search",
    path: "/search",
    label: "検索",
    title: "検索",
    icon: "M15.5 14h-.79l-.28-.27A6.471 6.471 0 0 0 16 9.5 6.5 6.5 0 1 0 9.5 16c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 11.99 14 9.5 14z",
  },
  {
    id: "flea",
    path: "/flea",
    label: "フリマ",
    title: "フリマ",
    icon: "M7 18c-1.1 0-1.99.9-1.99 2S5.9 22 7 22s2-.9 2-2-.9-2-2-2zM1 2v2h2l3.6 7.59-1.35 2.45c-.16.28-.25.61-.25.96 0 1.1.9 2 2 2h12v-2H7.42c-.14 0-.25-.11-.25-.25l.03-.12.9-1.63h7.45c.75 0 1.41-.41 1.75-1.03l3.58-6.49A1.003 1.003 0 0 0 20 4H5.21l-.94-2H1zm16 16c-1.1 0-1.99.9-1.99 2s.89 2 1.99 2 2-.9 2-2-.9-2-2-2z",
  },
  {
    id: "timetable",
    path: "/timetable",
    label: "時間割",
    title: "時間割",
    icon: "M19 4h-1V2h-2v2H8V2H6v2H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2zm0 16H5V10h14v10zm0-12H5V6h14v2zM7 12h5v5H7v-5z",
  },
] as const;

export type TabId = (typeof TAB_ROUTES)[number]["id"];

/** BottomNav primary tabs that participate in keep-alive (exact path only). */
export type MainTabId = TabId;

/**
 * Exact main-tab match. Nested routes like /flea/products/1 return null
 * so they render through <Outlet /> while keep-alive panes stay mounted (hidden).
 * /more is no longer a bottom tab — it renders via Outlet when visited.
 */
export function matchMainTab(pathname: string): MainTabId | null {
  const normalized = pathname.replace(/\/$/, "") || "/";
  if (normalized === "/" || normalized === "") return "home";
  if (normalized === "/communities") return "communities";
  if (normalized === "/search") return "search";
  if (normalized === "/flea") return "flea";
  if (normalized === "/timetable") return "timetable";
  return null;
}

/**
 * Normalize SPA pathnames.
 * React Router usually strips basename `/app`, but Capacitor / deep links
 * may still surface `/app/...` — strip it so conversation matching is reliable.
 */
export function normalizeSpaPath(pathname: string): string {
  let p = (pathname || "/").replace(/\/$/, "") || "/";
  if (p === "/app") return "/";
  if (p.startsWith("/app/")) p = p.slice(4) || "/";
  return p;
}

/**
 * Conversation / chat screens: message reading & composing.
 * Shared layout rule — keep inbox / request list / group create visible.
 */
export function isConversationPath(pathname: string): boolean {
  const p = normalizeSpaPath(pathname);

  // Trade chat (flea buyer/seller messaging)
  if (/^\/flea\/chats\/[^/]+$/.test(p)) return true;

  // Group create keeps bottom nav
  if (p === "/dm/groups/new") return false;

  // Group chat room
  if (/^\/dm\/groups\/[^/]+$/.test(p)) return true;

  // DM inbox & message-request list keep bottom nav
  if (p === "/dm" || p === "/dm/requests") return false;

  // 1:1 DM / message-request detail (numeric room id)
  if (/^\/dm\/\d+$/.test(p)) return true;

  // Any other /dm/:segment room-like path (future chat types)
  if (p.startsWith("/dm/")) {
    const rest = p.slice("/dm/".length);
    if (!rest || rest === "requests" || rest.startsWith("groups")) return false;
    return true;
  }

  return false;
}

/**
 * Conversation screens hide the mobile bottom tab bar so the composer +
 * keyboard can use the full height. Inbox / request list / group create keep it.
 */
export function shouldHideBottomNav(pathname: string): boolean {
  return isConversationPath(pathname);
}
