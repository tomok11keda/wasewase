export const ACCOUNT_MENU_STATE_KEY = "waseAccountMenu";

export function isAccountMenuState(state: unknown): boolean {
  if (!state || typeof state !== "object") return false;
  return Boolean(
    (state as { [ACCOUNT_MENU_STATE_KEY]?: unknown })[ACCOUNT_MENU_STATE_KEY]
  );
}

export function withAccountMenuState(state: unknown): Record<string, unknown> {
  const base =
    state && typeof state === "object"
      ? { ...(state as Record<string, unknown>) }
      : {};
  return { ...base, [ACCOUNT_MENU_STATE_KEY]: true };
}

/** Overlay destinations that should return to the account menu on back. */
export function shouldReplaceAccountMenu(input: {
  overlayNavigation: boolean;
  restoreMenu: boolean;
}): boolean {
  return input.overlayNavigation && !input.restoreMenu;
}
