/**
 * Pure helpers for ChatComposeBar send-button gesture handling.
 *
 * On iOS WKWebView, the first tap on Send while the keyboard is open often
 * blurs the input first. That dismisses the keyboard and toggles
 * `.chat-compose-bar:focus-within` padding (safe-area returns), so the button
 * moves and the synthesized click is lost. Preventing the send control's
 * pointerdown default keeps focus on the input through the tap.
 */

export function shouldPreventSendPointerDefault(opts: {
  disabled: boolean;
  busy: boolean;
  pointerType: string;
  button: number;
}): boolean {
  if (opts.disabled || opts.busy) return false;
  if (opts.pointerType === "mouse" && opts.button !== 0) return false;
  return true;
}

/**
 * Re-focus the compose input after a successful send so the keyboard stays
 * open for continuous messaging (chat-app convention).
 */
export function shouldRefocusComposeAfterSend(opts: {
  disabled: boolean;
  stillMounted: boolean;
}): boolean {
  return !opts.disabled && opts.stillMounted;
}
