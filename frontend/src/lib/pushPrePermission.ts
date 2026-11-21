/** Session-only dismiss for the iOS push pre-permission sheet. */
export const PUSH_PREPERM_SESSION_KEY = "wase_push_preperm_later";

/** Opens the iOS Settings page for this app (notification re-enable after deny). */
export const IOS_APP_SETTINGS_URL = "app-settings:";

const AUTH_OR_DIAG_PREFIXES = [
  "/login",
  "/signup",
  "/verify",
  "/onboarding",
  "/password-reset",
  "/internal/push-diag",
];

export type PushPermissionUx = "prompt" | "granted" | "denied" | "unknown";

export type PushPrePermissionInput = {
  pluginAvailable: boolean;
  permission: string;
  dismissedThisSession: boolean;
  authenticated: boolean;
  onboardingRequired: boolean;
  pathname: string;
};

export function isAuthOrDiagRoute(pathname: string): boolean {
  const path = pathname || "/";
  return AUTH_OR_DIAG_PREFIXES.some(
    (prefix) => path === prefix || path.startsWith(`${prefix}/`)
  );
}

/**
 * Show the WaseWase pre-permission sheet only for native plugin + notDetermined.
 * Old binaries without FirebaseMessaging never see this UI.
 */
export function shouldShowPushPrePermission(
  input: PushPrePermissionInput
): boolean {
  if (!input.pluginAvailable) return false;
  if (input.dismissedThisSession) return false;
  if (!input.authenticated) return false;
  if (input.onboardingRequired) return false;
  if (isAuthOrDiagRoute(input.pathname)) return false;
  return input.permission === "prompt";
}

/** Bootstrap must never call requestPermissions. */
export function shouldAutoRequestOnBootstrap(): boolean {
  return false;
}

export function shouldAcquireTokenWithoutPrompt(
  pluginAvailable: boolean,
  permission: string
): boolean {
  return pluginAvailable && permission === "granted";
}

export function shouldRequestPermissionsOnCta(input: {
  pluginAvailable: boolean;
  permission: string;
  userTappedEnable: boolean;
  requestInFlight: boolean;
}): boolean {
  return (
    input.pluginAvailable &&
    input.userTappedEnable &&
    input.permission === "prompt" &&
    !input.requestInFlight
  );
}

export function readPrePermissionDismissed(): boolean {
  try {
    return sessionStorage.getItem(PUSH_PREPERM_SESSION_KEY) === "1";
  } catch {
    return false;
  }
}

export function markPrePermissionDismissed(): void {
  try {
    sessionStorage.setItem(PUSH_PREPERM_SESSION_KEY, "1");
  } catch {
    /* ignore quota / private mode */
  }
}

/** Normalize Capacitor / bridge permission strings for Settings UX. */
export function normalizePushPermissionUx(permission: string): PushPermissionUx {
  const value = (permission || "").trim().toLowerCase();
  if (value === "granted" || value === "authorized") return "granted";
  if (value === "denied" || value === "blocked") return "denied";
  if (
    value === "prompt" ||
    value === "prompt-with-rationale" ||
    value === "notdetermined"
  ) {
    return "prompt";
  }
  return "unknown";
}

/** Settings → 通知 controls only on native binaries that ship FirebaseMessaging. */
export function shouldShowSettingsPushControls(input: {
  isNativeApp: boolean;
  pluginAvailable: boolean;
}): boolean {
  return input.isNativeApp && input.pluginAvailable;
}

/**
 * After OS deny, requestPermissions cannot show the system sheet again.
 * Guide the user to iOS Settings instead.
 */
export function shouldOpenSystemSettingsForPush(permission: string): boolean {
  return normalizePushPermissionUx(permission) === "denied";
}

export function shouldOfferPushEnableCta(permission: string): boolean {
  return normalizePushPermissionUx(permission) === "prompt";
}
