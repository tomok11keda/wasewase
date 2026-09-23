/** Session-only dismiss for the iOS push pre-permission sheet. */
export const PUSH_PREPERM_SESSION_KEY = "wase_push_preperm_later";

const AUTH_OR_DIAG_PREFIXES = [
  "/login",
  "/signup",
  "/verify",
  "/onboarding",
  "/password-reset",
  "/internal/push-diag",
];

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
