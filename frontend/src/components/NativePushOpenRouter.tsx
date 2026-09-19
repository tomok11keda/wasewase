import { useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { spaHrefTo } from "../lib/spaHref";
import {
  consumePendingPushOpenLink,
  pushLinkToRouterPath,
} from "../lib/nativePush";

/**
 * Navigate only when the user taps a push (wase:push-open / cold-start pending link).
 * Foreground receive (wase:push-received) must not change the current route.
 */
export function NativePushOpenRouter() {
  const navigate = useNavigate();
  const openedRef = useRef<string | null>(null);

  useEffect(() => {
    const go = (raw: string | null | undefined) => {
      const path = pushLinkToRouterPath(raw);
      if (!path) return;
      if (openedRef.current === path) return;
      openedRef.current = path;
      navigate(spaHrefTo(path));
    };

    go(consumePendingPushOpenLink());

    const onOpen = (event: Event) => {
      const detail = (event as CustomEvent<{ link?: string }>).detail;
      const link =
        typeof detail === "string"
          ? detail
          : detail && typeof detail.link === "string"
            ? detail.link
            : "";
      go(link);
    };
    window.addEventListener("wase:push-open", onOpen);
    return () => window.removeEventListener("wase:push-open", onOpen);
  }, [navigate]);

  return null;
}
