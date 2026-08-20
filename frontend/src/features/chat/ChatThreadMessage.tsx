import { useCallback, useRef, useState } from "react";
import { useLongPress } from "./useLongPress";
import { MessageActionSheet } from "./MessageActionSheet";
import { ChatMessageReportSheet } from "./ChatMessageReportSheet";
import type { ReplyTarget } from "./ChatReplyPreview";
import { analytics } from "../../lib/analytics/events";

export type ThreadMessage = {
  id: number;
  sender_name: string;
  sender_initial?: string;
  avatar_url?: string;
  body: string;
  created_at: string;
  is_mine: boolean;
  is_deleted?: boolean;
  reply_to?: {
    id: number;
    sender_name: string;
    text_preview: string;
    is_unavailable?: boolean;
  } | null;
  enrollment_label?: string | null;
  enrollment_role?: string | null;
};

type Props = {
  message: ThreadMessage;
  kind: "group" | "course";
  /** Open long-press / … menu (copy / report / delete). */
  canAct: boolean;
  /** Show Reply in the sheet (requires send permission). */
  canReply?: boolean;
  highlightedId: number | null;
  onReply: (target: ReplyTarget) => void;
  onDelete: (messageId: number) => Promise<void>;
  onScrollToReply: (messageId: number) => void;
  onToast: (text: string) => void;
};

export function ChatThreadMessage({
  message: m,
  kind,
  canAct,
  canReply = true,
  highlightedId,
  onReply,
  onDelete,
  onScrollToReply,
  onToast,
}: Props) {
  const [sheetOpen, setSheetOpen] = useState(false);
  const [reportOpen, setReportOpen] = useState(false);
  const rowRef = useRef<HTMLLIElement | null>(null);

  const openSheet = useCallback(() => {
    if (!canAct || m.is_deleted) return;
    analytics.chatMessageLongPressed({ kind });
    setSheetOpen(true);
  }, [canAct, m.is_deleted, kind]);

  const lp = useLongPress({ onLongPress: openSheet, enabled: canAct && !m.is_deleted });

  const copyBody = async () => {
    const text = m.body || "";
    try {
      await navigator.clipboard.writeText(text);
      analytics.chatMessageCopied({ kind });
      onToast("コピーしました");
    } catch {
      onToast("コピーに失敗しました");
    }
  };

  const startReply = () => {
    if (m.is_deleted || !canReply) return;
    analytics.chatReplyStarted({ kind });
    onReply({
      id: m.id,
      senderName: m.is_mine ? "自分" : m.sender_name,
      preview: (m.body || "").slice(0, 80),
    });
  };

  const confirmDelete = async () => {
    if (!window.confirm("このメッセージを削除しますか？")) return;
    try {
      await onDelete(m.id);
      analytics.chatMessageDeleted({ kind });
      onToast("削除しました");
    } catch (err) {
      window.alert(err instanceof Error ? err.message : "削除に失敗しました");
    }
  };

  return (
    <>
      <li
        ref={rowRef}
        id={`chat-msg-${m.id}`}
        className={`chat-row${m.is_mine ? " is-mine" : ""}${
          highlightedId === m.id ? " is-highlight" : ""
        }${m.is_deleted ? " is-deleted" : ""}`}
        data-message-id={m.id}
        {...lp}
      >
        <div className="chat-row__avatar" aria-hidden="true">
          {m.avatar_url ? (
            <img className="user-avatar--image" src={m.avatar_url} alt="" />
          ) : (
            <span className="user-avatar--initial">
              {m.sender_initial || "?"}
            </span>
          )}
        </div>
        <div className="chat-row__main">
          {!m.is_mine ? (
            <div className="chat-row__sender">
              {m.sender_name}
              {m.enrollment_label ? (
                <span
                  className={`course-talk-badge${
                    m.enrollment_role === "current" ? " is-current" : " is-past"
                  }`}
                >
                  {m.enrollment_label}
                </span>
              ) : null}
            </div>
          ) : null}
          <div className="chat-row__bubble-wrap">
            <div className="chat-row__bubble">
              {m.reply_to ? (
                <button
                  type="button"
                  className={`chat-reply-quote${
                    m.reply_to.is_unavailable ? " is-unavailable" : ""
                  }`}
                  onClick={(e) => {
                    e.stopPropagation();
                    if (!m.reply_to?.is_unavailable) {
                      onScrollToReply(m.reply_to!.id);
                    }
                  }}
                >
                  <span className="chat-reply-quote__name">
                    {m.reply_to.is_unavailable
                      ? ""
                      : m.reply_to.sender_name}
                  </span>
                  <span className="chat-reply-quote__text">
                    {m.reply_to.text_preview}
                  </span>
                </button>
              ) : null}
              {m.is_deleted ? (
                <span className="chat-row__deleted">
                  このメッセージは削除されました
                </span>
              ) : (
                m.body
              )}
            </div>
            <div className="chat-row__meta">
              <time className="chat-row__time">{m.created_at}</time>
              {canAct && !m.is_deleted ? (
                <button
                  type="button"
                  className="chat-row__more"
                  aria-label="メッセージの操作"
                  onClick={(e) => {
                    e.stopPropagation();
                    openSheet();
                  }}
                >
                  …
                </button>
              ) : null}
            </div>
          </div>
        </div>
      </li>

      <MessageActionSheet
        open={sheetOpen}
        isOwn={m.is_mine}
        canReply={canReply && !m.is_deleted}
        canCopy={!m.is_deleted && Boolean(m.body)}
        canDelete={m.is_mine && !m.is_deleted}
        canReport={!m.is_mine && !m.is_deleted}
        onClose={() => setSheetOpen(false)}
        onReply={startReply}
        onCopy={() => void copyBody()}
        onDelete={() => void confirmDelete()}
        onReport={() => setReportOpen(true)}
      />
      <ChatMessageReportSheet
        messageId={m.id}
        open={reportOpen}
        onClose={() => setReportOpen(false)}
        onReported={() => {
          analytics.chatMessageReported({ kind });
          onToast("通報しました");
        }}
      />
    </>
  );
}
