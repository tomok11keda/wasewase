/** Shared mapping for write-path rate limit errors. */

export const RATE_LIMITED_MESSAGE =
  "短時間に操作が集中しています。少し待ってからもう一度お試しください。";

export function isRateLimitedError(
  codeOrMessage: string | undefined | null
): boolean {
  if (!codeOrMessage) return false;
  return (
    codeOrMessage === "rate_limited" ||
    codeOrMessage.includes("rate_limited")
  );
}

/** Map API error codes to a user-facing Japanese string. */
export function userFacingMutationError(
  codeOrMessage: string | undefined | null,
  fallback: string
): string {
  if (isRateLimitedError(codeOrMessage)) {
    return RATE_LIMITED_MESSAGE;
  }
  if (codeOrMessage && /[ぁ-んァ-ン一-龥]/.test(codeOrMessage)) {
    return codeOrMessage;
  }
  return fallback;
}
