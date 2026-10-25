import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type FormEvent,
} from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useSession } from "../lib/session";
import { spaLoginPath } from "../features/auth/api";
import {
  deleteCourseTalkMessage,
  fetchOlderCourseTalkMessages,
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
import { ChatDateDivider } from "../features/chat/ChatDateDivider";
import { ChatRoomHeader } from "../features/chat/ChatRoomHeader";
import {
  ChatComposeSkeleton,
  ChatHeaderSkeleton,
  ChatLoadError,
  ChatThreadSkeleton,
} from "../features/chat/ChatRoomSkeleton";
import { readCourseHeaderPreview } from "../features/chat/inboxRoomPreview";
import { chatContentPhase } from "../lib/chatContentPhase";
import {
  isLatestRequest,
  isSameUserScope,
  nextRequestId,
} from "../lib/userScopedResult";
import { ChatReplyPreview, type ReplyTarget } from "../features/chat/ChatReplyPreview";
import { ChatThreadMessage } from "../features/chat/ChatThreadMessage";
import { buildChatThread } from "../features/chat/chatThread";
import {
  isChatNearBottom,
  mergeUniqueByIdAsc,
  scrollChatToBottom,
  useChatVisibleFrameHeight,
  useKeepChatPinnedOnCompose,
  useLoadOlderChatMessages,
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
  const sessionUserId =
    me?.authenticated && me.user?.id != null ? me.user.id : null;
  const userIdRef = useRef(sessionUserId);
  userIdRef.current = sessionUserId;
  const prevUserIdRef = useRef(sessionUserId);
  const fetchGen = useRef(0);
  const [offering, setOffering] = useState<CourseOffering | null>(null);
  const [room, setRoom] = useState<CourseTalkRoom | null>(null);
  const [messages, setMessages] = useState<CourseTalkMessage[]>([]);
  const [hasMore, setHasMore] = useState(false);
  const [nextBefore, setNextBefore] = useState<number | null>(null);
  const latestIdRef = useRef(0);
  const roomIdRef = useRef(0);
  const [body, setBody] = useState("");
  const [replyingTo, setReplyingTo] = useState<ReplyTarget | null>(null);
  const [loading, setLoading] = useState(true);
  const [hydrated, setHydrated] = useState(false);
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
    setMessages((prev) => mergeUniqueByIdAsc(prev, incoming, "append"));
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

  useLayoutEffect(() => {
    nextRequestId(fetchGen);
    setOffering(null);
    setRoom(null);
    setMessages([]);
    setHasMore(false);
    setNextBefore(null);
    setBody("");
    setReplyingTo(null);
    setHighlightId(null);
    latestIdRef.current = 0;
    roomIdRef.current = 0;
    setLoading(true);
    setHydrated(false);
    setError(null);
  }, [offeringId]);

  useLayoutEffect(() => {
    if (prevUserIdRef.current === sessionUserId) return;
    prevUserIdRef.current = sessionUserId;
    nextRequestId(fetchGen);
    setOffering(null);
    setRoom(null);
    setMessages([]);
    setHasMore(false);
    setNextBefore(null);
    setBody("");
    setReplyingTo(null);
    setHighlightId(null);
    latestIdRef.current = 0;
    roomIdRef.current = 0;
    setLoading(true);
    setHydrated(false);
    setError(null);
  }, [sessionUserId]);

  const load = useCallback(
    async (signal?: AbortSignal) => {
      if (!Number.isFinite(offeringId)) {
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
        const data = await openCourseTalk(offeringId);
        if (signal?.aborted) return;
        if (!isLatestRequest(fetchGen, gen)) return;
        if (!isSameUserScope(startedUserId, userIdRef.current)) return;
        setOffering(data.offering);
        setRoom(data.room);
        setMessages(data.messages || []);
        setHasMore(Boolean(data.has_more));
        setNextBefore(
          data.next_before != null ? Number(data.next_before) : null
        );
        latestIdRef.current = data.room.latest_id || 0;
        roomIdRef.current = data.room.id;
        setHydrated(true);
        requestAnimationFrame(() => {
          scrollChatToBottom(threadRef.current, "auto");
        });
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
      } catch (err) {
        if ((err as { name?: string } | null)?.name === "AbortError") return;
        if (!isLatestRequest(fetchGen, gen)) return;
        if (!isSameUserScope(startedUserId, userIdRef.current)) return;
        setOffering(null);
        setRoom(null);
        setMessages([]);
        setError(err instanceof Error ? err.message : "load_failed");
        setHydrated(true);
      } finally {
        if (isLatestRequest(fetchGen, gen)) setLoading(false);
      }
    },
    [offeringId, fromInbox]
  );

  useEffect(() => {
    if (sessionLoading) return;
    if (!me?.authenticated) {
      navigate(spaLoginPath(`/app/courses/${offeringPk || ""}/talk`), {
        replace: true,
      });
      return;
    }
    const ac = new AbortController();
    void load(ac.signal);
    return () => ac.abort();
  }, [me?.authenticated, sessionLoading, offeringId, offeringPk, navigate, load, sessionUserId]);

  const fetchOlder = useCallback(
    (beforeId: number) =>
      fetchOlderCourseTalkMessages(roomIdRef.current, beforeId),
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
    if (loadingOlder) return;
    const scroller = threadRef.current;
    if (!isChatNearBottom(scroller)) return;
    scrollChatToBottom(scroller, "smooth");
  }, [messages.length, loadingOlder]);

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
    if (!hydrated || !body.trim() || !room?.can_send || busy) return;
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
    if (!hydrated || !offering) return;
    if (
      !window.confirm(
        "授業掲示板から退出しますか？\n投稿は残ります。再度開くと再参加できます。"
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

  const liveOffering =
    offering && offering.id === offeringId ? offering : null;
  const liveRoom = liveOffering ? room : null;
  const phase = chatContentPhase({
    loading: sessionLoading || loading,
    error,
    hasRoom: Boolean(liveRoom && liveOffering),
    hydrated: Boolean(liveRoom && liveOffering) && hydrated,
    messageCount: liveRoom ? messages.length : 0,
  });
  const headerPreview = readCourseHeaderPreview(sessionUserId, offeringId);

  return (
    <div
      className="dm-page dm-room-page course-talk-page"
      data-spa-page="授業掲示板"
    >
      <main className="main-inner dm-room-main">
        {liveOffering && liveRoom ? (
          <ChatRoomHeader
            backTo="/dm?tab=course"
            backLabel="授業掲示板一覧"
            title={liveOffering.title}
            subtitle={`${liveOffering.instructor} · ${offeringScheduleText(liveOffering)}`}
            avatarInitial={(liveOffering.title || "授").slice(0, 1)}
            detailsTo={`/courses/${liveOffering.id}`}
            detailsLabel="授業詳細"
            trailing={
              <button
                type="button"
                className="chat-room-header__leave"
                disabled={leaveBusy || !hydrated}
                onClick={() => void onLeave()}
              >
                退出
              </button>
            }
          />
        ) : (
          <ChatHeaderSkeleton
            backTo="/dm?tab=course"
            backLabel="授業掲示板一覧"
            preview={headerPreview}
          />
        )}

        {phase === "error" || (hydrated && (!liveRoom || !liveOffering)) ? (
          <ChatLoadError
            message={`授業掲示板を表示できません（${error || "not_found"}）`}
            onRetry={() => void load()}
          />
        ) : phase === "skeleton" || !liveRoom || !liveOffering ? (
          <section className="chat-panel" aria-label="授業掲示板">
            <ChatThreadSkeleton />
            <ChatComposeSkeleton />
          </section>
        ) : (
          <>

        <div className="dm-thread course-talk-thread" ref={threadRef}>
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
            <div className="course-talk-empty">
              <strong>まだ投稿はありません</strong>
              <p>履修中・履修済み・検討中の人も、この授業について質問できます</p>
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
              {buildChatThread(messages).map((entry) =>
                entry.kind === "day" ? (
                  <ChatDateDivider key={entry.key} label={entry.label} />
                ) : (
                  <ChatThreadMessage
                    key={entry.message.id}
                    kind="course"
                    message={entry.message}
                    layout={entry.layout}
                    canAct={hydrated}
                    canReply={Boolean(liveRoom.can_send)}
                    highlightedId={highlightId}
                    onReply={setReplyingTo}
                    onDelete={async (id) => {
                      if (!hydrated) return;
                      const updated = await deleteCourseTalkMessage(
                        liveRoom.id,
                        id
                      );
                      upsertMessage(updated);
                    }}
                    onScrollToReply={scrollToReply}
                    onToast={showToast}
                  />
                )
              )}
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
          disabled={!hydrated || !liveRoom.can_send}
          busy={busy}
          placeholder={
            replyingTo ? "返信を入力…" : "質問や口コミを投稿…"
          }
        />
          </>
        )}
      </main>
      {toast ? <div className="chat-toast">{toast}</div> : null}
    </div>
  );
}
