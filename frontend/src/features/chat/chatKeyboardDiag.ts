import {
  readChatVisibleFrame,
  type ChatVisibleFrame,
} from "./chatVisibleFrame.ts";

export const CHAT_KB_DIAG_PARAM = "chat_kb_diag";
export const CHAT_KB_DIAG_STORAGE_KEY = "wase_chat_kb_diag";

type StorageLike = {
  getItem: (key: string) => string | null;
  setItem?: (key: string, value: string) => void;
  removeItem?: (key: string) => void;
};

export function isChatKeyboardDiagEnabled(search: string): boolean {
  return isChatKeyboardDiagRequested({ search });
}

export function isChatKeyboardDiagRequested(input: {
  search: string;
  storage?: StorageLike | null;
}): boolean {
  try {
    const params = new URLSearchParams(
      input.search.startsWith("?") ? input.search.slice(1) : input.search
    );
    const flag = params.get(CHAT_KB_DIAG_PARAM);
    if (flag === "1") return true;
    if (flag === "0" || flag === "clear") return false;
  } catch {
    /* ignore */
  }
  try {
    return input.storage?.getItem(CHAT_KB_DIAG_STORAGE_KEY) === "1";
  } catch {
    return false;
  }
}

/** Persist query so in-app navigations keep the flag. */
export function syncChatKeyboardDiagRequest(input: {
  search: string;
  storage?: StorageLike | null;
}): boolean {
  const params = (() => {
    try {
      return new URLSearchParams(
        input.search.startsWith("?") ? input.search.slice(1) : input.search
      );
    } catch {
      return null;
    }
  })();
  const flag = params?.get(CHAT_KB_DIAG_PARAM);
  try {
    if (flag === "1") {
      input.storage?.setItem?.(CHAT_KB_DIAG_STORAGE_KEY, "1");
      return true;
    }
    if (flag === "0" || flag === "clear") {
      input.storage?.removeItem?.(CHAT_KB_DIAG_STORAGE_KEY);
      return false;
    }
  } catch {
    /* ignore quota / private mode */
  }
  return isChatKeyboardDiagRequested(input);
}

export function shouldShowChatKeyboardDiag(input: {
  requested: boolean;
  isConversation: boolean;
  isDev: boolean;
  isStaff?: boolean;
  isSuperuser?: boolean;
}): boolean {
  if (!input.requested || !input.isConversation) return false;
  if (input.isDev) return true;
  return Boolean(input.isStaff || input.isSuperuser);
}

type RectBits = {
  top: number;
  bottom: number;
  height: number;
} | null;

export type ChatKeyboardDiagRects = {
  page: RectBits;
  messages: RectBits;
  compose: RectBits;
  input: RectBits;
  send: RectBits;
};

export type ChatKeyboardDiagSnapshot = {
  innerHeight: number;
  outerHeight: number;
  scrollY: number;
  vvHeight: number | null;
  vvOffsetTop: number | null;
  vvPageTop: number | null;
  vvScale: number | null;
  frameHeight: number;
  frameOffsetTop: number;
  cssVisibleH: number | null;
  cssVvOffset: number | null;
  cssSat: number | null;
  cssSab: number | null;
  cssSaiTop: number | null;
  cssSaiBottom: number | null;
  cssChrome: number | null;
  cssHeaderH: number | null;
  pageTop: number | null;
  pageBottom: number | null;
  pageHeight: number | null;
  messagesTop: number | null;
  messagesBottom: number | null;
  composeTop: number | null;
  composeBottom: number | null;
  composeHeight: number | null;
  inputTop: number | null;
  inputBottom: number | null;
  sendTop: number | null;
  sendBottom: number | null;
  lastEvent: string;
};

function roundOrNull(value: number | null | undefined): number | null {
  return value == null || !Number.isFinite(value) ? null : Math.round(value);
}

