import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import { isBrowsePreview, useSession } from "../lib/session";
import {
  COMMUNITY_ANON_HINT,
  createReply,
  deleteReply,
  deleteThread,
  editReply,
  fetchThreadDetail,
  participantLabel,
  type ThreadDetail,
  type ThreadReply,
} from "../features/community/api";
import { CommunityReportMenu } from "../features/community/CommunityReportMenu";
import { spaLoginPath } from "../features/auth/api";
import { BrowsePreviewNotice } from "../components/BrowsePreviewNotice";
import { readInitialThread } from "../features/community/threadNav";

function formatTime(iso: string): string {
  try {
    return new Date(iso).toLocaleString("ja-JP");
  } catch {
    return iso;
  }
}

export function CommunityThreadPage() {
  const { slug = "", threadPk = "" } = useParams();
  const pk = Number(threadPk);
  const { me, loading: sessionLoading } = useSession();
  const browsePreview = isBrowsePreview(me);
  const navigate = useNavigate();
  const location = useLocation();
  const composerRef = useRef<HTMLTextAreaElement | null>(null);

  const [thread, setThread] = useState<ThreadDetail | null>(() =>
    readInitialThread(location.state, pk)
  );
  const [loading, setLoading] = useState(() => !thread);
  const [hydrated, setHydrated] = useState(() => !thread);
  const [error, setError] = useState<string | null>(null);
  const [replyBody, setReplyBody] = useState("");
  const [busy, setBusy] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editBody, setEditBody] = useState("");
  const [replyTarget, setReplyTarget] = useState<ThreadReply | null>(null);

  const mutatedRef = useRef(false);
  const fetchGen = useRef(0);

  useEffect(() => {
    const next = readInitialThread(location.state, pk);
    mutatedRef.current = false;
    fetchGen.current += 1;
    setThread(next);
    setLoading(!next);
    setHydrated(!next);
    setError(null);
  }, [slug, pk, location.key]);

  const load = useCallback(async () => {
    if (!slug || !pk) return;
    const gen = ++fetchGen.current;
    const hadPreview = Boolean(readInitialThread(location.state, pk));
    if (!hadPreview) {
      setLoading(true);
      setError(null);
    }
    try {
      const data = await fetchThreadDetail(slug, pk);
      if (gen !== fetchGen.current) return;
      if (mutatedRef.current) {
        setThread((prev) =>
          prev
            ? {
                ...data,
                replies:
                  prev.replies.length > data.replies.length
                    ? prev.replies
                    : data.replies,
                visible_reply_count: Math.max(
                  prev.visible_reply_count,
                  data.visible_reply_count
                ),
              }
            : data
        );
      } else {
        setThread(data);
      }
      setError(null);
      setHydrated(true);
    } catch (err) {
      if (gen !== fetchGen.current) return;
      if (hadPreview && err instanceof TypeError) {
        setHydrated(true);
        return;
      }
      const message = err instanceof Error ? err.message : "detail_failed";
      setThread(null);
      setError(message);
      setHydrated(true);
    } finally {
      if (gen === fetchGen.current) setLoading(false);
    }
  }, [slug, pk, location.state]);

  useEffect(() => {
    if (sessionLoading) return;
    if (browsePreview) {
      setThread(null);
      setError(null);
      setLoading(false);
      setHydrated(true);
      return;
    }
    void load();
  }, [sessionLoading, browsePreview, load]);

  const requireLogin = () => {
    navigate(spaLoginPath(`/app/communities/${slug}/threads/${pk}`));
  };

  const startReplyTo = (reply: ThreadReply) => {
    if (!me?.authenticated) {
      requireLogin();
      return;
    }
    if (reply.is_removed) return;
    setReplyTarget(reply);
    window.setTimeout(() => composerRef.current?.focus(), 50);
  };

  const clearReplyTarget = () => setReplyTarget(null);

  const scrollToReply = (replyId: number) => {
    const el = document.getElementById(`reply-${replyId}`);
    if (el) {
      el.scrollIntoView({ behavior: "smooth", block: "center" });
      el.classList.add("is-flash");
      window.setTimeout(() => el.classList.remove("is-flash"), 1200);
    }
  };

  const onReply = async (e: FormEvent) => {
    e.preventDefault();
    if (!me?.authenticated) {
      requireLogin();
      return;
    }
    if (!thread) return;
    const body = replyBody.trim();
    if (!body) return;
    setBusy(true);
    try {
      const reply = await createReply(
        slug,
        pk,
        body,
        replyTarget?.id ?? null
      );
      mutatedRef.current = true;
      setThread({
        ...thread,
        replies: [...thread.replies, reply],
        visible_reply_count: thread.visible_reply_count + 1,
      });
      setReplyBody("");
      setReplyTarget(null);
      window.setTimeout(() => scrollToReply(reply.id), 80);
    } catch (err) {
      window.alert(err instanceof Error ? err.message : "返信に失敗しました");
    } finally {
      setBusy(false);
    }
  };

  const onDeleteThread = async () => {
    if (!thread?.can_delete) return;
    if (!window.confirm("このスレッドを削除しますか？")) return;
    setBusy(true);
    try {
      await deleteThread(slug, pk);
      navigate("/communities");
    } catch (err) {
      window.alert(err instanceof Error ? err.message : "削除に失敗しました");
    } finally {
      setBusy(false);
    }
  };

  const onDeleteReply = async (reply: ThreadReply) => {
    if (!reply.can_delete || !thread) return;
    if (!window.confirm("この発言を削除しますか？")) return;
    setBusy(true);
    try {
      await deleteReply(slug, pk, reply.id);
      mutatedRef.current = true;
      setThread({
        ...thread,
        replies: thread.replies.map((r) =>
          r.id === reply.id
            ? {
                ...r,
                is_removed: true,
                body: "",
                can_delete: false,
                can_edit: false,
                can_report: false,
                is_mine: false,
              }
            : r.reply_to?.id === reply.id
              ? {
                  ...r,
                  reply_to: r.reply_to
                    ? { ...r.reply_to, is_unavailable: true }
                    : r.reply_to,
                }
              : r
        ),
        visible_reply_count: Math.max(0, thread.visible_reply_count - 1),
      });
      if (replyTarget?.id === reply.id) setReplyTarget(null);
    } catch (err) {
      window.alert(err instanceof Error ? err.message : "削除に失敗しました");
    } finally {
      setBusy(false);
    }
  };

  const onSaveEdit = async (reply: ThreadReply) => {
    if (!thread) return;
    setBusy(true);
    try {
      const updated = await editReply(slug, pk, reply.id, editBody.trim());
      mutatedRef.current = true;
      setThread({
        ...thread,
        replies: thread.replies.map((r) => (r.id === reply.id ? updated : r)),
      });
      setEditingId(null);
    } catch (err) {
      window.alert(err instanceof Error ? err.message : "更新に失敗しました");
    } finally {
      setBusy(false);
    }
  };

  if (browsePreview) {
    return (
      <div data-spa-page="コミュニティ" className="community-thread-page">
        <BrowsePreviewNotice
          nextPath={`/app/communities/${slug}/threads/${threadPk}`}
        >
          スレッドはログイン後に表示されます。
        </BrowsePreviewNotice>
      </div>
    );
  }

  if (loading) {
    return (
      <div data-spa-page="コミュニティ" className="community-thread-page">
        <p className="empty-message">読み込み中…</p>
      </div>
    );
  }
  if (error || !thread) {
    return (
      <div data-spa-page="コミュニティ" className="community-thread-page">
        <p className="empty-message">スレッドを表示できません（{error}）</p>
      </div>
    );
  }

  return (
    <div data-spa-page="コミュニティ" className="community-thread-page">
      <p className="community-anon-hint">
        {thread.anonymous_hint || COMMUNITY_ANON_HINT}
      </p>

      <article className="thread-detail forum-op">
        <span className="thread-card__board">{thread.community.name}</span>
        <h2>{thread.title}</h2>
        <div className="forum-post forum-post--op">
          <div className="forum-post__main">
            <div className="forum-post__meta">
              <span className="forum-post__author">
                {participantLabel(thread.anonymous_label)}
              </span>
              <span aria-hidden="true">·</span>
              <time dateTime={thread.created_at}>
                {formatTime(thread.created_at)}
              </time>
              <span aria-hidden="true">·</span>
              <span>発言 {thread.visible_reply_count}</span>
              <CommunityReportMenu
                targetType="community_thread"
                targetId={thread.id}
                canReport={Boolean(thread.can_report)}
                ariaLabel="この投稿を通報"
              />
            </div>
            <div className="forum-post__body">{thread.body}</div>
          </div>
        </div>
        {thread.can_delete ? (
          <div className="thread-detail__actions">
            <button
              type="button"
              className="danger"
              disabled={busy}
              onClick={() => void onDeleteThread()}
            >
              スレッドを削除
            </button>
          </div>
        ) : null}
      </article>

      <section className="forum-replies" aria-label="スレッドの発言">
        {!hydrated && thread.replies.length === 0 ? (
          <p className="empty-message">発言を読み込み中…</p>
        ) : null}
        <ul className="reply-list">
          {thread.replies.map((reply) => {
            const isNested = Boolean(reply.reply_to);
            return (
              <li
                key={reply.id}
                id={`reply-${reply.id}`}
                className={`forum-post${isNested ? " is-reply" : ""}${
                  reply.is_removed ? " is-removed" : ""
                }`}
              >
                <span
                  className="forum-post__number"
                  aria-label={`発言番号 ${reply.reply_number ?? ""}`}
                >
                  #{reply.reply_number ?? "—"}
                </span>
                {reply.is_removed ? (
                  <div className="forum-post__main">
                    <p className="forum-post__removed">この発言は削除されました</p>
                  </div>
                ) : (
                  <div className="forum-post__main">
                    <div className="forum-post__meta">
                      <span className="forum-post__author">
                        {participantLabel(reply.anonymous_label, "")}
                      </span>
                      <span aria-hidden="true">·</span>
                      <time dateTime={reply.created_at}>
                        {formatTime(reply.created_at)}
                      </time>
                      <CommunityReportMenu
                        targetType="community_reply"
                        targetId={reply.id}
                        canReport={Boolean(reply.can_report)}
                        ariaLabel="この発言を通報"
                      />
                    </div>
                    {reply.reply_to ? (
                      <button
                        type="button"
                        className={`forum-post__reply-to${
                          reply.reply_to.is_unavailable ? " is-unavailable" : ""
                        }`}
                        onClick={() => {
                          if (!reply.reply_to?.is_unavailable) {
                            scrollToReply(reply.reply_to!.id);
                          }
                        }}
                      >
                        {reply.reply_to.is_unavailable
                          ? "↪ 削除された発言への返信"
                          : `↪ ${participantLabel(
                              reply.reply_to.anonymous_label,
                              "ユーザー"
                            )}`}
                      </button>
                    ) : null}
                    {editingId === reply.id ? (
                      <div>
                        <textarea
                          value={editBody}
                          onChange={(e) => setEditBody(e.target.value)}
                          rows={4}
                          maxLength={2000}
                          className="forum-edit-textarea"
                        />
                        <div className="reply-card__actions">
                          <button
                            type="button"
                            disabled={busy}
                            onClick={() => void onSaveEdit(reply)}
                          >
                            保存
                          </button>
                          <button
                            type="button"
                            onClick={() => setEditingId(null)}
                          >
                            キャンセル
                          </button>
                        </div>
                      </div>
                    ) : (
                      <>
                        <div className="forum-post__body">{reply.body}</div>
                        <div className="reply-card__actions">
                          <button
                            type="button"
                            onClick={() => startReplyTo(reply)}
                          >
                            返信
                          </button>
                          {reply.can_edit ? (
                            <button
                              type="button"
                              onClick={() => {
                                setEditingId(reply.id);
                                setEditBody(reply.body);
                              }}
                            >
                              編集
                            </button>
                          ) : null}
                          {reply.can_delete ? (
                            <button
                              type="button"
                              className="danger"
                              disabled={busy}
                              onClick={() => void onDeleteReply(reply)}
                            >
                              削除
                            </button>
                          ) : null}
                        </div>
                      </>
                    )}
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      </section>

      {me?.authenticated ? (
        <form className="community-reply-form forum-composer" onSubmit={onReply}>
          {replyTarget ? (
            <div className="forum-composer__target">
              <span>
                {participantLabel(replyTarget.anonymous_label, "ユーザー")}
                に返信
              </span>
              <button type="button" onClick={clearReplyTarget} aria-label="キャンセル">
                ×
              </button>
            </div>
          ) : null}
          <textarea
            ref={composerRef}
            value={replyBody}
            onChange={(e) => setReplyBody(e.target.value)}
            rows={4}
            maxLength={2000}
            placeholder={
              replyTarget
                ? "返信を入力してください"
                : "このテーマについて発言する…"
            }
            required
          />
          <button type="submit" disabled={busy || !replyBody.trim()}>
            {replyTarget ? "返信する" : "発言する"}
          </button>
        </form>
      ) : (
        <p className="feed-scope-hint" style={{ margin: 16 }}>
          発言するには
          <Link to={spaLoginPath(`/app/communities/${slug}/threads/${pk}`)}>
            ログイン
          </Link>
          してください。
        </p>
      )}
    </div>
  );
}
