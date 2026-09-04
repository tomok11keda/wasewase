import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useSession } from "../lib/session";
import {
  createReply,
  deleteReply,
  deleteThread,
  editReply,
  fetchThreadDetail,
  type ThreadDetail,
  type ThreadReply,
} from "../features/community/api";
import { spaLoginPath } from "../features/auth/api";

function formatTime(iso: string): string {
  try {
    return new Date(iso).toLocaleString("ja-JP");
  } catch {
    return iso;
  }
}

function AuthorAvatar({
  author,
  className,
}: {
  author: NonNullable<ThreadReply["author"]>;
  className: string;
}) {
  return (
    <Link
      className={className}
      to={`/users/${author.id}/posts`}
      aria-hidden="true"
    >
      {author.avatar_url ? (
        <img
          className="user-avatar--image"
          src={author.avatar_url}
          alt=""
        />
      ) : (
        author.initial
      )}
    </Link>
  );
}

export function CommunityThreadPage() {
  const { slug = "", threadPk = "" } = useParams();
  const pk = Number(threadPk);
  const { me } = useSession();
  const navigate = useNavigate();
  const composerRef = useRef<HTMLTextAreaElement | null>(null);

  const [thread, setThread] = useState<ThreadDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [replyBody, setReplyBody] = useState("");
  const [busy, setBusy] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editBody, setEditBody] = useState("");
  const [replyTarget, setReplyTarget] = useState<ThreadReply | null>(null);

  const load = useCallback(async () => {
    if (!slug || !pk) return;
    setLoading(true);
    setError(null);
    try {
      const data = await fetchThreadDetail(slug, pk);
      setThread(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "load_failed");
    } finally {
      setLoading(false);
    }
  }, [slug, pk]);

  useEffect(() => {
    void load();
  }, [load]);

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
      setThread({
        ...thread,
        replies: thread.replies.map((r) =>
          r.id === reply.id
            ? {
                ...r,
                is_removed: true,
                body: "",
                author: null,
                can_delete: false,
                can_edit: false,
              }
            : r.reply_to?.id === reply.id
              ? {
                  ...r,
                  reply_to: r.reply_to
                    ? { ...r.reply_to, is_unavailable: true, display_name: "" }
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

  if (loading) {
    return <p className="empty-message">読み込み中…</p>;
  }
  if (error || !thread) {
    return (
      <div>
        <Link className="community-back" to="/communities">
          ← コミュニティ
        </Link>
        <p className="empty-message">スレッドを表示できません（{error}）</p>
      </div>
    );
  }

  return (
    <div data-spa-page="コミュニティ" className="community-thread-page">
      <Link className="community-back" to="/communities">
        ← コミュニティ
      </Link>

      <article className="thread-detail forum-op">
        <span className="thread-card__board">{thread.community.name}</span>
        <h2>{thread.title}</h2>
        <div className="forum-post forum-post--op">
          {thread.author ? (
            <AuthorAvatar author={thread.author} className="forum-post__avatar" />
          ) : (
            <span className="forum-post__avatar is-deleted" aria-hidden="true">
              退
            </span>
          )}
          <div className="forum-post__main">
            <div className="forum-post__meta">
              {thread.author ? (
                <Link
                  className="forum-post__author"
                  to={`/users/${thread.author.id}/posts`}
                >
                  {thread.author.display_name}
                </Link>
              ) : (
                <span>削除済みユーザー</span>
              )}
              <span aria-hidden="true">·</span>
              <time dateTime={thread.created_at}>
                {formatTime(thread.created_at)}
              </time>
              <span aria-hidden="true">·</span>
              <span>発言 {thread.visible_reply_count}</span>
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
                <span className="forum-post__number" aria-label={`発言番号 ${reply.reply_number ?? ""}`}>
                  #{reply.reply_number ?? "—"}
                </span>
                {reply.is_removed ? (
                  <>
                    <span className="forum-post__avatar is-deleted" aria-hidden="true">
                      —
                    </span>
                    <div className="forum-post__main">
                      <p className="forum-post__removed">この発言は削除されました</p>
                    </div>
                  </>
                ) : (
                  <>
                    {reply.author ? (
                      <AuthorAvatar
                        author={reply.author}
                        className="forum-post__avatar"
                      />
                    ) : (
                      <span
                        className="forum-post__avatar is-deleted"
                        aria-hidden="true"
                      >
                        退
                      </span>
                    )}
                    <div className="forum-post__main">
                      <div className="forum-post__meta">
                        {reply.author ? (
                          <Link
                            className="forum-post__author"
                            to={`/users/${reply.author.id}/posts`}
                          >
                            {reply.author.display_name}
                          </Link>
                        ) : (
                          <span>ユーザー</span>
                        )}
                        <span aria-hidden="true">·</span>
                        <time dateTime={reply.created_at}>
                          {formatTime(reply.created_at)}
                        </time>
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
                            : `↪ ${reply.reply_to.display_name}${
                                reply.reply_to.reply_number
                                  ? ` · #${reply.reply_to.reply_number}`
                                  : ""
                              }`}
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
                  </>
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
                {replyTarget.author?.display_name || "ユーザー"}
                {replyTarget.reply_number
                  ? `（#${replyTarget.reply_number}）`
                  : ""}
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
