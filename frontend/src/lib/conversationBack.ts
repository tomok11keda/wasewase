import { useLocation, type NavigateFunction } from "react-router-dom";
import { isAuthOrDiagRoute } from "./pushPrePermission.ts";
import { normalizeSpaPath } from "./tabs.ts";

export const CONVERSATION_BACK_STATE_KEY = "waseConversationBack";

export type ConversationBackOrigin = {
  sessionId: string;
  fromPath: string;
  fromKey: string;
};

export type ConversationBackTarget =
  | { mode: "history" }
  | { mode: "path"; to: string; replace: true };

export type ConversationBackLocation = {
  pathname?: string;
  search?: string;
  key?: string;
};

function newSessionId(): string {
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}

function originPath(location: ConversationBackLocation): string {
  const pathname = normalizeSpaPath(location.pathname || "/");
  const search = location.search || "";
  return `${pathname}${search}`;
}

function pathnameOf(fromPath: string): string {
  return normalizeSpaPath((fromPath || "/").split("?")[0] || "/");
}

export function isSafeConversationBackOrigin(fromPath: string): boolean {
  const pathname = pathnameOf(fromPath);
  if (!pathname.startsWith("/")) return false;
  if (isAuthOrDiagRoute(pathname)) return false;
  return true;
}

function readRecord(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  return value as Record<string, unknown>;
}

export function createConversationBackController(
  sessionId = newSessionId()
) {
  function originFrom(
    location: ConversationBackLocation
  ): ConversationBackOrigin {
    return {
      sessionId,
      fromPath: originPath(location),
      fromKey: String(location.key || ""),
    };
  }

  function withState(
    location: ConversationBackLocation,
    extra?: unknown
  ): Record<string, unknown> {
    const extraRecord = readRecord(extra);
    const base = extraRecord ? { ...extraRecord } : {};
    return {
      ...base,
      [CONVERSATION_BACK_STATE_KEY]: originFrom(location),
    };
  }

  function readOrigin(state: unknown): ConversationBackOrigin | null {
    const raw = readRecord(state)?.[CONVERSATION_BACK_STATE_KEY];
    const origin = readRecord(raw);
    if (!origin) return null;
    if (typeof origin.sessionId !== "string" || !origin.sessionId) return null;
    if (typeof origin.fromPath !== "string" || !origin.fromPath) return null;
    if (typeof origin.fromKey !== "string" || !origin.fromKey) return null;
    return {
      sessionId: origin.sessionId,
      fromPath: origin.fromPath,
      fromKey: origin.fromKey,
    };
  }

  function canPop(state: unknown): boolean {
    const origin = readOrigin(state);
    if (!origin) return false;
    if (origin.sessionId !== sessionId) return false;
    if (!isSafeConversationBackOrigin(origin.fromPath)) return false;
    return true;
  }

  function resolve(
    state: unknown,
    fallbackTo: string
  ): ConversationBackTarget {
    if (canPop(state)) return { mode: "history" };
    return { mode: "path", to: fallbackTo, replace: true };
  }

  function execute(
    navigate: NavigateFunction,
    fallbackTo: string,
    state: unknown
  ): void {
    const dest = resolve(state, fallbackTo);
    if (dest.mode === "history") {
      navigate(-1);
      return;
    }
    navigate(dest.to, { replace: true });
  }

  return {
    sessionId,
    withState,
    readOrigin,
    canPop,
    resolve,
    execute,
  };
}

export const conversationBack = createConversationBackController();

export function withConversationBackState(
  location: ConversationBackLocation,
  extra?: unknown
): Record<string, unknown> {
  return conversationBack.withState(location, extra);
}

/** Stamp the current SPA location so a conversation header can POP later. */
export function useConversationBackState(
  extra?: unknown
): Record<string, unknown> {
  const location = useLocation();
  return conversationBack.withState(location, extra);
}
