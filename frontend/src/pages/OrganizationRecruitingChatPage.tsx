import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type FormEvent,
} from "react";
import { Link, Navigate, useNavigate, useParams } from "react-router-dom";
import { ChatComposeBar } from "../components/ChatComposeBar";
import { spaLoginPath } from "../features/auth/api";
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
import type { ChatMessage } from "../features/dm/api";
import { DM_POLL_MS, useChatPoll } from "../features/dm/useChatPoll";
import {
  fetchOrganizationProfile,
  OrganizationRequestError,
} from "../features/orgs/api";
import { RecruitingChatSection } from "../features/orgs/RecruitingChatSection";
import {
  recruitingChatApplicationsPath,
  recruitingChatMembersPath,
  recruitingChatSettingsPath,
  type RecruitingChat,
  type RecruitingChatEnvelope,
  type RecruitingRoom,
} from "../features/orgs/recruitingChat";
import {
  deleteRecruitingMessage,
  fetchOlderRecruitingMessages,
  fetchRecruitingChat,
  fetchRecruitingRoom,
  leaveRecruitingChat,
  pollRecruitingMessages,
  sendRecruitingMessage,
} from "../features/orgs/recruitingChatApi";
import { organizationInitial } from "../features/orgs/orgProfile";
import { analytics } from "../lib/analytics/events";
import { isBrowsePreview, useSession } from "../lib/session";

function isAbort(err: unknown): boolean {
  return (
    (err instanceof DOMException && err.name === "AbortError") ||
    (err instanceof Error && err.name === "AbortError")
  );
}

function isAccessLost(err: unknown): boolean {
  if (!(err instanceof OrganizationRequestError)) return false;
  return (
    err.status === 403 ||
    err.status === 404 ||
    err.code === "forbidden" ||
    err.code === "not_found"
  );
}

