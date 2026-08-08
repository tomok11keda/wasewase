/** Capacitor iOS WKWebView 判定（本番モバイル Safari では false） */
export function isNativeCapacitorApp(): boolean {
  try {
    const cap = (
      window as Window & {
        Capacitor?: { isNativePlatform?: () => boolean };
      }
    ).Capacitor;
    if (cap && typeof cap.isNativePlatform === "function" && cap.isNativePlatform()) {
      return true;
    }
  } catch {
    /* ignore */
  }
  try {
    return document.documentElement.classList.contains("is-native-capacitor");
  } catch {
    return false;
  }
}
