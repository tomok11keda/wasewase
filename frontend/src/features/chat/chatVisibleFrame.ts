export type VisualViewportLike = {
  height: number;
  offsetTop: number;
} | null | undefined;

export type ChatVisibleFrame = {
  height: number;
  offsetTop: number;
};

type StyleProps = {
  setProperty: (name: string, value: string) => void;
  removeProperty: (name: string) => void;
};

type ListenerTarget = {
  addEventListener: (type: string, listener: () => void) => void;
  removeEventListener: (type: string, listener: () => void) => void;
};

export type ChatVisibleFrameHost = ListenerTarget & {
  innerHeight: number;
  scrollX: number;
  scrollY: number;
  scrollTo: (x: number, y: number) => void;
  visualViewport?: (ListenerTarget & {
    height: number;
    offsetTop: number;
  }) | null;
};

/**
 * Visible chat frame in CSS pixels.
 *
 * Height follows visualViewport.height (fallback: innerHeight). Never subtract
 * keyboard height separately — Capacitor / WKWebView may already have resized.
 * offsetTop is the visual viewport's shift inside the layout viewport. Home
 * compose uses the same pair for position:fixed, so we do not also translateY.
 */
export function readChatVisibleFrame(input: {
  visualViewport?: VisualViewportLike;
  innerHeight: number;
}): ChatVisibleFrame {
  const fallback = Math.max(0, Math.round(input.innerHeight || 0));
  const rawHeight = input.visualViewport?.height;
  const height =
    rawHeight != null && Number.isFinite(rawHeight) && rawHeight > 0
      ? Math.round(rawHeight)
      : fallback;
  const rawOffset = input.visualViewport?.offsetTop;
  const offsetTop =
    rawOffset != null && Number.isFinite(rawOffset) && rawOffset > 0
      ? Math.round(rawOffset)
      : 0;
  return { height, offsetTop };
}

/** Notch padding still needed after the visual viewport has panned. */
export function chatOverlayPadTop(
  chromeOffset: number,
  offsetTop: number
): number {
  const chrome = Math.max(0, Math.round(chromeOffset || 0));
  const offset = Math.max(0, Math.round(offsetTop || 0));
  return Math.max(0, chrome - offset);
}

export function shouldResetDocumentScroll(
  scrollX: number,
  scrollY: number
): boolean {
  return (scrollX || 0) !== 0 || (scrollY || 0) !== 0;
}

export function applyChatVisibleFrame(
  style: Pick<StyleProps, "setProperty">,
  frame: ChatVisibleFrame
): void {
  if (frame.height > 0) {
    style.setProperty("--chat-visible-h", `${frame.height}px`);
  }
  style.setProperty("--chat-vv-offset", `${frame.offsetTop}px`);
}

export function clearChatVisibleFrame(
  style: Pick<StyleProps, "removeProperty">
): void {
  style.removeProperty("--chat-visible-h");
  style.removeProperty("--chat-vv-offset");
}

export function syncChatVisibleFrame(
  host: Pick<
    ChatVisibleFrameHost,
    "visualViewport" | "innerHeight" | "scrollX" | "scrollY" | "scrollTo"
  >,
  style: Pick<StyleProps, "setProperty">
): ChatVisibleFrame {
  const frame = readChatVisibleFrame({
    visualViewport: host.visualViewport,
    innerHeight: host.innerHeight,
  });
  applyChatVisibleFrame(style, frame);
  if (shouldResetDocumentScroll(host.scrollX, host.scrollY)) {
    host.scrollTo(0, 0);
  }
  return frame;
}

/** Subscribe to visualViewport resize/scroll + window resize. Returns unbind. */
export function bindChatVisibleFrame(
  host: ChatVisibleFrameHost,
  style: StyleProps
): () => void {
  let active = true;
  let resetting = false;
  let lastResetX = 0;
  let lastResetY = 0;

  const sync = () => {
    if (!active || resetting) return;
    const frame = readChatVisibleFrame({
      visualViewport: host.visualViewport,
      innerHeight: host.innerHeight,
    });
    applyChatVisibleFrame(style, frame);
    const x = host.scrollX || 0;
    const y = host.scrollY || 0;
    if (!shouldResetDocumentScroll(x, y)) {
      lastResetX = 0;
      lastResetY = 0;
      return;
    }
    if (x === lastResetX && y === lastResetY) return;
    lastResetX = x;
    lastResetY = y;
    resetting = true;
    try {
      host.scrollTo(0, 0);
    } finally {
      resetting = false;
    }
  };

  sync();
  const vv = host.visualViewport;
  vv?.addEventListener("resize", sync);
  vv?.addEventListener("scroll", sync);
  host.addEventListener("resize", sync);

  return () => {
    active = false;
    vv?.removeEventListener("resize", sync);
    vv?.removeEventListener("scroll", sync);
    host.removeEventListener("resize", sync);
    clearChatVisibleFrame(style);
  };
}
