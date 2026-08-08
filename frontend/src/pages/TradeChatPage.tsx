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
  sendChatMessage,
  type ChatMessage,
  type ChatRoomDetail,
} from "../features/flea/api";
import { TRADE_POLL_MS, useChatPoll } from "../features/dm/useChatPoll";

export function TradeChatPage() {
  const { roomPk } = useParams();
  const roomId = Number(roomPk);
  const navigate = useNavigate();
  const { me } = useSession();
  const [room, setRoom] = useState<ChatRoomDetail | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const latestIdRef = useRef(0);
  const [body, setBody] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const bottomRef = useRef<HTMLDivElement | null>(null);
  const roomIdRef = useRef(roomId);
  roomIdRef.current = roomId;

  const appendMessages = useCallback((incoming: ChatMessage[]) => {
    if (!incoming.length) return;
    setMessages((prev) => {
      const known = new Set(prev.map((m) => m.id));
      const next = incoming.filter((m) => !known.has(m.id));
      return next.length ? [...prev, ...next] : prev;
    });
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
    latestIdRef.current = 0;
    void (async () => {
      try {
        const detail = await fetchChatRoom(roomId);
        if (ac.signal.aborted) return;
        setRoom(detail);
        const initial = await fetchChatMessages(roomId, undefined, ac.signal);
        if (ac.signal.aborted) return;
        setMessages(initial.messages);
        latestIdRef.current = initial.latest_id;
        setError(null);
      } catch (err) {
        if ((err as Error)?.name === "AbortError") return;
        setError(err instanceof Error ? err.message : "load_failed");
      } finally {
        if (!ac.signal.aborted) setLoading(false);
      }
    })();
    return () => ac.abort();
  }, [me?.authenticated, roomId, roomPk]);

  useChatPoll(
    Boolean(me?.authenticated && room && !loading),
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
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length]);

  const onSend = async (e: FormEvent) => {
    e.preventDefault();
    if (!body.trim() || !room?.can_send_message) return;
    setBusy(true);
    try {
      const message = await sendChatMessage(roomId, body.trim());
      appendMessages([message]);
      latestIdRef.current = Math.max(latestIdRef.current, message.id);
      setBody("");
    } catch (err) {
      window.alert(err instanceof Error ? err.message : "送信に失敗しました");
    } finally {
      setBusy(false);
    }
  };

  const onConfirm = async () => {
    if (!window.confirm("この交渉を取引開始（pending）にしますか？")) return;
    setBusy(true);
    try {
      const updated = await confirmTrade(roomId);
      setRoom(updated);
      const data = await fetchChatMessages(roomId);
      setMessages(data.messages);
      latestIdRef.current = data.latest_id;
    } catch (err) {
      window.alert(err instanceof Error ? err.message : "取引開始に失敗しました");
    } finally {
      setBusy(false);
    }
  };

  const onHandover = async () => {
    if (!window.confirm("受け渡し完了として売り切れにしますか？")) return;
    setBusy(true);
    try {
      const updated = await completeHandover(roomId);
      setRoom(updated);
      const data = await fetchChatMessages(roomId);
      setMessages(data.messages);
      latestIdRef.current = data.latest_id;
    } catch (err) {
      window.alert(
        err instanceof Error ? err.message : "受け渡し完了に失敗しました"
      );
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

  return (
    <div className="trade-chat-page" data-spa-page="フリマ">
      <div className="main-inner">
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

        {(room.can_confirm_trade || room.can_complete_handover) && (
          <div className="chat-actions">
            {room.can_confirm_trade ? (
              <button type="button" onClick={() => void onConfirm()} disabled={busy}>
                取引を開始する
              </button>
            ) : null}
            {room.can_complete_handover ? (
              <button
                type="button"
                onClick={() => void onHandover()}
                disabled={busy}
              >
                受け渡し完了
              </button>
            ) : null}
          </div>
        )}

        <div className="chat-messages" aria-live="polite">
          {messages.map((m) => (
            <div
              key={m.id}
              className={`chat-bubble${
                m.is_system ? " system" : m.is_mine ? " mine" : " theirs"
              }`}
            >
              {!m.is_system ? (
                <p className="chat-meta">
                  {m.sender_name} · {m.created_at}
                </p>
              ) : null}
              {m.body}
            </div>
          ))}
          <div ref={bottomRef} />
        </div>

        {room.can_send_message ? (
          <form className="chat-compose" onSubmit={(e) => void onSend(e)}>
            <input
              value={body}
              onChange={(e) => setBody(e.target.value)}
              maxLength={500}
              placeholder="メッセージを入力..."
              aria-label="メッセージ"
            />
            <button type="submit" disabled={busy || !body.trim()}>
              送信
            </button>
          </form>
        ) : (
          <p className="chat-status">このチャットはメッセージ送信できません。</p>
        )}
      </div>
    </div>
  );
}
