import { useEffect, useRef, type RefObject } from "react";

const NEAR_BOTTOM_PX = 96;

/**
 * Track the *visible* frame height for chat rooms.
 *
 * Uses visualViewport.height (fallback: innerHeight) only — never subtracts
 * keyboard height separately. That avoids double-counting when Capacitor /
 * WKWebView already resized the webview for the keyboard.
 */
export function useChatVisibleFrameHeight(enabled: boolean): void {
  useEffect(() => {
    if (!enabled) return;
    const root = document.documentElement;

    const sync = () => {
      const vv = window.visualViewport;
      const h = Math.round(vv?.height ?? window.innerHeight);
      if (h > 0) {
        root.style.setProperty("--chat-visible-h", `${h}px`);
      }
    };

    sync();
    const vv = window.visualViewport;
    vv?.addEventListener("resize", sync);
    vv?.addEventListener("scroll", sync);
    window.addEventListener("resize", sync);

    return () => {
      vv?.removeEventListener("resize", sync);
      vv?.removeEventListener("scroll", sync);
      window.removeEventListener("resize", sync);
      root.style.removeProperty("--chat-visible-h");
    };
  }, [enabled]);
}

/** True when the thread scroller is already near the latest messages. */
export function isChatNearBottom(scroller: HTMLElement | null): boolean {
  if (!scroller) return true;
  const gap =
    scroller.scrollHeight - scroller.scrollTop - scroller.clientHeight;
  return gap <= NEAR_BOTTOM_PX;
}

/** Scroll only the thread pane — never the document (avoids iOS keyboard gaps). */
export function scrollChatToBottom(
  scroller: HTMLElement | null,
  behavior: ScrollBehavior = "auto"
): void {
  if (!scroller) return;
  if (behavior === "smooth" && "scrollTo" in scroller) {
    scroller.scrollTo({ top: scroller.scrollHeight, behavior: "smooth" });
    return;
  }
  scroller.scrollTop = scroller.scrollHeight;
}

/**
 * Keep latest messages visible when the composer grows / keyboard opens,
 * but only if the user was already near the bottom.
 */
export function useKeepChatPinnedOnCompose(
  scrollerRef: RefObject<HTMLElement | null>,
  enabled: boolean
): void {
  const wasNearBottomRef = useRef(true);

  useEffect(() => {
    if (!enabled) return;
    const scroller = scrollerRef.current;
    if (!scroller) return;

    const onScroll = () => {
      wasNearBottomRef.current = isChatNearBottom(scroller);
    };
    onScroll();
    scroller.addEventListener("scroll", onScroll, { passive: true });

    const vv = window.visualViewport;
    const onViewport = () => {
      if (wasNearBottomRef.current) {
        scrollChatToBottom(scroller, "auto");
      }
    };
    vv?.addEventListener("resize", onViewport);

    return () => {
      scroller.removeEventListener("scroll", onScroll);
      vv?.removeEventListener("resize", onViewport);
    };
  }, [enabled, scrollerRef]);
}
