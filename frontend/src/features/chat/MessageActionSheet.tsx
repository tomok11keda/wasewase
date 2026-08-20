import { useEffect, useId, useRef } from "react";

export type MessageActionKey = "reply" | "copy" | "delete" | "report";

type Props = {
  open: boolean;
  isOwn: boolean;
  canReply?: boolean;
  canCopy?: boolean;
  canDelete?: boolean;
  canReport?: boolean;
  onClose: () => void;
  onReply: () => void;
  onCopy: () => void;
  onDelete: () => void;
  onReport: () => void;
};

/**
 * Bottom action sheet for chat message long-press.
 * Own: reply / copy / delete. Other: reply / copy / report.
 */
export function MessageActionSheet({
  open,
  isOwn,
  canReply = true,
  canCopy = true,
  canDelete = true,
  canReport = true,
  onClose,
  onReply,
  onCopy,
  onDelete,
  onReport,
}: Props) {
  const titleId = useId();
  const sheetRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
    };
  }, [open, onClose]);

  if (!open) return null;

  const actions: Array<{
    key: MessageActionKey;
    label: string;
    danger?: boolean;
    onClick: () => void;
    show: boolean;
  }> = [
    {
      key: "reply",
      label: "↩ 返信",
      onClick: onReply,
      show: canReply,
    },
    {
      key: "copy",
      label: "📋 コピー",
      onClick: onCopy,
      show: canCopy,
    },
    {
      key: "delete",
      label: "🗑 削除",
      danger: true,
      onClick: onDelete,
      show: isOwn && canDelete,
    },
    {
      key: "report",
      label: "⚑ 通報",
      danger: true,
      onClick: onReport,
      show: !isOwn && canReport,
    },
  ];

  return (
    <div className="msg-action-sheet" role="presentation">
      <button
        type="button"
        className="msg-action-sheet__backdrop"
        aria-label="閉じる"
        onClick={onClose}
      />
      <div
        ref={sheetRef}
        className="msg-action-sheet__panel"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
      >
        <h2 id={titleId} className="msg-action-sheet__title">
          メッセージ
        </h2>
        <ul className="msg-action-sheet__list">
          {actions
            .filter((a) => a.show)
            .map((a) => (
              <li key={a.key}>
                <button
                  type="button"
                  className={`msg-action-sheet__btn${
                    a.danger ? " is-danger" : ""
                  }`}
                  onClick={() => {
                    onClose();
                    a.onClick();
                  }}
                >
                  {a.label}
                </button>
              </li>
            ))}
        </ul>
        <button
          type="button"
          className="msg-action-sheet__cancel"
          onClick={onClose}
        >
          キャンセル
        </button>
      </div>
    </div>
  );
}
