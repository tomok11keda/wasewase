import { useEffect, useId, useState } from "react";
import { createPortal } from "react-dom";
import { SfIcon } from "./SfIcon";
import {
  canUseWebShare,
  copyText,
  shareWithSystemSheet,
  type SharePayload,
} from "../lib/share";

type Props = {
  open: boolean;
  payload: SharePayload;
  onClose: () => void;
};

/**
 * External share sheet (OS share + copy link).
 * Reuses the chat message action-sheet visual pattern.
 */
export function ShareActionSheet({ open, payload, onClose }: Props) {
  const titleId = useId();
  const [toast, setToast] = useState<string | null>(null);
  const webShare = canUseWebShare();

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

  useEffect(() => {
    if (!toast) return;
    const timer = window.setTimeout(() => setToast(null), 1800);
    return () => window.clearTimeout(timer);
  }, [toast]);

  if (!open && !toast) return null;

  const onCopy = async () => {
    const ok = await copyText(payload.url);
    if (ok) {
      setToast("リンクをコピーしました");
      onClose();
      return;
    }
    setToast("コピーできませんでした");
  };

  const onNativeShare = async () => {
    onClose();
    const result = await shareWithSystemSheet(payload);
    if (result === "cancelled") return;
    if (result === "shared") return;
    const ok = await copyText(payload.url);
    setToast(ok ? "リンクをコピーしました" : "シェアできませんでした");
  };

  return createPortal(
    <>
      {open ? (
        <div className="msg-action-sheet share-action-sheet" role="presentation">
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
              シェア
            </h2>
            <ul className="msg-action-sheet__list">
              {webShare ? (
                <li>
                  <button
                    type="button"
                    className="msg-action-sheet__btn share-action-sheet__btn"
                    onClick={() => void onNativeShare()}
                  >
                    <SfIcon name="square_and_arrow_up" />
                    他のアプリでシェア
                  </button>
                </li>
              ) : null}
              <li>
                <button
                  type="button"
                  className="msg-action-sheet__btn share-action-sheet__btn"
                  onClick={() => void onCopy()}
                >
                  <SfIcon name="link" />
                  リンクをコピー
                </button>
              </li>
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
      ) : null}
      {toast ? (
        <div className="share-toast" role="status" aria-live="polite">
          {toast}
        </div>
      ) : null}
    </>,
    document.body
  );
}
