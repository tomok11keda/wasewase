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
  fetchGroupRoom,
  pollGroupMessages,
  sendGroupMessage,
  type ChatMessage,
  type GroupRoomDetail,
} from "../features/dm/api";
import { DM_POLL_MS, useChatPoll } from "../features/dm/useChatPoll";

export function GroupRoomPage() {
  const { roomPk } = useParams();
  const roomId = Number(roomPk);
  const navigate = useNavigate();
  const { me, loading: sessionLoading } = useSession();
  const [room, setRoom] = useState<GroupRoomDetail | null>(null);
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
    latestIdRef.current = 0;
    void fetchGroupRoom(roomId, ac.signal)
      .then((data) => {
        setRoom(data.room);
        setMessages(data.messages || []);
        latestIdRef.current = data.room.latest_id || 0;
        setError(null);
      })
      .catch((err) => {
        if (err?.name === "AbortError") return;
        setError(err instanceof Error ? err.message : "load_failed");
      })
      .finally(() => setLoading(false));
    return () => ac.abort();
  }, [me?.authenticated, sessionLoading, roomId, roomPk]);

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
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length]);

  const onSend = async (e: FormEvent) => {
    e.preventDefault();
    if (!body.trim() || !room?.can_send) return;
    setBusy(true);
    try {
      const message = await sendGroupMessage(roomId, body.trim());
      appendMessages([message]);
      latestIdRef.current = Math.max(latestIdRef.current, message.id);
      setBody("");
    } catch (err) {
      window.alert(err instanceof Error ? err.message : "送信に失敗しました");
    } finally {
      setBusy(false);
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
          </p>
        </section>

        <section className="chat-panel" aria-label="グループチャット">
          <h2>メッセージ</h2>
          <p className="chat-hint">グループのやり取りです（15秒ごとに自動更新）</p>

          <div className="dm-message-area">
            {messages.length === 0 ? (
              <p className="empty-message">まだメッセージはありません。</p>
            ) : (
              <ul className="message-list">
                {messages.map((m) => (
                  <li
                    key={m.id}
                    className={`chat-row${m.is_mine ? " is-mine" : ""}`}
                    data-message-id={m.id}
                  >
                    <div className="chat-row__avatar" aria-hidden="true">
                      {m.avatar_url ? (
                        <img
                          className="user-avatar--image"
                          src={m.avatar_url}
                          alt=""
                        />
                      ) : (
                        <span className="user-avatar--initial">
                          {m.sender_initial || "?"}
                        </span>
                      )}
                    </div>
                    <div className="chat-row__main">
                      {!m.is_mine ? (
                        <div className="chat-row__sender">{m.sender_name}</div>
                      ) : null}
                      <div className="chat-row__bubble-wrap">
                        <div className="chat-row__bubble">{m.body}</div>
                        <time className="chat-row__time">{m.created_at}</time>
                      </div>
                    </div>
                  </li>
                ))}
              </ul>
            )}
            <div ref={bottomRef} />
          </div>

          <form className="chat-form" onSubmit={(e) => void onSend(e)}>
            <input
              value={body}
              onChange={(e) => setBody(e.target.value)}
              maxLength={500}
              placeholder="メッセージを入力..."
              aria-label="メッセージ"
              autoComplete="off"
            />
            <button type="submit" disabled={busy || !body.trim()}>
              送信
            </button>
          </form>
        </section>
      </main>
    </div>
  );
}
