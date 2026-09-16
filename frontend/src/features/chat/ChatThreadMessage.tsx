import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useLongPress } from "./useLongPress";
import { MessageActionSheet } from "./MessageActionSheet";
import { ChatMessageReportSheet } from "./ChatMessageReportSheet";
import { ChatModerationAppealSheet } from "./ChatModerationAppealSheet";
import type { ReplyTarget } from "./ChatReplyPreview";
import { analytics } from "../../lib/analytics/events";

export type ThreadMessage = {
  id: number;
  sender_id?: number | null;
  sender_name: string;
  sender_username?: string;
  sender_initial?: string;
  avatar_url?: string;
  body: string;
  created_at: string;
  is_mine: boolean;
  is_deleted?: boolean;
  is_removed?: boolean;
  can_appeal?: boolean;
  appeal_status?: "pending" | "accepted" | "rejected" | null;
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
  const [appealOpen, setAppealOpen] = useState(false);
  const [appealStatus, setAppealStatus] = useState(m.appeal_status ?? null);
  const rowRef = useRef<HTMLLIElement | null>(null);
  const isRemoved = Boolean(m.is_removed);
  const isTombstone = isRemoved || Boolean(m.is_deleted);
  const showAppeal = isRemoved && m.is_mine && Boolean(m.can_appeal) && appealStatus !== "pending";
  const showAppealPending = isRemoved && m.is_mine && appealStatus === "pending";

  useEffect(() => {
    setAppealStatus(m.appeal_status ?? null);
  }, [m.appeal_status]);

  const openSheet = useCallback(() => {
    if (!canAct || isTombstone) return;
    analytics.chatMessageLongPressed({ kind });
    setSheetOpen(true);
  }, [canAct, isTombstone, kind]);

  const lp = useLongPress({ onLongPress: openSheet, enabled: canAct && !isTombstone });
  const profilePath =
    kind === "course" && m.sender_id
      ? `/users/${m.sender_id}/posts`
      : null;
  const avatar = m.avatar_url ? (
    <img className="user-avatar--image" src={m.avatar_url} alt="" />
  ) : (
    <span className="user-avatar--initial">{m.sender_initial || "?"}</span>
  );

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
    if (isTombstone || !canReply) return;
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
        }${m.is_deleted ? " is-deleted" : ""}${isRemoved ? " is-removed" : ""}`}
        data-message-id={m.id}
        {...lp}
      >
        {profilePath ? (
          <Link
            className="chat-row__avatar"
            to={profilePath}
            aria-label={`${m.sender_name}のプロフィール`}
          >
            {avatar}
          </Link>
        ) : (
          <div className="chat-row__avatar" aria-hidden="true">
            {avatar}
          </div>
        )}
        <div className="chat-row__main">
          {!m.is_mine ? (
            <div className="chat-row__sender">
              {profilePath ? (
                <Link className="chat-row__sender-link" to={profilePath}>
                  {m.sender_name}
                  {m.sender_username ? (
                    <span className="chat-row__handle">@{m.sender_username}</span>
                  ) : null}
                </Link>
              ) : (
                m.sender_name
              )}
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
              {isRemoved ? (
                <span className="chat-row__deleted">
                  このメッセージは運営により削除されました。
                </span>
              ) : m.is_deleted ? (
                <span className="chat-row__deleted">
                  このメッセージは削除されました
                </span>
              ) : (
                m.body
              )}
            </div>
            {showAppealPending ? (
              <p className="chat-row__appeal-status">異議申し立てを確認中です</p>
            ) : null}
            {showAppeal ? (
              <button
                type="button"
                className="chat-row__appeal"
                onClick={(e) => {
                  e.stopPropagation();
                  setAppealOpen(true);
                }}
              >
                異議申し立て
              </button>
            ) : null}
            <div className="chat-row__meta">
              <time className="chat-row__time">{m.created_at}</time>
              {canAct && !isTombstone ? (
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
        canReply={canReply && !isTombstone}
        canCopy={!isTombstone && Boolean(m.body)}
        canDelete={m.is_mine && !isTombstone}
        canReport={!m.is_mine && !isTombstone}
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
      <ChatModerationAppealSheet
        messageId={m.id}
        open={appealOpen}
        onClose={() => setAppealOpen(false)}
        onSubmitted={() => {
          setAppealStatus("pending");
          onToast("異議申し立てを受け付けました。運営が内容を確認します。");
        }}
      />
    </>
  );
}
