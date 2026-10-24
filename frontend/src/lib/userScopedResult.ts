export function nextRequestId(ref: { current: number }): number {
  ref.current += 1;
  return ref.current;
}

export function isLatestRequest(
  ref: { current: number },
  requestId: number
): boolean {
  return ref.current === requestId;
}

/** True only when the user who started a request is still the current viewer. */
export function isSameUserScope(
  startedUserId: number | null | undefined,
  currentUserId: number | null | undefined
): boolean {
  const started = toUserId(startedUserId);
  const current = toUserId(currentUserId);
  if (started == null && current == null) return true;
  if (started == null || current == null) return false;
  return started === current;
}

function toUserId(value: number | null | undefined): number | null {
  if (value == null) return null;
  if (!Number.isFinite(value) || value <= 0) return null;
  return value;
}
