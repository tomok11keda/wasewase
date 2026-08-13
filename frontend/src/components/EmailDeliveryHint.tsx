type EmailDeliveryHintProps = {
  /** Compact line placed near resend controls. */
  compact?: boolean;
  className?: string;
};

/**
 * Visible tip for OTP / verification emails that often land in spam
 * (especially university mailboxes). Presentation only — no auth logic.
 */
export function EmailDeliveryHint({
  compact = false,
  className = "",
}: EmailDeliveryHintProps) {
  if (compact) {
    return (
      <p
        className={`email-delivery-hint email-delivery-hint--compact${className ? ` ${className}` : ""}`}
        role="note"
      >
        ⚠️ 受信トレイに見つからない場合は、迷惑メールフォルダも必ず確認してください。
      </p>
    );
  }

  return (
    <aside
      className={`email-delivery-hint${className ? ` ${className}` : ""}`}
      role="note"
      aria-label="認証メールが届かない場合"
    >
      <p className="email-delivery-hint__title">📩 認証メールが届かない場合</p>
      <p className="email-delivery-hint__body">
        まず「迷惑メール」フォルダを確認してください。
        大学のメールアドレスでは、わせわせからのメールが迷惑メールに振り分けられる場合があります。
      </p>
      <p className="email-delivery-hint__warn">
        ⚠️ 受信トレイに見つからない場合は、迷惑メールフォルダも必ず確認してください。
      </p>
    </aside>
  );
}
