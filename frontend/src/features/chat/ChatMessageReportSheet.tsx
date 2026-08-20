import { useState } from "react";
import {
  REPORT_REASONS,
  submitContentReport,
  type ReportReason,
} from "../timeline/api";

type Props = {
  messageId: number;
  open: boolean;
  onClose: () => void;
  onReported: () => void;
};

export function ChatMessageReportSheet({
  messageId,
  open,
  onClose,
  onReported,
}: Props) {
  const [busy, setBusy] = useState(false);

  if (!open) return null;

  const submit = async (reason: ReportReason) => {
    setBusy(true);
    try {
      await submitContentReport("chat_message", messageId, reason);
      onReported();
      onClose();
    } catch (err) {
      window.alert(err instanceof Error ? err.message : "通報に失敗しました");
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
        aria-label="通報理由"
      >
        <h2 className="msg-action-sheet__title">通報理由</h2>
        <ul className="msg-action-sheet__list">
          {REPORT_REASONS.map((r) => (
            <li key={r.value}>
              <button
                type="button"
                className="msg-action-sheet__btn"
                disabled={busy}
                onClick={() => void submit(r.value)}
              >
                {r.label}
              </button>
            </li>
          ))}
        </ul>
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
