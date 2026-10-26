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
  document?: ListenerTarget;
};

export type BindChatVisibleFrameOptions = {
  onFrame?: (frame: ChatVisibleFrame) => void;
};

/**
 * Visible chat frame in CSS pixels.
 *
 * Capacitor WKWebView often pans visualViewport.offsetTop without shrinking
 * visualViewport.height. Using that unclipped height with top: offsetTop puts
 * the compose bar below the keyboard. Clip so offsetTop + height <= innerHeight.
 * Never subtract keyboard height as a separate term.
 */
export function readChatVisibleFrame(input: {
  visualViewport?: VisualViewportLike;
  innerHeight: number;
}): ChatVisibleFrame {
  const inner = Math.max(0, Math.round(input.innerHeight || 0));
  const rawHeight = input.visualViewport?.height;
  const reportedHeight =
    rawHeight != null && Number.isFinite(rawHeight) && rawHeight > 0
      ? Math.round(rawHeight)
      : inner;
  const rawOffset = input.visualViewport?.offsetTop;
  const offsetTop =
    rawOffset != null && Number.isFinite(rawOffset) && rawOffset > 0
      ? Math.round(rawOffset)
      : 0;
  const maxHeight = Math.max(0, inner - offsetTop);
  const height =
    maxHeight > 0 ? Math.min(reportedHeight, maxHeight) : reportedHeight;
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
  style: StyleProps,
  options?: BindChatVisibleFrameOptions
): () => void {
  let active = true;
  let resetting = false;
  let lastResetX = 0;
  let lastResetY = 0;

  const applyFrame = () => {
    const frame = readChatVisibleFrame({
      visualViewport: host.visualViewport,
      innerHeight: host.innerHeight,
    });
    applyChatVisibleFrame(style, frame);
    options?.onFrame?.(frame);
    return frame;
  };

  const sync = () => {
    if (!active || resetting) return;
    applyFrame();
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

  const onFocusIn = () => {
    if (!active) return;
    applyFrame();
  };

  sync();
  const vv = host.visualViewport;
  vv?.addEventListener("resize", sync);
  vv?.addEventListener("scroll", sync);
  host.addEventListener("resize", sync);
  host.document?.addEventListener("focusin", onFocusIn);

  return () => {
    active = false;
    vv?.removeEventListener("resize", sync);
    vv?.removeEventListener("scroll", sync);
    host.removeEventListener("resize", sync);
    host.document?.removeEventListener("focusin", onFocusIn);
    clearChatVisibleFrame(style);
  };
}
