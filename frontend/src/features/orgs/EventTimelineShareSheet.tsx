import { useEffect, useRef } from "react";
import { createPortal } from "react-dom";

type Props = {
  open: boolean;
  body: string;
  submitting: boolean;
  error: string | null;
  onBodyChange: (value: string) => void;
  onClose: () => void;
  onSubmit: () => void;
};

export function EventTimelineShareSheet({
  open,
  body,
  submitting,
  error,
  onBodyChange,
  onClose,
  onSubmit,
}: Props) {
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);

  useEffect(() => {
    if (!open) return;
    const vv = window.visualViewport;
    if (!vv) return;
    const sync = () => {
      document.documentElement.style.setProperty(
        "--compose-vv-offset",
        `${vv.offsetTop}px`
      );
      document.documentElement.style.setProperty(
        "--compose-vv-height",
        `${vv.height}px`
      );
    };
    sync();
    vv.addEventListener("resize", sync);
    vv.addEventListener("scroll", sync);
    return () => {
      vv.removeEventListener("resize", sync);
      vv.removeEventListener("scroll", sync);
      document.documentElement.style.removeProperty("--compose-vv-offset");
      document.documentElement.style.removeProperty("--compose-vv-height");
    };
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const focusTimer = window.setTimeout(() => {
      textareaRef.current?.focus();
    }, 50);
    return () => {
      window.clearTimeout(focusTimer);
      document.body.style.overflow = previous;
    };
  }, [open]);

  if (!open || typeof document === "undefined") return null;

  return createPortal(
    <div
      className="compose-modal spa-compose-modal org-event-share-modal"
      aria-hidden="false"
    >
      <div
        className="compose-modal__backdrop"
        aria-hidden="true"
        onClick={() => {
          if (!submitting) onClose();
        }}
      />
      <div
        className="compose-modal__panel"
        role="dialog"
        aria-modal="true"
        aria-labelledby="org-event-timeline-share-title"
      >
        <header className="compose-modal__header">
          <h2 id="org-event-timeline-share-title">タイムラインにシェア</h2>
          <button
            type="button"
            className="compose-modal__close"
            aria-label="閉じる"
            disabled={submitting}
            onClick={onClose}
          >
            ×
          </button>
        </header>
        {error ? (
          <p className="org-edit-error" role="alert">
            {error}
          </p>
        ) : null}
        <label className="org-event-share-modal__label" htmlFor="event-timeline-body">
          紹介文（任意）
        </label>
        <textarea
          ref={textareaRef}
          id="event-timeline-body"
          className="org-event-share-modal__textarea"
          value={body}
          onChange={(event) => onBodyChange(event.target.value)}
          rows={4}
          maxLength={280}
          placeholder="紹介文がなくてもシェアできます"
          disabled={submitting}
        />
        <div className="org-event-share-modal__actions">
          <button
            type="button"
            className="btn btn-primary"
            data-action="submit-timeline-share"
            disabled={submitting}
            onClick={onSubmit}
          >
            {submitting ? "シェア中…" : "シェアする"}
          </button>
          <button
            type="button"
            className="btn btn-secondary"
            disabled={submitting}
            onClick={onClose}
          >
            キャンセル
          </button>
        </div>
      </div>
    </div>,
    document.body
  );
}
