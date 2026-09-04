import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type FormEvent,
} from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useSession } from "../lib/session";
import { spaLoginPath } from "../features/auth/api";
import {
  acceptGroupInvitation,
  declineGroupInvitation,
  deleteGroupMessage,
  fetchGroupRoom,
  fetchOlderGroupMessages,
  pollGroupMessages,
  sendGroupMessage,
  type ChatMessage,
  type GroupRoomDetail,
} from "../features/dm/api";
import { DM_POLL_MS, useChatPoll } from "../features/dm/useChatPoll";
import { ChatComposeBar } from "../components/ChatComposeBar";
import {
  ChatReplyPreview,
  type ReplyTarget,
} from "../features/chat/ChatReplyPreview";
import { ChatThreadMessage } from "../features/chat/ChatThreadMessage";
import {
  isChatNearBottom,
  mergeUniqueByIdAsc,
  scrollChatToBottom,
  useChatVisibleFrameHeight,
  useKeepChatPinnedOnCompose,
  useLoadOlderChatMessages,
} from "../features/chat/useChatRoomLayout";
import { analytics } from "../lib/analytics/events";

export function GroupRoomPage() {
  const { roomPk } = useParams();
  const roomId = Number(roomPk);
  const navigate = useNavigate();
  const { me, loading: sessionLoading } = useSession();
  const [room, setRoom] = useState<GroupRoomDetail | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [hasMore, setHasMore] = useState(false);
  const [nextBefore, setNextBefore] = useState<number | null>(null);
  const latestIdRef = useRef(0);
  const [body, setBody] = useState("");
  const [replyingTo, setReplyingTo] = useState<ReplyTarget | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [inviteBusy, setInviteBusy] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [highlightId, setHighlightId] = useState<number | null>(null);
  const bottomRef = useRef<HTMLDivElement | null>(null);
  const threadRef = useRef<HTMLDivElement | null>(null);
  const roomIdRef = useRef(roomId);
  roomIdRef.current = roomId;

  useChatVisibleFrameHeight(true);
  useKeepChatPinnedOnCompose(threadRef, true);

  const showToast = useCallback((text: string) => {
    setToast(text);
    window.setTimeout(() => setToast(null), 1800);
  }, []);

  const appendMessages = useCallback((incoming: ChatMessage[]) => {
    if (!incoming.length) return;
    setMessages((prev) => mergeUniqueByIdAsc(prev, incoming, "append"));
  }, []);

  const upsertMessage = useCallback((message: ChatMessage) => {
    setMessages((prev) => {
      const idx = prev.findIndex((m) => m.id === message.id);
      if (idx < 0) return [...prev, message];
      const copy = [...prev];
      copy[idx] = message;
      return copy;
    });
  }, []);

  useEffect(() => {
    if (sessionLoading) return;
    if (!me?.authenticated) {
      navigate(spaLoginPath(`/app/dm/groups/${roomPk || ""}`), {
        replace: true,
      });
      return;
    }
    if (!Number.isFinite(roomId)) {
      setError("invalid_id");
      setLoading(false);
      return;
    }
    const ac = new AbortController();
    setLoading(true);
    setRoom(null);
    setMessages([]);
    setHasMore(false);
    setNextBefore(null);
    latestIdRef.current = 0;
    void fetchGroupRoom(roomId, ac.signal)
      .then((data) => {
        setRoom(data.room);
        setMessages(data.messages || []);
        setHasMore(Boolean(data.has_more));
        setNextBefore(
          data.next_before != null ? Number(data.next_before) : null
        );
        latestIdRef.current = data.room.latest_id || 0;
        setError(null);
        requestAnimationFrame(() => {
          scrollChatToBottom(threadRef.current, "auto");
        });
      })
      .catch((err) => {
        if (err?.name === "AbortError") return;
        setError(err instanceof Error ? err.message : "load_failed");
      })
      .finally(() => setLoading(false));
    return () => ac.abort();
  }, [me?.authenticated, sessionLoading, roomId, roomPk, navigate]);

  const isPending = room?.membership_status === "pending_invite";
  const canSend = Boolean(room?.can_send && !isPending);

  const fetchOlder = useCallback(
    (beforeId: number) => fetchOlderGroupMessages(roomIdRef.current, beforeId),
    []
  );

  const { loadingOlder } = useLoadOlderChatMessages({
    enabled: Boolean(me?.authenticated && room && !loading && !isPending),
    scrollerRef: threadRef,
    messages,
    hasMore,
    setHasMore,
    setNextBefore,
    nextBefore,
    setMessages,
    fetchOlder,
  });

  useChatPoll(
    Boolean(me?.authenticated && room && !loading),
    DM_POLL_MS,
    async (signal) => {
      const id = roomIdRef.current;
      if (!Number.isFinite(id)) return;
      const data = await pollGroupMessages(id, latestIdRef.current || 0, signal);
      if (signal.aborted) return;
      appendMessages(data.messages || []);
      if (typeof data.latest_id === "number") {
        latestIdRef.current = data.latest_id;
      }
    }
  );

  useEffect(() => {
    if (loadingOlder) return;
    const scroller = threadRef.current;
    if (!isChatNearBottom(scroller)) return;
    scrollChatToBottom(scroller, "smooth");
  }, [messages.length, loadingOlder]);

  const scrollToReply = useCallback(
    (messageId: number) => {
      const el = document.getElementById(`chat-msg-${messageId}`);
      if (!el) {
        showToast("元のメッセージはまだ読み込まれていません");
        return;
      }
      el.scrollIntoView({ behavior: "smooth", block: "center" });
      setHighlightId(messageId);
      window.setTimeout(() => setHighlightId(null), 1200);
    },
    [showToast]
  );

  const onSend = async (e: FormEvent) => {
    e.preventDefault();
    if (!body.trim() || !canSend) return;
    const replyId = replyingTo?.id ?? null;
    setBusy(true);
    try {
      const message = await sendGroupMessage(roomId, body.trim(), replyId);
      upsertMessage(message);
      latestIdRef.current = Math.max(latestIdRef.current, message.id);
      setBody("");
      if (replyId) {
        analytics.chatReplySent({ kind: "group" });
        setReplyingTo(null);
      }
    } catch (err) {
      window.alert(err instanceof Error ? err.message : "送信に失敗しました");
    } finally {
      setBusy(false);
    }
  };

  const onAccept = async () => {
    setInviteBusy(true);
    try {
      const data = await acceptGroupInvitation(roomId);
      setRoom({
        ...data.room,
        membership_status: data.room.membership_status || "member",
        invitation: data.room.invitation || null,
        pending_invites: Array.isArray(data.room.pending_invites)
          ? data.room.pending_invites
          : [],
      });
      setMessages(data.messages || []);
      setHasMore(Boolean(data.has_more));
      setNextBefore(
        data.next_before != null ? Number(data.next_before) : null
      );
      latestIdRef.current = data.room.latest_id || latestIdRef.current;
    } catch (err) {
      window.alert(err instanceof Error ? err.message : "参加に失敗しました");
    } finally {
      setInviteBusy(false);
    }
  };

  const onDecline = async () => {
    if (!window.confirm("このグループへの招待を辞退しますか？")) return;
    setInviteBusy(true);
    try {
      await declineGroupInvitation(roomId);
      navigate("/dm", { replace: true });
    } catch (err) {
      window.alert(err instanceof Error ? err.message : "辞退に失敗しました");
    } finally {
      setInviteBusy(false);
    }
  };

  if (loading || sessionLoading) {
    return (
      <div className="dm-page" data-spa-page="メッセージ">
        <div className="main-inner">
          <p>読み込み中…</p>
        </div>
      </div>
    );
  }

  if (error || !room) {
    return (
      <div className="dm-page" data-spa-page="メッセージ">
        <div className="main-inner">
          <Link className="dm-back-text" to="/dm">
            ← メッセージ一覧
          </Link>
          <p>グループを表示できません（{error || "not_found"}）</p>
        </div>
      </div>
    );
  }

  const inviterName =
    room.invitation?.inviter?.display_name ||
    room.invitation?.inviter?.username ||
    "ユーザー";

  return (
    <div className="dm-page dm-room-page" data-spa-page="メッセージ">
      <main className="main-inner dm-room-main">
        <p className="dm-room-top">
          <Link className="dm-back-text" to="/dm">
            ← メッセージ一覧
          </Link>
        </p>

        <section className="dm-partner-card">
          <h1 className="dm-partner-name">{room.name}</h1>
          <p className="dm-partner-meta">
            メンバー {room.member_count}人
            {room.members.length
              ? ` · ${room.members
                  .slice(0, 5)
                  .map((m) => m.display_name)
                  .join("、")}${room.members.length > 5 ? "…" : ""}`
              : ""}
            {room.pending_invites?.length
              ? ` · 招待中 ${room.pending_invites.length}人`
              : ""}
          </p>
        </section>

        {isPending ? (
          <section className="dm-group-invite-banner" aria-label="グループ招待">
            <p className="dm-group-invite-banner__lead">
              {inviterName}さんから招待されています
            </p>
            <strong className="dm-group-invite-banner__question">
              このグループに参加しますか？
            </strong>
            <p className="dm-group-invite-banner__hint">
              参加するまでメッセージは送信できません。内容は確認できます。
            </p>
            <div className="dm-group-invite-banner__actions">
              <button
                type="button"
                className="dm-btn dm-btn-primary"
                disabled={inviteBusy}
                onClick={() => void onAccept()}
              >
                参加する
              </button>
              <button
                type="button"
                className="dm-btn dm-btn-ghost"
                disabled={inviteBusy}
                onClick={() => void onDecline()}
              >
                辞退する
              </button>
            </div>
          </section>
        ) : null}

        <section className="chat-panel" aria-label="グループチャット">
          <h2>メッセージ</h2>
          <p className="chat-hint">グループのやり取りです（15秒ごとに自動更新）</p>

          <div className="dm-message-area" ref={threadRef}>
            {loadingOlder ? (
              <p className="chat-hint" style={{ textAlign: "center" }}>
                過去のメッセージを読み込み中…
              </p>
            ) : hasMore ? (
              <p className="chat-hint" style={{ textAlign: "center" }}>
                上にスクロールして過去のメッセージを表示
              </p>
            ) : null}
            {messages.length === 0 ? (
              <p className="empty-message">まだメッセージはありません。</p>
            ) : (
              <ul className="message-list">
                {messages.map((m) => (
                  <ChatThreadMessage
                    key={m.id}
                    kind="group"
                    message={m}
                    canAct
                    canReply={canSend}
                    highlightedId={highlightId}
                    onReply={setReplyingTo}
                    onDelete={async (id) => {
                      const updated = await deleteGroupMessage(roomId, id);
                      upsertMessage(updated);
                    }}
                    onScrollToReply={scrollToReply}
                    onToast={showToast}
                  />
                ))}
              </ul>
            )}
            <div ref={bottomRef} />
          </div>

          {canSend ? (
            <>
              {replyingTo ? (
                <ChatReplyPreview
                  reply={replyingTo}
                  onClear={() => setReplyingTo(null)}
                />
              ) : null}
              <ChatComposeBar
                value={body}
                onChange={setBody}
                onSend={onSend}
                busy={busy}
                placeholder={replyingTo ? "返信を入力…" : undefined}
              />
            </>
          ) : isPending ? (
            <p className="dm-group-invite-locked">
              参加するとメッセージを送信できます。
            </p>
          ) : null}
        </section>
      </main>
      {toast ? <div className="chat-toast">{toast}</div> : null}
    </div>
  );
}