export function OrganizationRecruitingChatPage() {
  const { slug } = useParams();
  const navigate = useNavigate();
  const { me, loading: sessionLoading } = useSession();
  const browsePreview = isBrowsePreview(me);
  const [envelope, setEnvelope] = useState<RecruitingChatEnvelope | null>(null);
  const [orgName, setOrgName] = useState("");
  const [orgAvatar, setOrgAvatar] = useState("");
  const [room, setRoom] = useState<RecruitingRoom | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [hasMore, setHasMore] = useState(false);
  const [nextBefore, setNextBefore] = useState<number | null>(null);
  const latestIdRef = useRef(0);
  const [body, setBody] = useState("");
  const [replyingTo, setReplyingTo] = useState<ReplyTarget | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [accessLost, setAccessLost] = useState(false);
  const [busy, setBusy] = useState(false);
  const [leaveBusy, setLeaveBusy] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [highlightId, setHighlightId] = useState<number | null>(null);
  const bottomRef = useRef<HTMLDivElement | null>(null);
  const threadRef = useRef<HTMLDivElement | null>(null);
  const slugRef = useRef(slug);
  slugRef.current = slug;
  const roomIdRef = useRef<number | null>(null);

  useChatVisibleFrameHeight(true);
  useKeepChatPinnedOnCompose(threadRef, true);

  const showToast = useCallback((text: string) => {
    setToast(text);
    window.setTimeout(() => setToast(null), 1800);
  }, []);

  const clearThread = useCallback(() => {
    setRoom(null);
    setMessages([]);
    setHasMore(false);
    setNextBefore(null);
    latestIdRef.current = 0;
    roomIdRef.current = null;
    setReplyingTo(null);
    setAccessLost(false);
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

  const applyEnvelope = useCallback((next: RecruitingChatEnvelope) => {
    setEnvelope(next);
    const chat = next.recruiting_chat;
    if (!chat?.room_id || !chat.can_send) {
      setRoom(null);
      setMessages([]);
      roomIdRef.current = null;
    }
  }, []);

  useEffect(() => {
    if (sessionLoading) return;
    if (!me?.authenticated) {
      navigate(spaLoginPath(`/app/organizations/${slug || ""}/recruiting-chat`), {
        replace: true,
      });
      return;
    }
    if (!slug) {
      setError("not_found");
      setLoading(false);
      return;
    }
    const ac = new AbortController();
    const currentSlug = slug;
    setLoading(true);
    setError(null);
    setEnvelope(null);
    setOrgName("");
    setOrgAvatar("");
    clearThread();
    void (async () => {
      try {
        const [chatEnvelope, profile] = await Promise.all([
          fetchRecruitingChat(currentSlug, ac.signal),
          fetchOrganizationProfile(currentSlug).catch(() => null),
        ]);
        if (ac.signal.aborted || slugRef.current !== currentSlug) return;
        applyEnvelope(chatEnvelope);
        if (profile) {
          setOrgName(profile.organization.name);
          setOrgAvatar(profile.organization.avatar_url);
        }
        const roomId = chatEnvelope.recruiting_chat?.room_id;
        const canSend = Boolean(chatEnvelope.recruiting_chat?.can_send);
        if (!roomId || !canSend) {
          setLoading(false);
          return;
        }
        const data = await fetchRecruitingRoom(roomId, ac.signal);
        if (ac.signal.aborted || slugRef.current !== currentSlug) return;
        if (roomIdRef.current !== null && roomIdRef.current !== roomId) return;
        roomIdRef.current = data.room.id;
        setRoom(data.room);
        setMessages(data.messages || []);
        setHasMore(Boolean(data.has_more));
        setNextBefore(
          data.next_before != null ? Number(data.next_before) : null
        );
        latestIdRef.current = data.room.latest_id || 0;
        if (data.recruiting_chat) {
          applyEnvelope({
            ...chatEnvelope,
            recruiting_chat: data.recruiting_chat,
            can_manage:
              chatEnvelope.can_manage || data.recruiting_chat.can_manage,
          });
        }
        requestAnimationFrame(() => {
          scrollChatToBottom(threadRef.current, "auto");
        });
      } catch (err) {
        if (isAbort(err) || slugRef.current !== currentSlug) return;
        clearThread();
        if (isAccessLost(err)) {
          setAccessLost(true);
          setError(
            err instanceof OrganizationRequestError ? err.code : "forbidden"
          );
        } else {
          setError(err instanceof Error ? err.message : "load_failed");
        }
      } finally {
        if (!ac.signal.aborted && slugRef.current === currentSlug) {
          setLoading(false);
        }
      }
    })();
    return () => ac.abort();
  }, [me?.authenticated, sessionLoading, slug, navigate, clearThread, applyEnvelope]);

  const chat = envelope?.recruiting_chat ?? null;
  const canManage = Boolean(envelope?.can_manage || chat?.can_manage);
  const canSend = Boolean(
    chat?.can_send && chat.room_id && room?.can_send && !accessLost
  );
  const showThread = Boolean(canSend && room && !accessLost);

  const fetchOlder = useCallback((beforeId: number) => {
    const id = roomIdRef.current;
    if (id == null) return Promise.resolve({ messages: [] });
    return fetchOlderRecruitingMessages(id, beforeId);
  }, []);

  const { loadingOlder } = useLoadOlderChatMessages({
    enabled: Boolean(me?.authenticated && showThread && !loading),
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
    Boolean(me?.authenticated && showThread && !loading),
    DM_POLL_MS,
    async (signal) => {
      const id = roomIdRef.current;
      const currentSlug = slugRef.current;
      if (id == null) return;
      try {
        const data = await pollRecruitingMessages(
          id,
          latestIdRef.current || 0,
          signal
        );
        if (signal.aborted || slugRef.current !== currentSlug) return;
        if (roomIdRef.current !== id) return;
        appendMessages(data.messages || []);
        if (typeof data.latest_id === "number") {
          latestIdRef.current = data.latest_id;
        }
      } catch (err) {
        if (isAbort(err) || slugRef.current !== currentSlug) return;
        if (isAccessLost(err)) {
          clearThread();
          setAccessLost(true);
          setEnvelope((prev) =>
            prev
              ? {
                  ...prev,
                  recruiting_chat: prev.recruiting_chat
                    ? {
                        ...prev.recruiting_chat,
                        can_send: false,
                        room_id: null,
                        can_leave: false,
                      }
                    : null,
                }
              : prev
          );
        }
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
    const id = roomIdRef.current;
    if (!body.trim() || !canSend || id == null || busy) return;
    const replyId = replyingTo?.id ?? null;
    const sentBody = body;
    setBusy(true);
    try {
      const message = await sendRecruitingMessage(id, sentBody.trim(), replyId);
      if (roomIdRef.current !== id) return;
      upsertMessage(message);
      latestIdRef.current = Math.max(latestIdRef.current, message.id);
      setBody("");
      if (replyId) {
        analytics.chatReplySent({ kind: "recruiting" });
        setReplyingTo(null);
      }
    } catch (err) {
      if (isAccessLost(err)) {
        clearThread();
        setAccessLost(true);
        setBody(sentBody);
      } else {
        window.alert(err instanceof Error ? err.message : "送信に失敗しました");
      }
    } finally {
      setBusy(false);
    }
  };

  const onLeave = async () => {
    if (!slug) return;
    if (
      !window.confirm(
        "新歓チャットから退出しますか？退出するとメッセージを読めなくなります。"
      )
    ) {
      return;
    }
    if (leaveBusy) return;
    setLeaveBusy(true);
    try {
      const next = await leaveRecruitingChat(slug);
      clearThread();
      setEnvelope((prev) =>
        prev
          ? {
              ...prev,
              recruiting_chat: next,
              can_manage: prev.can_manage || next.can_manage,
            }
          : prev
      );
    } catch (err) {
      window.alert(err instanceof Error ? err.message : "退出に失敗しました");
    } finally {
      setLeaveBusy(false);
    }
  };

  if (!slug) return <Navigate to="/" replace />;

  if (browsePreview) {
    return (
      <div className="dm-page" data-spa-page="新歓チャット">
        <div className="main-inner">
          <p>新歓チャットはログイン後に利用できます。</p>
        </div>
      </div>
    );
  }

  if (loading || sessionLoading) {
    return (
      <div className="dm-page" data-spa-page="新歓チャット">
        <div className="main-inner">
          <p>読み込み中…</p>
        </div>
      </div>
    );
  }

  const displayName = chat?.name || room?.name || "新歓チャット";
  const orgLabel = orgName || room?.organization_name || "";

  if (error === "not_found" && !envelope) {
    return (
      <div className="dm-page" data-spa-page="新歓チャット">
        <div className="main-inner">
          <Link className="dm-back-text" to="/dm">
            ← メッセージ一覧
          </Link>
          <p>新歓チャットが見つからないか、表示できません。</p>
        </div>
      </div>
    );
  }

  return (
    <div className="dm-page dm-room-page org-recruiting-room" data-spa-page="新歓チャット">
      <main className="main-inner dm-room-main">
        <p className="dm-room-top">
          <Link className="dm-back-text" to="/dm">
            ← メッセージ一覧
          </Link>
        </p>

        <section className="dm-partner-card org-recruiting-room__header">
          {orgAvatar ? (
            <img
              className="org-recruiting-room__avatar user-avatar--image"
              src={orgAvatar}
              alt=""
            />
          ) : (
            <span className="org-recruiting-room__avatar user-avatar--icon">
              {organizationInitial(orgLabel || displayName)}
            </span>
          )}
          <div>
            <h1 className="dm-partner-name">{displayName}</h1>
            <p className="dm-partner-meta">
              {orgLabel ? (
                <Link to={`/orgs/${slug}`}>{orgLabel}</Link>
              ) : (
                "新歓チャット"
              )}
              {room ? ` · メンバー ${room.member_count}人` : ""}
            </p>
          </div>
        </section>

        {canManage ? (
          <p className="org-recruiting-room__admin">
            <Link to={recruitingChatSettingsPath(slug)}>設定</Link>
            <Link to={recruitingChatApplicationsPath(slug)}>申請管理</Link>
            <Link to={recruitingChatMembersPath(slug)}>参加者管理</Link>
          </p>
        ) : null}

        {accessLost ? (
          <p className="org-recruiting-card__closed" role="status">
            このチャットを表示する権限がなくなりました。
          </p>
        ) : null}

        {!showThread ? (
          <RecruitingChatSection
            slug={slug}
            envelope={envelope}
            error={
              error && error !== "forbidden" && error !== "not_found"
                ? "通信に失敗しました。"
                : null
            }
            onReload={() => window.location.reload()}
            onUpdated={(next: RecruitingChat) => {
              applyEnvelope({
                ok: true,
                recruiting_chat: next,
                can_create: false,
                can_manage: canManage || next.can_manage,
              });
              if (!next.room_id || !next.can_send) return;
              const roomId = next.room_id;
              const currentSlug = slug;
              setLoading(true);
              void fetchRecruitingRoom(roomId)
                .then((data) => {
                  if (slugRef.current !== currentSlug) return;
                  roomIdRef.current = data.room.id;
                  setRoom(data.room);
                  setMessages(data.messages || []);
                  setHasMore(Boolean(data.has_more));
                  setNextBefore(
                    data.next_before != null ? Number(data.next_before) : null
                  );
                  latestIdRef.current = data.room.latest_id || 0;
                  setAccessLost(false);
                })
                .catch((err) => {
                  if (slugRef.current !== currentSlug) return;
                  clearThread();
                  if (isAccessLost(err)) setAccessLost(true);
                })
                .finally(() => {
                  if (slugRef.current === currentSlug) setLoading(false);
                });
            }}
          />
        ) : (
          <>
            {chat?.can_leave ? (
              <p className="org-recruiting-room__leave">
                <button
                  type="button"
                  className="btn btn-secondary"
                  disabled={leaveBusy}
                  onClick={() => void onLeave()}
                >
                  {leaveBusy ? "退出中…" : "退出する"}
                </button>
              </p>
            ) : null}
            <section className="chat-panel" aria-label="新歓チャット">
              <h2>メッセージ</h2>
              <p className="chat-hint">
                団体の新歓チャットです（15秒ごとに自動更新）
              </p>
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
                        kind="recruiting"
                        message={m}
                        canAct
                        canReply={canSend}
                        highlightedId={highlightId}
                        onReply={setReplyingTo}
                        onDelete={async (id) => {
                          const roomId = roomIdRef.current;
                          if (roomId == null) return;
                          const updated = await deleteRecruitingMessage(
                            roomId,
                            id
                          );
                          if (roomIdRef.current !== roomId) return;
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
                    allowMedia={false}
                    placeholder={replyingTo ? "返信を入力…" : "メッセージを入力..."}
                  />
                </>
              ) : (
                <p className="dm-group-invite-locked">
                  メッセージを送信できません。
                </p>
              )}
            </section>
          </>
        )}
      </main>
      {toast ? <div className="chat-toast">{toast}</div> : null}
    </div>
  );
}
