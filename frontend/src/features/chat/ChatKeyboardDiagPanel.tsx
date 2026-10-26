import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useLocation } from "react-router-dom";
import { matchChromeMode } from "../../lib/chrome";
import { useSession } from "../../lib/session";
import {
  bindChatKeyboardDiagListeners,
  captureChatKeyboardDiagSnapshot,
  chatKeyboardDiagOverlayPins,
  formatChatKeyboardDiagLines,
  shouldShowChatKeyboardDiag,
  syncChatKeyboardDiagRequest,
  type ChatKeyboardDiagSnapshot,
} from "./chatKeyboardDiag";
import "./chatKeyboardDiag.css";

function readSai(el: HTMLElement | null): { top: number; bottom: number } | null {
  if (!el) return null;
  const style = getComputedStyle(el);
  return {
    top: Number.parseFloat(style.paddingTop) || 0,
    bottom: Number.parseFloat(style.paddingBottom) || 0,
  };
}

function captureNow(
  lastEvent: string,
  saiEl: HTMLElement | null
): ChatKeyboardDiagSnapshot {
  return captureChatKeyboardDiagSnapshot(
    {
      innerHeight: window.innerHeight,
      outerHeight: window.outerHeight,
      scrollY: window.scrollY || document.documentElement.scrollTop || 0,
      visualViewport: window.visualViewport,
      root: document,
      css: getComputedStyle(document.documentElement),
      sai: readSai(saiEl),
    },
    lastEvent
  );
}

export function ChatKeyboardDiagPanel() {
  const location = useLocation();
  const { me } = useSession();
  const saiRef = useRef<HTMLSpanElement | null>(null);
  const [snap, setSnap] = useState<ChatKeyboardDiagSnapshot | null>(null);

  const requested = syncChatKeyboardDiagRequest({
    search: location.search,
    storage: typeof sessionStorage !== "undefined" ? sessionStorage : null,
  });
  const show = shouldShowChatKeyboardDiag({
    requested,
    isConversation: matchChromeMode(location.pathname) === "conversation",
    isDev: Boolean(import.meta.env.DEV),
    isStaff: Boolean(me?.is_staff),
    isSuperuser: Boolean(me?.is_superuser),
  });

  useEffect(() => {
    if (!show) {
      setSnap(null);
      return;
    }
    let raf = 0;
    const unbind = bindChatKeyboardDiagListeners(window, (name) => {
      if (raf) cancelAnimationFrame(raf);
      raf = requestAnimationFrame(() => {
        raf = 0;
        setSnap(captureNow(name, saiRef.current));
      });
    });
    return () => {
      unbind();
      if (raf) cancelAnimationFrame(raf);
    };
  }, [show]);

  if (!show || !snap) return null;

  const lines = formatChatKeyboardDiagLines(snap);
  const pins = chatKeyboardDiagOverlayPins(snap.vvOffsetTop);

  return createPortal(
    <>
      {pins.map((pin) => (
        <div
          key={pin.id}
          className="chat-kb-diag"
          data-testid={pin.id === "A" ? "chat-kb-diag" : `chat-kb-diag-${pin.id}`}
          data-pin={pin.id}
          aria-hidden="true"
          style={{ top: pin.top }}
        >
          <pre className="chat-kb-diag__card">{`${pin.id}\n${lines.join("\n")}`}</pre>
          {pin.id === "A" ? (
            <span className="chat-kb-diag__sai" ref={saiRef} />
          ) : null}
        </div>
      ))}
    </>,
    document.body
  );
}
