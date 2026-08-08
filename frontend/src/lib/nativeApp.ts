/** Capacitor iOS WKWebView 判定（本番モバイル Safari では false） */
export function isNativeCapacitorApp(): boolean {
  try {
    const cap = (
      window as Window & {
        Capacitor?: {
          isNativePlatform?: () => boolean;
          getPlatform?: () => string;
        };
      }
    ).Capacitor;
    if (cap) {
      if (
        typeof cap.isNativePlatform === "function" &&
        cap.isNativePlatform()
      ) {
        return true;
      }
      if (typeof cap.getPlatform === "function") {
        const platform = cap.getPlatform();
        if (platform === "ios" || platform === "android") {
          return true;
        }
      }
    }
  } catch {
    /* ignore */
  }

  try {
    if (document.documentElement.classList.contains("is-native-capacitor")) {
      return true;
    }
  } catch {
    /* ignore */
  }

  try {
    const cfg = (
      window as Window & { WASE_ADMOB_CONFIG?: { IS_APP?: boolean } }
    ).WASE_ADMOB_CONFIG;
    if (cfg && cfg.IS_APP === true) {
      return true;
    }
  } catch {
    /* ignore */
  }

  try {
    if (/(?:^|;\s*)wase_is_app=1(?:;|$)/.test(document.cookie || "")) {
      return true;
    }
  } catch {
    /* ignore */
  }

  return false;
}
