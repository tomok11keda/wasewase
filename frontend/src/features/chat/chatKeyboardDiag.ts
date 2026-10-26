import type { ChatVisibleFrame } from "./chatVisibleFrame";

export const CHAT_KB_DIAG_PARAM = "chat_kb_diag";

export function isChatKeyboardDiagEnabled(search: string): boolean {
  try {
    return new URLSearchParams(search).get(CHAT_KB_DIAG_PARAM) === "1";
  } catch {
    return false;
  }
}

type RectBits = {
  top: number;
  bottom: number;
  height: number;
} | null;

export type ChatKeyboardDiagRects = {
  page: RectBits;
  compose: RectBits;
  input: RectBits;
  send: RectBits;
};

export type ChatKeyboardDiagSnapshot = {
  innerHeight: number;
  scrollY: number;
  vvHeight: number | null;
  vvOffsetTop: number | null;
  frameHeight: number;
  frameOffsetTop: number;
  pageTop: number | null;
  pageBottom: number | null;
  pageHeight: number | null;
  composeTop: number | null;
  composeBottom: number | null;
  composeHeight: number | null;
  inputTop: number | null;
  inputBottom: number | null;
  sendTop: number | null;
  sendBottom: number | null;
};

function roundOrNull(value: number | null | undefined): number | null {
  return value == null || !Number.isFinite(value) ? null : Math.round(value);
}

/** Geometry only — never include message text or user identifiers. */
export function readChatKeyboardDiagSnapshot(input: {
  innerHeight: number;
  scrollY: number;
  visualViewport?: { height: number; offsetTop: number } | null;
  frame: ChatVisibleFrame;
  rects: ChatKeyboardDiagRects;
}): ChatKeyboardDiagSnapshot {
  return {
    innerHeight: Math.round(input.innerHeight || 0),
    scrollY: Math.round(input.scrollY || 0),
    vvHeight: roundOrNull(input.visualViewport?.height),
    vvOffsetTop: roundOrNull(input.visualViewport?.offsetTop),
    frameHeight: input.frame.height,
    frameOffsetTop: input.frame.offsetTop,
    pageTop: roundOrNull(input.rects.page?.top),
    pageBottom: roundOrNull(input.rects.page?.bottom),
    pageHeight: roundOrNull(input.rects.page?.height),
    composeTop: roundOrNull(input.rects.compose?.top),
    composeBottom: roundOrNull(input.rects.compose?.bottom),
    composeHeight: roundOrNull(input.rects.compose?.height),
    inputTop: roundOrNull(input.rects.input?.top),
    inputBottom: roundOrNull(input.rects.input?.bottom),
    sendTop: roundOrNull(input.rects.send?.top),
    sendBottom: roundOrNull(input.rects.send?.bottom),
  };
}

function rectBits(el: Element | null): RectBits {
  if (!el) return null;
  const r = el.getBoundingClientRect();
  return { top: r.top, bottom: r.bottom, height: r.height };
}

export function collectChatKeyboardDiagRects(
  root: ParentNode
): ChatKeyboardDiagRects {
  const page = root.querySelector(".dm-room-page");
  const compose = root.querySelector(".chat-compose-bar");
  return {
    page: rectBits(page),
    compose: rectBits(compose),
    input: rectBits(
      compose?.querySelector(".chat-compose-bar__input") ?? null
    ),
    send: rectBits(compose?.querySelector(".chat-compose-bar__send") ?? null),
  };
}
