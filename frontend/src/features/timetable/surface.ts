/**
 * Own vs other timetable identity. Route params, Profile override, and
 * BottomNav keep-alive must not be mixed.
 */

export function resolveTimetableTargetUserPk(input: {
  overrideUserPk?: number;
  routeUserPk?: string;
  ignoreRouteUserPk?: boolean;
}): string | undefined {
  if (input.overrideUserPk != null && Number.isFinite(input.overrideUserPk)) {
    return String(input.overrideUserPk);
  }
  if (input.ignoreRouteUserPk) return undefined;
  return input.routeUserPk || undefined;
}

/** No target (BottomNav own) or target matches the logged-in user. */
export function isOwnTimetableSurface(input: {
  targetUserPk?: string;
  myUserId?: number | null;
}): boolean {
  if (!input.targetUserPk) return true;
  if (input.myUserId == null) return false;
  return String(input.myUserId) === input.targetUserPk;
}
