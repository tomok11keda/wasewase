import { useEffect, useRef } from "react";
import { useLocation } from "react-router-dom";
import { useSpaNavDiag } from "../lib/spaNavDiag";
import {
  flashDiagBegin,
  flashDiagEnd,
  flashDiagMark,
  flashDiagSnapshot,
} from "../lib/flashDiag";

type WaseCapacitorBridge = {
  notifySpaNavigation?: (reason?: string) => void;
  trackPageView?: (reason?: string) => Promise<void>;
  handlePageTriggers?: () => void;
  repositionBannerAd?: () => void;
};

/**
 * Fire Capacitor Analytics / AdMob page triggers on React Router navigations.
 * Diag: ?spa_nav_diag=no_bridge|off → このコンポーネントは何もしない。
 * Flash timeline: ?spa_flash_diag=1
 */
export function NativeSpaBridge() {
  const location = useLocation();
  const diag = useSpaNavDiag();
  const prevPathRef = useRef<string | null>(null);

  useEffect(() => {
    const from = prevPathRef.current;
    const to = `${location.pathname}${location.search}`;
    prevPathRef.current = to;

    const traceId = flashDiagBegin({
      kind: "route_change",
      from,
      to,
      pathname: location.pathname,
      search: location.search,
      spaNavDiag: diag.raw || "normal",
    });
    flashDiagMark("route_change_start", {
      from,
      to,
      traceId,
      spaNavDiag: diag.raw || "normal",
    });

    if (diag.disableBridge || diag.disableAll) {
      flashDiagMark("native_spa_bridge_skipped", {
        reason: diag.disableAll ? "diag_off" : "diag_no_bridge",
      });
      flashDiagMark("route_change_end", { bridge: "skipped" });
      window.setTimeout(() => {
        flashDiagEnd({ reason: "bridge_skipped" });
      }, 450);
      return;
    }

    const bridge = (window as Window & { WaseCapacitor?: WaseCapacitorBridge })
      .WaseCapacitor;
    flashDiagMark("native_spa_bridge_run", {
      hasBridge: Boolean(bridge),
      hasNotify: Boolean(bridge?.notifySpaNavigation),
    });

    if (!bridge) {
      flashDiagMark("route_change_end", { bridge: "missing" });
      window.setTimeout(() => flashDiagEnd({ reason: "no_bridge_object" }), 200);
      return;
    }

    if (typeof bridge.notifySpaNavigation === "function") {
      bridge.notifySpaNavigation("spa-route");
    } else {
      if (typeof bridge.trackPageView === "function") {
        void bridge.trackPageView("spa-route");
      }
      if (typeof bridge.handlePageTriggers === "function") {
        try {
          bridge.handlePageTriggers();
        } catch {
          /* ignore */
        }
      }
    }

    flashDiagSnapshot("after_bridge_call");
    flashDiagMark("route_change_end", { bridge: "called" });
    // Allow banner debounce (~100ms) + native sample window to land in same trace
    window.setTimeout(() => {
      flashDiagEnd({ reason: "route_settled" });
    }, 450);
  }, [location.pathname, location.search, diag.disableBridge, diag.disableAll, diag.raw]);

  return null;
}
