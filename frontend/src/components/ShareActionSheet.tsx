import { useEffect, useId, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { SfIcon } from "./SfIcon";
import {
  canUseWebShare,
  copyText,
  shareWithSystemSheet,
  type SharePayload,
} from "../lib/share";
import {
  fetchShareRecipients,
  sendShareToRecipient,
  type ShareRecipient,
  type ShareTarget,
} from "../features/share/api";

type RecipientStatus = "idle" | "sending" | "sent" | "error";

type Props = {
  open: boolean;
  payload: SharePayload;
  shareTarget?: ShareTarget;
  onClose: () => void;
};

/**
 * Share sheet: internal DM recipients above OS share + copy link.
 * Reuses the chat message action-sheet visual pattern.
 */
export function ShareActionSheet({
  open,
  payload,
  shareTarget,
  onClose,
}: Props) {
  const titleId = useId();
  const [toast, setToast] = useState<string | null>(null);
  const [recipients, setRecipients] = useState<ShareRecipient[]>([]);
  const [allRecipients, setAllRecipients] = useState<ShareRecipient[]>([]);
  const [hasMore, setHasMore] = useState(false);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [statusByUser, setStatusByUser] = useState<
    Record<number, RecipientStatus>
  >({});
  const inFlight = useRef<Set<number>>(new Set());
  const webShare = canUseWebShare();

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        if (pickerOpen) {
          setPickerOpen(false);
          return;
        }
        onClose();
      }
    };
    window.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
    };
  }, [open, onClose, pickerOpen]);

  useEffect(() => {
    if (!toast) return;
    const timer = window.setTimeout(() => setToast(null), 1800);
    return () => window.clearTimeout(timer);
  }, [toast]);

  useEffect(() => {
    if (!open) {
      setPickerOpen(false);
      setStatusByUser({});
      inFlight.current.clear();
      return;
    }
    if (!shareTarget) {
      setRecipients([]);
      setAllRecipients([]);
      setHasMore(false);
      return;
    }
    const ac = new AbortController();
    void fetchShareRecipients(ac.signal)
      .then((data) => {
        setRecipients(data.recipients);
        setAllRecipients(data.all_recipients);
        setHasMore(data.has_more);
      })
      .catch(() => {
        setRecipients([]);
        setAllRecipients([]);
        setHasMore(false);
      });
    return () => ac.abort();
  }, [open, shareTarget]);

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

  const onSendTo = async (recipient: ShareRecipient) => {
    if (!shareTarget) return;
    if (inFlight.current.has(recipient.user_id)) return;
    inFlight.current.add(recipient.user_id);
    setStatusByUser((prev) => ({ ...prev, [recipient.user_id]: "sending" }));
    try {
      await sendShareToRecipient(recipient.user_id, shareTarget);
      setStatusByUser((prev) => ({ ...prev, [recipient.user_id]: "sent" }));
    } catch {
      setStatusByUser((prev) => ({ ...prev, [recipient.user_id]: "error" }));
      setToast("送信できませんでした");
    } finally {
      inFlight.current.delete(recipient.user_id);
    }
  };

  const renderRecipient = (recipient: ShareRecipient) => {
    const status = statusByUser[recipient.user_id] || "idle";
    const label =
      status === "sending"
        ? "送信中"
        : status === "sent"
          ? "送信しました"
          : status === "error"
            ? "送信できませんでした"
            : `${recipient.display_name}に送る`;
    return (
      <button
        key={recipient.user_id}
        type="button"
        className={`share-recipient${
          status === "sent" ? " is-sent" : ""
        }${status === "sending" ? " is-sending" : ""}`}
        onClick={() => void onSendTo(recipient)}
        disabled={status === "sending"}
        aria-label={label}
      >
        <span className="share-recipient__avatar" aria-hidden="true">
          {recipient.avatar_url ? (
            <img src={recipient.avatar_url} alt="" />
          ) : (
            <span>{recipient.initial || recipient.display_name.slice(0, 1)}</span>
          )}
          {status === "sent" ? (
            <span className="share-recipient__check" aria-hidden="true">
              ✓
            </span>
          ) : null}
        </span>
        <span className="share-recipient__name">{recipient.display_name}</span>
      </button>
    );
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

            <section
              className="share-action-sheet__section"
              aria-labelledby={`${titleId}-internal`}
            >
              <h3
                id={`${titleId}-internal`}
                className="share-action-sheet__heading"
              >
                わせわせで送る
              </h3>
              {recipients.length === 0 ? (
                <p className="share-action-sheet__empty">
                  まだメッセージできる相手がいません
                </p>
              ) : (
                <>
                  <div className="share-recipient-row">{recipients.map(renderRecipient)}</div>
                  {hasMore ? (
                    <button
                      type="button"
                      className="share-recipient-more"
                      onClick={() => setPickerOpen(true)}
                    >
                      もっと見る
                    </button>
                  ) : null}
                </>
              )}
            </section>

            <section
              className="share-action-sheet__section"
              aria-labelledby={`${titleId}-external`}
            >
              <h3
                id={`${titleId}-external`}
                className="share-action-sheet__heading"
              >
                その他の方法でシェア
              </h3>
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
            </section>

            <button
              type="button"
              className="msg-action-sheet__cancel"
              onClick={onClose}
            >
              キャンセル
            </button>
          </div>

          {pickerOpen ? (
            <div className="share-picker" role="dialog" aria-label="メッセージできる相手">
              <button
                type="button"
                className="share-picker__backdrop"
                aria-label="閉じる"
                onClick={() => setPickerOpen(false)}
              />
              <div className="share-picker__panel">
                <div className="share-picker__head">
                  <h3>わせわせで送る</h3>
                  <button
                    type="button"
                    className="share-picker__close"
                    onClick={() => setPickerOpen(false)}
                  >
                    閉じる
                  </button>
                </div>
                <ul className="share-picker__list">
                  {allRecipients.map((recipient) => (
                    <li key={recipient.user_id}>{renderRecipient(recipient)}</li>
                  ))}
                </ul>
              </div>
            </div>
          ) : null}
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
