import { normalizeSpaPath } from "./tabs.ts";

/**
 * Message stack: inbox + personal/group/recruiting conversation rooms.
 * Used for iOS-style push/pop only — not course/trade/settings/other details.
 */
export function isMessageStackPath(pathname: string): boolean {
  const p = normalizeSpaPath(pathname);
  if (p === "/dm") return true;
  if (/^\/dm\/\d+$/.test(p)) return true;
  if (/^\/dm\/groups\/\d+$/.test(p)) return true;
  if (/^\/dm\/recruiting\/[^/]+$/.test(p)) return true;
  if (/^\/(?:organizations|orgs)\/[^/]+\/recruiting-chat$/.test(p)) return true;
  return false;
}

export function isDmInboxPath(pathname: string): boolean {
  return normalizeSpaPath(pathname) === "/dm";
}

export const DM_INBOX_SCROLL_KEY = "/dm";

export const STACK_POP_STATE_KEY = "waseStackPop";

export function isStackPopState(state: unknown): boolean {
  if (!state || typeof state !== "object") return false;
  return Boolean((state as { waseStackPop?: unknown }).waseStackPop);
}

export function stackPopState(): { waseStackPop: true } {
  return { waseStackPop: true };
}
