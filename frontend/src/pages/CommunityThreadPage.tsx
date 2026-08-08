import { useCallback, useEffect, useState, type FormEvent } from "react";
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

export function CommunityThreadPage() {
  const { slug = "", threadPk = "" } = useParams();
  const pk = Number(threadPk);
  const { me } = useSession();
  const navigate = useNavigate();

  const [thread, setThread] = useState<ThreadDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [replyBody, setReplyBody] = useState("");
  const [busy, setBusy] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editBody, setEditBody] = useState("");

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

  const onReply = async (e: FormEvent) => {
    e.preventDefault();
    if (!me?.authenticated) {
      requireLogin();
      return;
    }
    if (!thread) return;
    setBusy(true);
    try {
      const reply = await createReply(slug, pk, replyBody.trim());
      setThread({
        ...thread,
        replies: [...thread.replies, reply],
        visible_reply_count: thread.visible_reply_count + 1,
      });
      setReplyBody("");
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
    if (!window.confirm("この返信を削除しますか？")) return;
    setBusy(true);
    try {
      await deleteReply(slug, pk, reply.id);
      setThread({
        ...thread,
        replies: thread.replies.map((r) =>
          r.id === reply.id
            ? { ...r, is_removed: true, body: "", can_delete: false, can_edit: false }
            : r
        ),
        visible_reply_count: Math.max(0, thread.visible_reply_count - 1),
      });
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
    <div data-spa-page="コミュニティ">
      <Link className="community-back" to="/communities">
        ← コミュニティ
      </Link>

      <article className="thread-detail">
        <span className="thread-card__board">{thread.community.name}</span>
        <h2>{thread.title}</h2>
        <p className="thread-card__meta">
          {thread.author?.display_name || "ユーザー"} ·{" "}
          {formatTime(thread.created_at)} · 返信 {thread.visible_reply_count}
        </p>
        <div className="thread-detail__body">{thread.body}</div>
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

      <ul className="reply-list">
        {thread.replies.map((reply) => (
          <li
            key={reply.id}
            id={`reply-${reply.id}`}
            className={`reply-card${reply.is_removed ? " is-removed" : ""}`}
          >
            {reply.is_removed ? (
              <p>この返信は削除されました</p>
            ) : (
              <>
                <div className="reply-card__meta">
                  {reply.author?.display_name || "ユーザー"} ·{" "}
                  {formatTime(reply.created_at)}
                </div>
                {editingId === reply.id ? (
                  <div>
                    <textarea
                      value={editBody}
                      onChange={(e) => setEditBody(e.target.value)}
                      rows={4}
                      maxLength={2000}
                      style={{ width: "100%", fontFamily: "inherit" }}
                    />
                    <div className="reply-card__actions">
                      <button
                        type="button"
                        disabled={busy}
                        onClick={() => void onSaveEdit(reply)}
                      >
                        保存
                      </button>
                      <button type="button" onClick={() => setEditingId(null)}>
                        キャンセル
                      </button>
                    </div>
                  </div>
                ) : (
                  <>
                    <div className="reply-card__body">{reply.body}</div>
                    <div className="reply-card__actions">
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
              </>
            )}
          </li>
        ))}
      </ul>

      {me?.authenticated ? (
        <form className="community-reply-form" onSubmit={onReply}>
          <textarea
            value={replyBody}
            onChange={(e) => setReplyBody(e.target.value)}
            rows={4}
            maxLength={2000}
            placeholder="返信を入力してください"
            required
          />
          <button type="submit" disabled={busy || !replyBody.trim()}>
            返信する
          </button>
        </form>
      ) : (
        <p className="feed-scope-hint" style={{ margin: 16 }}>
          返信するには
          <Link to={spaLoginPath(`/app/communities/${slug}/threads/${pk}`)}>
            ログイン
          </Link>
          してください。
        </p>
      )}
    </div>
  );
}
