import {
  useEffect,
  useRef,
  useState,
  type Dispatch,
  type RefObject,
  type SetStateAction,
} from "react";
import {
  bindChatVisibleFrame,
  type ChatVisibleFrameHost,
} from "./chatVisibleFrame";

const NEAR_BOTTOM_PX = 96;
const NEAR_TOP_PX = 72;

/**
 * Track the visible chat frame (height + visualViewport.offsetTop).
 *
 * Never subtracts keyboard height separately. That avoids double-counting when
 * Capacitor / WKWebView already resized the webview. offsetTop is applied as
 * CSS `top` on mobile conversation frames (same coordinate space as the home
 * compose modal) — not as an extra translateY.
 */
export function useChatVisibleFrameHeight(enabled: boolean): void {
  useEffect(() => {
    if (!enabled) return;
    const host: ChatVisibleFrameHost = {
      get innerHeight() {
        return window.innerHeight;
      },
      get scrollX() {
        return window.scrollX;
      },
      get scrollY() {
        return window.scrollY || document.documentElement.scrollTop || 0;
      },
      scrollTo(x, y) {
        window.scrollTo(x, y);
      },
      get visualViewport() {
        return window.visualViewport;
      },
      document,
      addEventListener(type, listener) {
        window.addEventListener(type, listener);
      },
      removeEventListener(type, listener) {
        window.removeEventListener(type, listener);
      },
    };
    return bindChatVisibleFrame(host, document.documentElement.style);
  }, [enabled]);
}

/** True when the thread scroller is already near the latest messages. */
export function isChatNearBottom(scroller: HTMLElement | null): boolean {
  if (!scroller) return true;
  const gap =
    scroller.scrollHeight - scroller.scrollTop - scroller.clientHeight;
  return gap <= NEAR_BOTTOM_PX;
}

export function isChatNearTop(scroller: HTMLElement | null): boolean {
  if (!scroller) return false;
  return scroller.scrollTop <= NEAR_TOP_PX;
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

/** Keep visual anchor when older messages are prepended above. */
export function preserveScrollAfterPrepend(
  scroller: HTMLElement | null,
  apply: () => void
): void {
  if (!scroller) {
    apply();
    return;
  }
  const prevHeight = scroller.scrollHeight;
  const prevTop = scroller.scrollTop;
  apply();
  requestAnimationFrame(() => {
    const delta = scroller.scrollHeight - prevHeight;
    scroller.scrollTop = prevTop + delta;
  });
}

export function mergeUniqueByIdAsc<T extends { id: number }>(
  existing: T[],
  incoming: T[],
  mode: "append" | "prepend"
): T[] {
  if (!incoming.length) return existing;
  const known = new Set(existing.map((m) => m.id));
  const next = incoming.filter((m) => !known.has(m.id));
  if (!next.length) return existing;
  return mode === "prepend" ? [...next, ...existing] : [...existing, ...next];
}

type HistoryPage<T> = {
  messages: T[];
  has_more?: boolean;
  next_before?: number | null;
};

/**
 * Load older messages when the user scrolls near the top of the thread.
 */
export function useLoadOlderChatMessages<T extends { id: number }>(opts: {
  enabled: boolean;
  scrollerRef: RefObject<HTMLElement | null>;
  messages: T[];
  hasMore: boolean;
  setHasMore: (v: boolean) => void;
  setNextBefore: (v: number | null) => void;
  nextBefore: number | null;
  setMessages: Dispatch<SetStateAction<T[]>>;
  fetchOlder: (beforeId: number) => Promise<HistoryPage<T>>;
}): { loadingOlder: boolean } {
  const {
    enabled,
    scrollerRef,
    messages,
    hasMore,
    setHasMore,
    setNextBefore,
    nextBefore,
    setMessages,
    fetchOlder,
  } = opts;
  const loadingRef = useRef(false);
  const [loadingOlder, setLoadingOlder] = useState(false);
  const fetchOlderRef = useRef(fetchOlder);
  fetchOlderRef.current = fetchOlder;
  const messagesRef = useRef(messages);
  messagesRef.current = messages;
  const nextBeforeRef = useRef(nextBefore);
  nextBeforeRef.current = nextBefore;
  const hasMoreRef = useRef(hasMore);
  hasMoreRef.current = hasMore;

  useEffect(() => {
    if (!enabled) return;
    const scroller = scrollerRef.current;
    if (!scroller) return;

    const onScroll = () => {
      if (!hasMoreRef.current || loadingRef.current) return;
      if (!isChatNearTop(scroller)) return;
      const beforeId =
        nextBeforeRef.current ?? (messagesRef.current[0]?.id ?? null);
      if (!beforeId) return;

      loadingRef.current = true;
      setLoadingOlder(true);
      void fetchOlderRef
        .current(beforeId)
        .then((data) => {
          const incoming = data.messages || [];
          preserveScrollAfterPrepend(scroller, () => {
            setMessages((prev) =>
              mergeUniqueByIdAsc(prev, incoming, "prepend")
            );
          });
          setHasMore(Boolean(data.has_more));
          setNextBefore(
            data.next_before != null ? Number(data.next_before) : null
          );
        })
        .catch(() => {
          /* ignore history load errors */
        })
        .finally(() => {
          loadingRef.current = false;
          setLoadingOlder(false);
        });
    };

    scroller.addEventListener("scroll", onScroll, { passive: true });
    return () => scroller.removeEventListener("scroll", onScroll);
  }, [enabled, scrollerRef, setHasMore, setNextBefore, setMessages]);

  return { loadingOlder };
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