function parseCssPx(style: { getPropertyValue: (name: string) => string }, name: string): number | null {
  const raw = style.getPropertyValue(name).trim();
  if (!raw) return null;
  const n = Number.parseFloat(raw);
  return Number.isFinite(n) ? Math.round(n) : null;
}

/** Geometry only — never include message text or user identifiers. */
export function readChatKeyboardDiagSnapshot(input: {
  innerHeight: number;
  outerHeight?: number;
  scrollY: number;
  visualViewport?: {
    height: number;
    offsetTop: number;
    pageTop?: number;
    scale?: number;
  } | null;
  frame: ChatVisibleFrame;
  rects: ChatKeyboardDiagRects;
  css?: { getPropertyValue: (name: string) => string } | null;
  sai?: {
    top?: number;
    bottom?: number;
  } | null;
  lastEvent?: string;
}): ChatKeyboardDiagSnapshot {
  const event = (input.lastEvent || "").trim() || "init";
  return {
    innerHeight: Math.round(input.innerHeight || 0),
    outerHeight: Math.round(input.outerHeight || 0),
    scrollY: Math.round(input.scrollY || 0),
    vvHeight: roundOrNull(input.visualViewport?.height),
    vvOffsetTop: roundOrNull(input.visualViewport?.offsetTop),
    vvPageTop: roundOrNull(input.visualViewport?.pageTop),
    vvScale:
      input.visualViewport?.scale != null &&
      Number.isFinite(input.visualViewport.scale)
        ? Math.round(input.visualViewport.scale * 100) / 100
        : null,
    frameHeight: input.frame.height,
    frameOffsetTop: input.frame.offsetTop,
    cssVisibleH: input.css ? parseCssPx(input.css, "--chat-visible-h") : null,
    cssVvOffset: input.css ? parseCssPx(input.css, "--chat-vv-offset") : null,
    cssSat: input.css ? parseCssPx(input.css, "--wase-sat") : null,
    cssSab: input.css ? parseCssPx(input.css, "--wase-sab") : null,
    cssSaiTop: roundOrNull(input.sai?.top),
    cssSaiBottom: roundOrNull(input.sai?.bottom),
    cssChrome: input.css ? parseCssPx(input.css, "--wase-chrome-offset") : null,
    cssHeaderH: input.css ? parseCssPx(input.css, "--wase-header-h") : null,
    pageTop: roundOrNull(input.rects.page?.top),
    pageBottom: roundOrNull(input.rects.page?.bottom),
    pageHeight: roundOrNull(input.rects.page?.height),
    messagesTop: roundOrNull(input.rects.messages?.top),
    messagesBottom: roundOrNull(input.rects.messages?.bottom),
    composeTop: roundOrNull(input.rects.compose?.top),
    composeBottom: roundOrNull(input.rects.compose?.bottom),
    composeHeight: roundOrNull(input.rects.compose?.height),
    inputTop: roundOrNull(input.rects.input?.top),
    inputBottom: roundOrNull(input.rects.input?.bottom),
    sendTop: roundOrNull(input.rects.send?.top),
    sendBottom: roundOrNull(input.rects.send?.bottom),
    lastEvent: event.slice(0, 24),
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
    messages: rectBits(root.querySelector(".dm-message-area")),
    compose: rectBits(compose),
    input: rectBits(
      compose?.querySelector(".chat-compose-bar__input") ?? null
    ),
    send: rectBits(compose?.querySelector(".chat-compose-bar__send") ?? null),
  };
}

