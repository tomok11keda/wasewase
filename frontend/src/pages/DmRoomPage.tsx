import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type FormEvent,
} from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useSession } from "../lib/session";
import { spaLoginPath } from "../features/auth/api";
import {
  acceptMessageRequest,
  declineMessageRequest,
  fetchDmRoom,
  fetchOlderDmMessages,
  pollDmMessages,
  sendDmMessage,
  type ChatMessage,
  type DmRoomDetail,
} from "../features/dm/api";
import { DM_POLL_MS, useChatPoll } from "../features/dm/useChatPoll";
import { ChatComposeBar } from "../components/ChatComposeBar";
import { ChatDateDivider } from "../features/chat/ChatDateDivider";
import { ChatRoomHeader } from "../features/chat/ChatRoomHeader";
import {
  ChatComposeSkeleton,
  ChatHeaderSkeleton,
  ChatLoadError,
  ChatThreadSkeleton,
} from "../features/chat/ChatRoomSkeleton";
import { readDmHeaderPreview } from "../features/chat/inboxRoomPreview";
import { chatContentPhase, chatRoomMatches } from "../lib/chatContentPhase";
import {
  isLatestRequest,
  isSameUserScope,
  nextRequestId,
} from "../lib/userScopedResult";
import {
  buildChatThread,
  chatTimeLabel,
} from "../features/chat/chatThread";
import { SharedContentCard } from "../features/share/SharedContentCard";
import {
  isChatNearBottom,
  mergeUniqueByIdAsc,
  scrollChatToBottom,
  useChatVisibleFrameHeight,
  useKeepChatPinnedOnCompose,
  useLoadOlderChatMessages,
} from "../features/chat/useChatRoomLayout";
import { AccountDisplayName } from "../components/VerifiedAccountBadge";

