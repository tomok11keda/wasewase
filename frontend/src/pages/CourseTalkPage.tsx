import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type FormEvent,
} from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useSession } from "../lib/session";
import { spaLoginPath } from "../features/auth/api";
import {
  deleteCourseTalkMessage,
  leaveCourseTalk,
  offeringScheduleText,
  openCourseTalk,
  pollCourseTalkMessages,
  sendCourseTalkMessage,
  type CourseOffering,
  type CourseTalkMessage,
  type CourseTalkRoom,
} from "../features/courses/api";
import { DM_POLL_MS, useChatPoll } from "../features/dm/useChatPoll";
import { ChatComposeBar } from "../components/ChatComposeBar";
import { ChatReplyPreview, type ReplyTarget } from "../features/chat/ChatReplyPreview";
import { ChatThreadMessage } from "../features/chat/ChatThreadMessage";
import {
  isChatNearBottom,
  scrollChatToBottom,
  useChatVisibleFrameHeight,
  useKeepChatPinnedOnCompose,
} from "../features/chat/useChatRoomLayout";
import { analytics } from "../lib/analytics/events";

const EMPTY_PROMPTS = [
  "この授業の課題量どうですか？",
  "テストはどんな形式ですか？",
  "出席は毎回取りますか？",
];

export function CourseTalkPage() {
  const { offeringPk } = useParams();
  const offeringId = Number(offeringPk);
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { me, loading: sessionLoading } = useSession();
  const [offering, setOffering] = useState<CourseOffering | null>(null);
  const [room, setRoom] = useState<CourseTalkRoom | null>(null);
  const [messages, setMessages] = useState<CourseTalkMessage[]>([]);
  const latestIdRef = useRef(0);
  const roomIdRef = useRef(0);
  const [body, setBody] = useState("");
  const [replyingTo, setReplyingTo] = useState<ReplyTarget | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [leaveBusy, setLeaveBusy] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [highlightId, setHighlightId] = useState<number | null>(null);
  const bottomRef = useRef<HTMLDivElement | null>(null);
  const threadRef = useRef<HTMLDivElement | null>(null);
  const fromInbox = searchParams.get("from") === "inbox";

  useChatVisibleFrameHeight(true);
  useKeepChatPinnedOnCompose(threadRef, true);

  const showToast = useCallback((text: string) => {
    setToast(text);
    window.setTimeout(() => setToast(null), 1800);
  }, []);

  const appendMessages = useCallback((incoming: CourseTalkMessage[]) => {
    if (!incoming.length) return;
    setMessages((prev) => {
      const known = new Set(prev.map((m) => m.id));
      const next = incoming.filter((m) => !known.has(m.id));
      return next.length ? [...prev, ...next] : prev;
    });
  }, []);

  const upsertMessage = useCallback((message: CourseTalkMessage) => {
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
      navigate(spaLoginPath(`/app/courses/${offeringPk || ""}/talk`), {
        replace: true,
      });
      return;
    }
    if (!Number.isFinite(offeringId)) {
      setError("invalid_id");
      setLoading(false);
      return;
    }
    const ac = new AbortController();
    setLoading(true);
    setError(null);
    void openCourseTalk(offeringId)
      .then((data) => {
        if (ac.signal.aborted) return;
        setOffering(data.offering);
        setRoom(data.room);
        setMessages(data.messages || []);
        latestIdRef.current = data.room.latest_id || 0;
        roomIdRef.current = data.room.id;
        if (data.joined_now) {
          analytics.courseChatJoined();
        }
        analytics.courseChatOpened({
          from_detail: !fromInbox,
          from_inbox: fromInbox,
        });
        if (fromInbox) {
          analytics.courseChatOpenedFromInbox();
        } else {
          analytics.courseChatOpenedFromDetail();
        }
      })
      .catch((err) => {
        if (ac.signal.aborted) return;
        setError(err instanceof Error ? err.message : "load_failed");
      })
      .finally(() => {
        if (!ac.signal.aborted) setLoading(false);
      });
    return () => ac.abort();
  }, [me?.authenticated, sessionLoading, offeringId, offeringPk, fromInbox, navigate]);

  useChatPoll(
    Boolean(me?.authenticated && room && !loading),
    DM_POLL_MS,
    async (signal) => {
      const id = roomIdRef.current;
      if (!Number.isFinite(id) || !id) return;
      const data = await pollCourseTalkMessages(
        id,
        latestIdRef.current || 0,
        signal
      );
      if (signal.aborted) return;
      appendMessages(data.messages || []);
      if (typeof data.latest_id === "number") {
        latestIdRef.current = data.latest_id;
      }
    }
  );

  useEffect(() => {
    const scroller = threadRef.current;
    if (!isChatNearBottom(scroller)) return;
    scrollChatToBottom(scroller, "smooth");
  }, [messages.length]);

  const scrollToReply = useCallback((messageId: number) => {
    const el = document.getElementById(`chat-msg-${messageId}`);
    if (!el) {
      showToast("元のメッセージはまだ読み込まれていません");
      return;
    }
    el.scrollIntoView({ behavior: "smooth", block: "center" });
    setHighlightId(messageId);
    window.setTimeout(() => setHighlightId(null), 1200);
  }, [showToast]);

  const onSend = async (e: FormEvent) => {
    e.preventDefault();
    if (!body.trim() || !room?.can_send) return;
    const replyId = replyingTo?.id ?? null;
    setBusy(true);
    try {
      const message = await sendCourseTalkMessage(
        room.id,
        body.trim(),
        replyId
      );
      upsertMessage(message);
      latestIdRef.current = Math.max(latestIdRef.current, message.id);
      setBody("");
      if (replyId) {
        analytics.chatReplySent({ kind: "course" });
        setReplyingTo(null);
      }
      analytics.courseChatMessageSent();
    } catch (err) {
      window.alert(err instanceof Error ? err.message : "送信に失敗しました");
    } finally {
      setBusy(false);
    }
  };

  const onLeave = async () => {
    if (!offering) return;
    if (
      !window.confirm(
        "授業トークから退出しますか？\nメッセージ履歴は残ります。再度開くと再参加できます。"
      )
    ) {
      return;
    }
    setLeaveBusy(true);
    try {
      await leaveCourseTalk(offering.id);
      analytics.courseChatLeft();
      navigate("/dm?tab=course", { replace: true });
    } catch (err) {
      window.alert(err instanceof Error ? err.message : "退出に失敗しました");
    } finally {
      setLeaveBusy(false);
    }
  };

  if (loading || sessionLoading) {
    return (
      <div className="dm-page course-talk-page" data-spa-page="授業トーク">
        <div className="main-inner">
          <p>読み込み中…</p>
        </div>
      </div>
    );
  }

  if (error || !room || !offering) {
    return (
      <div className="dm-page course-talk-page" data-spa-page="授業トーク">
        <div className="main-inner">
          <Link className="dm-back-text" to="/dm?tab=course">
            ← 授業トーク一覧
          </Link>
          <p>授業トークを表示できません（{error || "not_found"}）</p>
        </div>
      </div>
    );
  }

  return (
    <div
      className="dm-page dm-room-page course-talk-page"
      data-spa-page="授業トーク"
    >
      <main className="main-inner dm-room-main">
        <p className="dm-room-top">
          <Link className="dm-back-text" to="/dm?tab=course">
            ← 授業トーク一覧
          </Link>
        </p>

        <section className="dm-partner-card course-talk-header">
          <h1 className="dm-partner-name">{offering.title}</h1>
          <p className="dm-partner-meta">
            {offering.instructor}
            {" ｜ "}
            {offeringScheduleText(offering)}
          </p>
          <p className="course-talk-header__links">
            <Link to={`/courses/${offering.id}`}>授業詳細</Link>
            <button
              type="button"
              className="course-talk-leave"
              disabled={leaveBusy}
              onClick={() => void onLeave()}
            >
              退出
            </button>
          </p>
        </section>

        <div className="dm-thread course-talk-thread" ref={threadRef}>
          {messages.length === 0 ? (
            <div className="course-talk-empty">
              <strong>まだトークはありません</strong>
              <p>この授業について気になることを聞いてみよう</p>
              <ul>
                {EMPTY_PROMPTS.map((p) => (
                  <li key={p}>
                    <button
                      type="button"
                      className="course-talk-prompt"
                      onClick={() => setBody(p)}
                    >
                      {p}
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          ) : (
            <ul className="message-list">
              {messages.map((m) => (
                <ChatThreadMessage
                  key={m.id}
                  kind="course"
                  message={m}
                  canAct
                  canReply={Boolean(room.can_send)}
                  highlightedId={highlightId}
                  onReply={setReplyingTo}
                  onDelete={async (id) => {
                    const updated = await deleteCourseTalkMessage(room.id, id);
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
          disabled={!room.can_send}
          busy={busy}
          placeholder={
            replyingTo ? "返信を入力…" : "質問や口コミを投稿…"
          }
        />
      </main>
      {toast ? <div className="chat-toast">{toast}</div> : null}
    </div>
  );
}