export function formatChatKeyboardDiagLines(
  snap: ChatKeyboardDiagSnapshot
): string[] {
  const n = (value: number | null | undefined) =>
    value == null ? "-" : String(value);
  return [
    `KB ${snap.lastEvent}`,
    `inH ${snap.innerHeight} outH ${snap.outerHeight} scY ${snap.scrollY}`,
    `vvH ${n(snap.vvHeight)} vvOT ${n(snap.vvOffsetTop)} vvPT ${n(snap.vvPageTop)} sc ${n(snap.vvScale)}`,
    `frH ${snap.frameHeight} frOT ${snap.frameOffsetTop}`,
    `cssH ${n(snap.cssVisibleH)} cssOT ${n(snap.cssVvOffset)} sat ${n(snap.cssSat)} sab ${n(snap.cssSab)}`,
    `sai ${n(snap.cssSaiTop)}/${n(snap.cssSaiBottom)} ch ${n(snap.cssChrome)} hd ${n(snap.cssHeaderH)}`,
    `page ${n(snap.pageTop)}-${n(snap.pageBottom)} h${n(snap.pageHeight)}`,
    `msg ${n(snap.messagesTop)}-${n(snap.messagesBottom)}`,
    `bar ${n(snap.composeTop)}-${n(snap.composeBottom)} h${n(snap.composeHeight)}`,
    `inp ${n(snap.inputTop)}-${n(snap.inputBottom)} send ${n(snap.sendTop)}-${n(snap.sendBottom)}`,
  ];
}

export function captureChatKeyboardDiagSnapshot(
  host: {
    innerHeight: number;
    outerHeight?: number;
    scrollY: number;
    visualViewport?: {
      height: number;
      offsetTop: number;
      pageTop?: number;
      scale?: number;
    } | null;
    root?: ParentNode | null;
    css?: { getPropertyValue: (name: string) => string } | null;
    sai?: { top?: number; bottom?: number } | null;
  },
  lastEvent = "init"
): ChatKeyboardDiagSnapshot {
  return readChatKeyboardDiagSnapshot({
    innerHeight: host.innerHeight,
    outerHeight: host.outerHeight,
    scrollY: host.scrollY,
    visualViewport: host.visualViewport,
    frame: readChatVisibleFrame({
      visualViewport: host.visualViewport,
      innerHeight: host.innerHeight,
    }),
    rects: host.root
      ? collectChatKeyboardDiagRects(host.root)
      : {
          page: null,
          messages: null,
          compose: null,
          input: null,
          send: null,
        },
    css: host.css,
    sai: host.sai,
    lastEvent,
  });
}

export function chatKeyboardDiagOverlayPins(offsetTop: number | null): Array<{
  id: "A" | "B";
  top: number;
}> {
  const offset = Math.max(0, offsetTop ?? 0);
  if (offset === 0) return [{ id: "A", top: 0 }];
  return [
    { id: "A", top: 0 },
    { id: "B", top: offset },
  ];
}

type ListenerTarget = {
  addEventListener: (type: string, listener: () => void) => void;
  removeEventListener: (type: string, listener: () => void) => void;
};

export function bindChatKeyboardDiagListeners(
  host: ListenerTarget & {
    visualViewport?: ListenerTarget | null;
    document?: ListenerTarget | null;
  },
  onEvent: (name: string) => void
): () => void {
  let active = true;
  const fire = (name: string) => {
    if (!active) return;
    onEvent(name);
  };
  const onResize = () => fire("win.resize");
  const onVvResize = () => fire("vv.resize");
  const onVvScroll = () => fire("vv.scroll");
  const onFocusIn = () => fire("focusin");
  const onFocusOut = () => fire("focusout");

  host.addEventListener("resize", onResize);
  host.visualViewport?.addEventListener("resize", onVvResize);
  host.visualViewport?.addEventListener("scroll", onVvScroll);
  host.document?.addEventListener("focusin", onFocusIn);
  host.document?.addEventListener("focusout", onFocusOut);
  fire("init");

  return () => {
    active = false;
    host.removeEventListener("resize", onResize);
    host.visualViewport?.removeEventListener("resize", onVvResize);
    host.visualViewport?.removeEventListener("scroll", onVvScroll);
    host.document?.removeEventListener("focusin", onFocusIn);
    host.document?.removeEventListener("focusout", onFocusOut);
  };
}
