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
  acceptMessageRequest,
  declineMessageRequest,
  fetchDmRoom,
  pollDmMessages,
  sendDmMessage,
  type ChatMessage,
  type DmRoomDetail,
} from "../features/dm/api";
import { DM_POLL_MS, useChatPoll } from "../features/dm/useChatPoll";

export function DmRoomPage() {
  const { roomPk } = useParams();
  const roomId = Number(roomPk);
  const navigate = useNavigate();
  const { me, loading: sessionLoading } = useSession();
  const [room, setRoom] = useState<DmRoomDetail | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const latestIdRef = useRef(0);
  const [body, setBody] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [requestBusy, setRequestBusy] = useState(false);
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

  const applyReadIds = useCallback((ids: number[]) => {
    if (!ids.length) return;
    const set = new Set(ids);
    setMessages((prev) =>
      prev.map((m) =>
        m.is_mine && set.has(m.id) ? { ...m, is_read: true } : m
      )
    );
  }, []);

  useEffect(() => {
    if (sessionLoading) return;
    if (!me?.authenticated) {
      navigate(spaLoginPath(`/app/dm/${roomPk || ""}`), { replace: true });
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
    void fetchDmRoom(roomId, ac.signal)
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
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length]);

  const onSend = async (e: FormEvent) => {
    e.preventDefault();
    if (!body.trim() || !room?.can_send) return;
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
          <p>DMを表示できません（{error || "not_found"}）</p>
        </div>
      </div>
    );
  }

  const partnerName = room.is_blocked
    ? "不明なユーザー"
    : room.partner?.display_name || "DM";
  const partnerInitial = room.is_blocked
    ? "?"
    : room.partner?.initial || partnerName.slice(0, 1);

  return (
    <div className="dm-page dm-room-page" data-spa-page="メッセージ">
      <main className="main-inner dm-room-main">
        <p className="dm-room-top">
          <Link className="dm-back-text" to="/dm">
            ← メッセージ一覧
          </Link>
        </p>

        {room.partner || room.is_blocked ? (
          <section
            className={`dm-partner-card${
              room.is_blocked ? " dm-partner-card--blocked" : ""
            }`}
          >
            <div className="dm-partner-row">
              <span className="dm-partner-avatar" aria-hidden="true">
                {room.partner?.avatar_url && !room.is_blocked ? (
                  <img
                    className="user-avatar--image"
                    src={room.partner.avatar_url}
                    alt=""
                  />
                ) : (
                  <span className="user-avatar--initial">{partnerInitial}</span>
                )}
              </span>
              <div className="dm-partner-text">
                <h1 className="dm-partner-name">{partnerName}</h1>
                <p className="dm-partner-meta">
                  {room.is_blocked ? (
                    "ブロック中のためプロフィールは表示できません"
                  ) : room.partner ? (
                    <Link to={`/users/${room.partner.id}/posts`}>
                      プロフィールを見る
                    </Link>
                  ) : null}
                </p>
              </div>
            </div>
          </section>
        ) : null}

        {isPendingRequest ? (
          <section className="dm-group-invite-banner" aria-label="メッセージリクエスト">
            <p className="dm-group-invite-banner__lead">
              {(room.message_request?.from_user?.display_name ||
                room.partner?.display_name ||
                "ユーザー") + "さんからメッセージリクエストが届いています"}
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
          <h2>メッセージ</h2>
          {!room.can_send || room.is_blocked ? (
            <p className="block-banner">
              {room.is_blocked
                ? "このユーザーをブロック中です。メッセージの送信はできません。"
                : "このユーザーとはメッセージの送受信が制限されています。"}
            </p>
          ) : (
            <p className="chat-hint">1対1のやり取りです（15秒ごとに自動更新）</p>
          )}

          <div className="dm-message-area">
            {messages.length === 0 ? (
              <p className="empty-message">
                まだメッセージはありません。最初の一言を送ってみましょう。
              </p>
            ) : (
              <ul className="message-list">
                {messages.map((m) => (
                  <li
                    key={m.id}
                    className={`chat-row${m.is_mine ? " is-mine" : ""}`}
                    data-message-id={m.id}
                  >
                    <div className="chat-row__avatar" aria-hidden="true">
                      {m.avatar_url && !(room.is_blocked && !m.is_mine) ? (
                        <img
                          className="user-avatar--image"
                          src={m.avatar_url}
                          alt=""
                        />
                      ) : (
                        <span className="user-avatar--initial">
                          {room.is_blocked && !m.is_mine
                            ? "?"
                            : m.sender_initial || "?"}
                        </span>
                      )}
                    </div>
                    <div className="chat-row__main">
                      <div className="chat-row__bubble">{m.body}</div>
                      <div className="chat-row__meta">
                        {m.is_mine && m.is_read ? (
                          <span className="chat-row__read">既読</span>
                        ) : null}
                        <time className="chat-row__time">{m.created_at}</time>
                      </div>
                    </div>
                  </li>
                ))}
              </ul>
            )}
            <div ref={bottomRef} />
          </div>

          <form
            className={`chat-form${room.can_send ? "" : " chat-form--blocked"}`}
            onSubmit={(e) => void onSend(e)}
            aria-disabled={!room.can_send}
          >
            <input
              value={body}
              onChange={(e) => setBody(e.target.value)}
              maxLength={500}
              placeholder={
                room.is_blocked
                  ? "このユーザーはブロック中です"
                  : room.can_send
                    ? "メッセージを入力..."
                    : "メッセージを送信できません"
              }
              disabled={!room.can_send}
              autoComplete="off"
              aria-label="メッセージ"
            />
            {room.can_send ? (
              <button type="submit" disabled={busy || !body.trim()}>
                送信
              </button>
            ) : (
              <button type="button" disabled>
                送信
              </button>
            )}
          </form>
        </section>
      </main>
    </div>
  );
}
