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
  completeHandover,
  confirmTrade,
  fetchChatMessages,
  fetchChatRoom,
  fetchOlderChatMessages,
  handoverErrorMessage,
  sendChatMessage,
  type ChatMessage,
  type ChatRoomDetail,
} from "../features/flea/api";
import { TRADE_POLL_MS, useChatPoll } from "../features/dm/useChatPoll";
import { ChatComposeBar } from "../components/ChatComposeBar";
import {
  isChatNearBottom,
  mergeUniqueByIdAsc,
  scrollChatToBottom,
  useChatVisibleFrameHeight,
  useKeepChatPinnedOnCompose,
  useLoadOlderChatMessages,
} from "../features/chat/useChatRoomLayout";
import { analytics } from "../lib/analytics/events";

export function TradeChatPage() {
  const { roomPk } = useParams();
  const roomId = Number(roomPk);
  const navigate = useNavigate();
  const { me } = useSession();
  const [room, setRoom] = useState<ChatRoomDetail | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [hasMore, setHasMore] = useState(false);
  const [nextBefore, setNextBefore] = useState<number | null>(null);
  const latestIdRef = useRef(0);
  const [body, setBody] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [handoverDone, setHandoverDone] = useState(false);
  const bottomRef = useRef<HTMLDivElement | null>(null);
  const threadRef = useRef<HTMLDivElement | null>(null);
  const roomIdRef = useRef(roomId);
  const handoverStartedRef = useRef(false);
  roomIdRef.current = roomId;

  useChatVisibleFrameHeight(true);
  useKeepChatPinnedOnCompose(threadRef, true);

  const appendMessages = useCallback((incoming: ChatMessage[]) => {
    if (!incoming.length) return;
    setMessages((prev) => mergeUniqueByIdAsc(prev, incoming, "append"));
  }, []);

  useEffect(() => {
    if (!me?.authenticated) {
      navigate(spaLoginPath(`/app/flea/chats/${roomPk || ""}`), {
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
    setHandoverDone(false);
    setActionError(null);
    handoverStartedRef.current = false;
    latestIdRef.current = 0;
    void (async () => {
      try {
        const detail = await fetchChatRoom(roomId);
        if (ac.signal.aborted) return;
        setRoom(detail);
        const initial = await fetchChatMessages(roomId, undefined, ac.signal);
        if (ac.signal.aborted) return;
        setMessages(initial.messages);
        setHasMore(Boolean(initial.has_more));
        setNextBefore(
          initial.next_before != null ? Number(initial.next_before) : null
        );
        latestIdRef.current = initial.latest_id;
        setError(null);
        requestAnimationFrame(() => {
          scrollChatToBottom(threadRef.current, "auto");
        });
      } catch (err) {
        if ((err as Error)?.name === "AbortError") return;
        setError(err instanceof Error ? err.message : "load_failed");
      } finally {
        if (!ac.signal.aborted) setLoading(false);
      }
    })();
    return () => ac.abort();
  }, [me?.authenticated, roomId, roomPk, navigate]);

  const fetchOlder = useCallback(
    (beforeId: number) => fetchOlderChatMessages(roomIdRef.current, beforeId),
    []
  );

  const { loadingOlder } = useLoadOlderChatMessages({
    enabled: Boolean(me?.authenticated && room && !loading && !handoverDone),
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
    Boolean(me?.authenticated && room && !loading && !handoverDone),
    TRADE_POLL_MS,
    async (signal) => {
      const id = roomIdRef.current;
      if (!Number.isFinite(id)) return;
      const data = await fetchChatMessages(
        id,
        latestIdRef.current || undefined,
        signal
      );
      if (signal.aborted) return;
      appendMessages(data.messages);
      latestIdRef.current = data.latest_id;
    }
  );

  useEffect(() => {
    if (loadingOlder) return;
    const scroller = threadRef.current;
    if (!isChatNearBottom(scroller)) return;
    scrollChatToBottom(scroller, "smooth");
  }, [messages.length, loadingOlder]);

  useEffect(() => {
    if (!handoverDone) return;
    const timer = window.setTimeout(() => {
      navigate("/flea", { replace: true });
    }, 1800);
    return () => window.clearTimeout(timer);
  }, [handoverDone, navigate]);

  const onSend = async (e: FormEvent) => {
    e.preventDefault();
    if (!body.trim() || !room?.can_send_message || busy) return;
    setBusy(true);
    setActionError(null);
    try {
      const message = await sendChatMessage(roomId, body.trim());
      appendMessages([message]);
      latestIdRef.current = Math.max(latestIdRef.current, message.id);
      setBody("");
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "送信に失敗しました");
    } finally {
      setBusy(false);
    }
  };

  const onConfirm = async () => {
    if (busy) return;
    if (!window.confirm("この交渉を取引開始（pending）にしますか？")) return;
    setBusy(true);
    setActionError(null);
    try {
      const updated = await confirmTrade(roomId);
      analytics.tradeStarted({ method: "confirm_negotiation" });
      setRoom(updated);
      const data = await fetchChatMessages(roomId);
      setMessages(data.messages);
      setHasMore(Boolean(data.has_more));
      setNextBefore(
        data.next_before != null ? Number(data.next_before) : null
      );
      latestIdRef.current = data.latest_id;
      requestAnimationFrame(() => {
        scrollChatToBottom(threadRef.current, "auto");
      });
    } catch (err) {
      setActionError(
        err instanceof Error ? err.message : "取引開始に失敗しました"
      );
    } finally {
      setBusy(false);
    }
  };

  const onHandover = async () => {
    if (busy || handoverStartedRef.current || handoverDone) return;
    if (!window.confirm("受け渡し完了として売り切れにしますか？")) return;
    handoverStartedRef.current = true;
    setBusy(true);
    setActionError(null);
    try {
      const { room: updated, product_status } = await completeHandover(roomId);
      const status = product_status || updated.product.status;
      const soldOk =
        updated.product.is_sold ||
        status === "sold" ||
        status === "sold_out";
      if (!soldOk) {
        throw new Error("save_failed");
      }
      setRoom(updated);
      analytics.tradeCompleted();
      setHandoverDone(true);
    } catch (err) {
      handoverStartedRef.current = false;
      const code = err instanceof Error ? err.message : "handover_failed";
      setActionError(handoverErrorMessage(code));
    } finally {
      setBusy(false);
    }
  };

  if (loading) {
    return (
      <div className="trade-chat-page" data-spa-page="フリマ">
        <div className="main-inner">
          <p>読み込み中…</p>
        </div>
      </div>
    );
  }

  if (error || !room) {
    return (
      <div className="trade-chat-page" data-spa-page="フリマ">
        <div className="main-inner">
          <Link className="back-link" to="/flea">
            ← フリマへ戻る
          </Link>
          <p>チャットを表示できません（{error || "not_found"}）</p>
        </div>
      </div>
    );
  }

  if (handoverDone) {
    return (
      <div className="trade-chat-page" data-spa-page="フリマ">
        <div className="main-inner">
          <div className="trade-complete-card" role="status" aria-live="polite">
            <p className="trade-complete-title">取引完了！</p>
            <p className="trade-complete-thanks">(人''▽｀)ありがとう♪</p>
            <p className="trade-complete-hint">フリマへ戻ります…</p>
            <button
              type="button"
              className="trade-complete-btn"
              onClick={() => navigate("/flea", { replace: true })}
            >
              フリマへ戻る
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="trade-chat-page dm-room-page" data-spa-page="フリマ">
      <div className="main-inner dm-room-main">
        <Link className="back-link" to={`/flea/products/${room.product.id}`}>
          ← 商品詳細へ戻る
        </Link>
        <p>
          <Link className="back-link" to="/dm">
            ← メッセージ一覧
          </Link>
        </p>

        <div className="chat-product-card">
          <div className="chat-product-card-inner">
            <div className="chat-product-thumb">
              {room.product_thumbnail_url ? (
                <img
                  src={room.product_thumbnail_url}
                  alt={room.product.name}
                />
              ) : (
                "📦"
              )}
            </div>
            <div>
              <p className="chat-product-name">{room.product.name}</p>
              <p className="chat-status">
                {room.trade_status_label} · 相手:{" "}
                {room.partner?.display_name || "—"}
              </p>
            </div>
          </div>
        </div>

        {actionError ? (
          <p className="trade-action-error" role="alert">
            {actionError}
          </p>
        ) : null}

        {(room.can_confirm_trade || room.can_complete_handover) && (
          <div className="chat-actions">
            {room.can_confirm_trade ? (
              <button
                type="button"
                onClick={() => void onConfirm()}
                disabled={busy}
              >
                取引を開始する
              </button>
            ) : null}
            {room.can_complete_handover ? (
              <button
                type="button"
                onClick={() => void onHandover()}
                disabled={busy}
              >
                {busy ? "処理中…" : "受け渡し完了"}
              </button>
            ) : null}
          </div>
        )}

        <div className="chat-messages dm-thread" ref={threadRef} aria-live="polite">
          {loadingOlder ? (
            <p className="chat-hint" style={{ textAlign: "center" }}>
              過去のメッセージを読み込み中…
            </p>
          ) : hasMore ? (
            <p className="chat-hint" style={{ textAlign: "center" }}>
              上にスクロールして過去のメッセージを表示
            </p>
          ) : null}
          {messages.map((m) =>
            m.is_system ? (
              <div key={m.id} className="chat-bubble system">
                {m.body}
              </div>
            ) : (
              <div
                key={m.id}
                className={`chat-item${m.is_mine ? " mine" : " theirs"}`}
              >
                <div className="chat-meta">
                  {m.sender_name} · {m.created_at}
                </div>
                <div className="chat-bubble">{m.body}</div>
              </div>
            )
          )}
          <div ref={bottomRef} />
        </div>

        {room.can_send_message ? (
          <ChatComposeBar
            value={body}
            onChange={setBody}
            onSend={onSend}
            busy={busy}
          />
        ) : (
          <p className="chat-status">このチャットはメッセージ送信できません。</p>
        )}
      </div>
    </div>
  );
}
