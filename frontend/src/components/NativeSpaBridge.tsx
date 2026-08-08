import { useEffect } from "react";
import { useLocation } from "react-router-dom";

type WaseCapacitorBridge = {
  notifySpaNavigation?: (reason?: string) => void;
  trackPageView?: (reason?: string) => Promise<void>;
  handlePageTriggers?: () => void;
  repositionBannerAd?: () => void;
};

/**
 * Fire Capacitor Analytics / AdMob page triggers on React Router navigations.
 */
export function NativeSpaBridge() {
  const location = useLocation();

  useEffect(() => {
    const bridge = (window as Window & { WaseCapacitor?: WaseCapacitorBridge })
      .WaseCapacitor;
    if (!bridge) return;
    if (typeof bridge.notifySpaNavigation === "function") {
      bridge.notifySpaNavigation("spa-route");
      return;
    }
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
  }, [location.pathname, location.search]);

  return null;
}
