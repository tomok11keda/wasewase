import { useEffect, useId, useRef, useState } from "react";
import { submitChatModerationAppeal } from "../dm/api";

type Props = {
  messageId: number;
  open: boolean;
  onClose: () => void;
  onSubmitted: () => void;
};

export function ChatModerationAppealSheet({
  messageId,
  open,
  onClose,
  onSubmitted,
}: Props) {
  const titleId = useId();
  const [explanation, setExplanation] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);

  useEffect(() => {
    if (!open) return;
    setExplanation("");
    setError("");
    setBusy(false);
    const t = window.setTimeout(() => textareaRef.current?.focus(), 0);
    return () => window.clearTimeout(t);
  }, [open, messageId]);

  if (!open) return null;

  const submit = async () => {
    const text = explanation.trim();
    if (!text) {
      setError("理由を入力してください。");
      return;
    }
    setBusy(true);
    setError("");
    try {
      await submitChatModerationAppeal(messageId, text);
      onSubmitted();
      onClose();
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "送信に失敗しました。時間をおいてもう一度お試しください。"
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="msg-action-sheet" role="presentation">
      <button
        type="button"
        className="msg-action-sheet__backdrop"
        aria-label="閉じる"
        onClick={onClose}
      />
      <div
        className="msg-action-sheet__panel"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
      >
        <h2 id={titleId} className="msg-action-sheet__title">
          異議申し立て
        </h2>
        <p className="msg-action-sheet__lead">
          この措置に異議がある場合は、その理由を入力してください。運営が内容を確認します。
        </p>
        <textarea
          ref={textareaRef}
          className="msg-action-sheet__textarea"
          value={explanation}
          onChange={(e) => setExplanation(e.target.value)}
          maxLength={1000}
          rows={5}
          disabled={busy}
          placeholder="理由を入力"
        />
        {error ? <p className="msg-action-sheet__error">{error}</p> : null}
        <button
          type="button"
          className="msg-action-sheet__btn"
          disabled={busy}
          onClick={() => void submit()}
        >
          送信する
        </button>
        <button
          type="button"
          className="msg-action-sheet__cancel"
          disabled={busy}
          onClick={onClose}
        >
          キャンセル
        </button>
      </div>
    </div>
  );
}