export function DmRoomPage() {
  const { roomPk } = useParams();
  const roomId = Number(roomPk);
  const navigate = useNavigate();
  const { me, loading: sessionLoading } = useSession();
  const sessionUserId =
    me?.authenticated && me.user?.id != null ? me.user.id : null;
  const userIdRef = useRef(sessionUserId);
  userIdRef.current = sessionUserId;
  const prevUserIdRef = useRef(sessionUserId);
  const fetchGen = useRef(0);
  const [room, setRoom] = useState<DmRoomDetail | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [hasMore, setHasMore] = useState(false);
  const [nextBefore, setNextBefore] = useState<number | null>(null);
  const latestIdRef = useRef(0);
  const [body, setBody] = useState("");
  const [loading, setLoading] = useState(true);
  const [hydrated, setHydrated] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [requestBusy, setRequestBusy] = useState(false);
  const bottomRef = useRef<HTMLDivElement | null>(null);
  const threadRef = useRef<HTMLDivElement | null>(null);
  const roomIdRef = useRef(roomId);
  roomIdRef.current = roomId;

  useChatVisibleFrameHeight(true);
  useKeepChatPinnedOnCompose(threadRef, true);

  const appendMessages = useCallback((incoming: ChatMessage[]) => {
    if (!incoming.length) return;
    setMessages((prev) => mergeUniqueByIdAsc(prev, incoming, "append"));
  }, []);

  const applyReadIds = useCallback((ids: number[]) => {
    if (!ids.length) return;
    const set = new Set(ids);
    setMessages((prev) =>
      prev.map((m) =>
        m.is_mine && set.has(m.id) ? { ...m, is_read: true } : m
      )
    );
  }, []);

  useLayoutEffect(() => {
    nextRequestId(fetchGen);
    setRoom(null);
    setMessages([]);
    setHasMore(false);
    setNextBefore(null);
    setBody("");
    latestIdRef.current = 0;
    setLoading(true);
    setHydrated(false);
    setError(null);
  }, [roomId]);

  useLayoutEffect(() => {
    if (prevUserIdRef.current === sessionUserId) return;
    prevUserIdRef.current = sessionUserId;
    nextRequestId(fetchGen);
    setRoom(null);
    setMessages([]);
    setHasMore(false);
    setNextBefore(null);
    setBody("");
    latestIdRef.current = 0;
    setLoading(true);
    setHydrated(false);
    setError(null);
  }, [sessionUserId]);

  const load = useCallback(
    async (signal?: AbortSignal) => {
      if (!Number.isFinite(roomId)) {
        setError("invalid_id");
        setLoading(false);
        setHydrated(true);
        return;
      }
      const gen = nextRequestId(fetchGen);
      const startedUserId = userIdRef.current;
      setLoading(true);
      setError(null);
      try {
        const data = await fetchDmRoom(roomId, signal);
        if (signal?.aborted) return;
        if (!isLatestRequest(fetchGen, gen)) return;
        if (!isSameUserScope(startedUserId, userIdRef.current)) return;
        if (roomIdRef.current !== roomId) return;
        setRoom(data.room);
        setMessages(data.messages || []);
        setHasMore(Boolean(data.has_more));
        setNextBefore(
          data.next_before != null ? Number(data.next_before) : null
        );
        latestIdRef.current = data.room.latest_id || 0;
        setError(null);
        setHydrated(true);
        requestAnimationFrame(() => {
          scrollChatToBottom(threadRef.current, "auto");
        });
      } catch (err) {
        if ((err as { name?: string } | null)?.name === "AbortError") return;
        if (!isLatestRequest(fetchGen, gen)) return;
        if (!isSameUserScope(startedUserId, userIdRef.current)) return;
        setRoom(null);
        setMessages([]);
        setError(err instanceof Error ? err.message : "load_failed");
        setHydrated(true);
      } finally {
        if (isLatestRequest(fetchGen, gen)) setLoading(false);
      }
    },
    [roomId]
  );

  useEffect(() => {
    if (sessionLoading) return;
    if (!me?.authenticated) {
      navigate(spaLoginPath(`/app/dm/${roomPk || ""}`), { replace: true });
      return;
    }
    const ac = new AbortController();
    void load(ac.signal);
    return () => ac.abort();
  }, [me?.authenticated, sessionLoading, roomId, roomPk, navigate, load, sessionUserId]);

  const fetchOlder = useCallback(
    (beforeId: number) => fetchOlderDmMessages(roomIdRef.current, beforeId),
    []
  );

  const { loadingOlder } = useLoadOlderChatMessages({
    enabled: Boolean(me?.authenticated && room && !loading),
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
      const data = await pollDmMessages(id, latestIdRef.current || 0, signal);
      if (signal.aborted) return;
      appendMessages(data.messages || []);
      if (typeof data.latest_id === "number") {
        latestIdRef.current = data.latest_id;
      }
      if (Array.isArray(data.read_message_ids)) {
        applyReadIds(data.read_message_ids);
      }
      setRoom((prev) =>
        prev
          ? {
              ...prev,
              can_send: data.can_send,
              is_blocked: data.is_blocked,
            }
          : prev
      );
    }
  );

  useEffect(() => {
    if (loadingOlder) return;
    const scroller = threadRef.current;
    if (!isChatNearBottom(scroller)) return;
    scrollChatToBottom(scroller, "smooth");
  }, [messages.length, loadingOlder]);

  const onSend = async (e: FormEvent) => {
    e.preventDefault();
    if (!hydrated || !body.trim() || !room?.can_send || busy) return;
    setBusy(true);
    try {
      const message = await sendDmMessage(roomId, body.trim());
      appendMessages([message]);
      latestIdRef.current = Math.max(latestIdRef.current, message.id);
      setBody("");
    } catch (err) {
      window.alert(err instanceof Error ? err.message : "送信に失敗しました");
    } finally {
      setBusy(false);
    }
  };

  const isPendingRequest = room?.request_status === "pending_request";

  const onAcceptRequest = async () => {
    setRequestBusy(true);
    try {
      const data = await acceptMessageRequest(roomId);
      setRoom({
        ...data.room,
        request_status: data.room.request_status || "active",
        message_request: data.room.message_request || null,
      });
      setMessages(data.messages || []);
      latestIdRef.current = data.room.latest_id || latestIdRef.current;
    } catch (err) {
      window.alert(err instanceof Error ? err.message : "承認に失敗しました");
    } finally {
      setRequestBusy(false);
    }
  };

  const onDeclineRequest = async () => {
    if (!window.confirm("このメッセージリクエストを拒否しますか？")) return;
    setRequestBusy(true);
    try {
      await declineMessageRequest(roomId);
      navigate("/dm", { replace: true });
    } catch (err) {
      window.alert(err instanceof Error ? err.message : "拒否に失敗しました");
    } finally {
      setRequestBusy(false);
    }
  };

  const roomMatches = chatRoomMatches(room, roomId);
  const liveRoom = roomMatches ? room : null;
  const phase = chatContentPhase({
    loading: sessionLoading || loading,
    error,
    hasRoom: Boolean(liveRoom),
    hydrated: Boolean(liveRoom) && hydrated,
    messageCount: liveRoom ? messages.length : 0,
  });
  const headerPreview = readDmHeaderPreview(sessionUserId, roomId);
  const partnerName = liveRoom
    ? liveRoom.is_blocked
      ? "不明なユーザー"
      : liveRoom.partner?.display_name || "DM"
    : headerPreview?.title || "";
  const partnerInitial = liveRoom
    ? liveRoom.is_blocked
      ? "?"
      : liveRoom.partner?.initial || partnerName.slice(0, 1)
    : headerPreview?.avatarInitial;
  const partnerProfileTo =
    hydrated && liveRoom && !liveRoom.is_blocked && liveRoom.partner?.id
      ? `/users/${liveRoom.partner.id}/posts`
      : undefined;

  return (
    <div className="dm-page dm-room-page" data-spa-page="メッセージ">
      <main className="main-inner dm-room-main">
        {liveRoom ? (
          <ChatRoomHeader
            backTo="/dm"
            backLabel="メッセージ一覧"
            title={partnerName}
            subtitle={
              liveRoom.is_blocked
                ? "ブロック中のためプロフィールは表示できません"
                : undefined
            }
            avatarUrl={
              liveRoom.partner?.avatar_url && !liveRoom.is_blocked
                ? liveRoom.partner.avatar_url
                : undefined
            }
            avatarInitial={partnerInitial}
            detailsTo={partnerProfileTo}
            detailsLabel="プロフィール"
          />
        ) : (
          <ChatHeaderSkeleton
            backTo="/dm"
            backLabel="メッセージ一覧"
            preview={headerPreview}
          />
        )}

        {phase === "error" || (hydrated && !liveRoom) ? (
          <ChatLoadError
            message={`DMを表示できません（${error || "not_found"}）`}
            onRetry={() => void load()}
          />
        ) : phase === "skeleton" || !liveRoom ? (
          <section className="chat-panel" aria-label="ダイレクトメッセージ">
            <ChatThreadSkeleton />
            <ChatComposeSkeleton />
          </section>
        ) : (
          <>
        {isPendingRequest ? (
          <section className="dm-group-invite-banner" aria-label="メッセージリクエスト">
            <p className="dm-group-invite-banner__lead">
              <AccountDisplayName
                name={
                  liveRoom.message_request?.from_user?.display_name ||
                  liveRoom.partner?.display_name ||
                  "ユーザー"
                }
                verified={
                  liveRoom.message_request?.from_user?.is_operator_verified ??
                  liveRoom.partner?.is_operator_verified
                }
              />
              さんからメッセージリクエストが届いています
            </p>
            <strong className="dm-group-invite-banner__question">
              チャットを開始しますか？
            </strong>
            <p className="dm-group-invite-banner__hint">
              開始するまで通常のDM一覧には表示されません。拒否すると一覧から消えます。
            </p>
            <div className="dm-group-invite-banner__actions">
              <button
                type="button"
                className="dm-btn dm-btn-primary"
                disabled={requestBusy}
                onClick={() => void onAcceptRequest()}
              >
                チャットを開始
              </button>
              <button
                type="button"
                className="dm-btn dm-btn-ghost"
                disabled={requestBusy}
                onClick={() => void onDeclineRequest()}
              >
                拒否
              </button>
            </div>
          </section>
        ) : null}

        <section className="chat-panel" aria-label="ダイレクトメッセージ">
          {!liveRoom.can_send || liveRoom.is_blocked ? (
            <p className="block-banner">
              {liveRoom.is_blocked
                ? "このユーザーをブロック中です。メッセージの送信はできません。"
                : "このユーザーとはメッセージの送受信が制限されています。"}
            </p>
          ) : null}

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
              <p className="empty-message">
                まだメッセージはありません。最初の一言を送ってみましょう。
              </p>
            ) : (
              <ul className="message-list">
                {buildChatThread(messages, {
                  showPeerAvatar: false,
                  showPeerName: false,
                }).map((entry) => {
                  if (entry.kind === "day") {
                    return (
                      <ChatDateDivider key={entry.key} label={entry.label} />
                    );
                  }
                  const m = entry.message;
                  return (
                    <li
                      key={m.id}
                      className={`chat-row is-cluster-${entry.layout.cluster}${
                        m.is_mine ? " is-mine" : ""
                      }`}
                      data-message-id={m.id}
                    >
                      <div className="chat-row__main">
                        {m.message_kind === "share" &&
                        m.share &&
                        m.share.type !== "org_event_lottery" ? (
                          <SharedContentCard share={m.share} />
                        ) : (
                          <div className="chat-row__bubble">{m.body}</div>
                        )}
                        <div className="chat-row__meta">
                          {m.is_mine && m.is_read ? (
                            <span className="chat-row__read">既読</span>
                          ) : null}
                          {entry.layout.showTime ? (
                            <time className="chat-row__time">
                              {chatTimeLabel(m.created_at)}
                            </time>
                          ) : null}
                        </div>
                      </div>
                    </li>
                  );
                })}
              </ul>
            )}
            <div ref={bottomRef} />
          </div>

          <ChatComposeBar
            value={body}
            onChange={setBody}
            onSend={onSend}
            busy={busy}
            disabled={!hydrated || !liveRoom.can_send}
            placeholder={
              liveRoom.is_blocked
                ? "このユーザーはブロック中です"
                : liveRoom.can_send
                  ? "メッセージを入力..."
                  : "メッセージを送信できません"
            }
          />
        </section>
          </>
        )}
      </main>
    </div>
  );
}
