import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { BookmarkButton } from "../../components/BookmarkButton";
import { SfIcon } from "../../components/SfIcon";
import type { TimelinePost } from "./api";
import {
  addComment,
  deleteComment,
  deletePost,
  toggleBookmark,
  toggleLike,
} from "./api";
import { saveScrollPosition } from "../profile/api";

type Props = {
  post: TimelinePost;
  authenticated: boolean;
  onChange: (post: TimelinePost) => void;
  onRemove: (postId: number) => void;
  onQuote: (post: TimelinePost) => void;
  onRequireLogin: () => void;
};

function formatRelative(iso: string): string {
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return "";
  const sec = Math.max(0, Math.floor((Date.now() - t) / 1000));
  if (sec < 60) return "数秒";
  if (sec < 3600) return `${Math.floor(sec / 60)}分`;
  if (sec < 86400) return `${Math.floor(sec / 3600)}時間`;
  if (sec < 86400 * 30) return `${Math.floor(sec / 86400)}日`;
  return new Date(iso).toLocaleDateString("ja-JP");
}

function linkifyMentions(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(
      /@([a-zA-Z0-9_]{3,30})/g,
      '<span class="mention-link">@$1</span>'
    );
}

function formatCount(n: number): string {
  if (!n) return "";
  if (n < 1000) return String(n);
  if (n < 10000) return `${(n / 1000).toFixed(1).replace(/\.0$/, "")}千`;
  return `${Math.floor(n / 1000)}千`;
}

export function TimelinePostCard({
  post,
  authenticated,
  onChange,
  onRemove,
  onQuote,
  onRequireLogin,
}: Props) {
  const [commentsOpen, setCommentsOpen] = useState(false);
  const [commentBody, setCommentBody] = useState("");
  const [busy, setBusy] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement | null>(null);
  const bodyHtml = useMemo(() => linkifyMentions(post.body), [post.body]);

  useEffect(() => {
    if (!menuOpen) return;
    const onPointer = (e: MouseEvent) => {
      if (!menuRef.current?.contains(e.target as Node)) {
        setMenuOpen(false);
      }
    };
    document.addEventListener("mousedown", onPointer);
    return () => document.removeEventListener("mousedown", onPointer);
  }, [menuOpen]);

  const guard = (fn: () => void) => {
    if (!authenticated) {
      onRequireLogin();
      return;
    }
    fn();
  };

  const run = async (fn: () => Promise<void>) => {
    if (busy) return;
    setBusy(true);
    try {
      await fn();
    } catch (err) {
      window.alert(err instanceof Error ? err.message : "操作に失敗しました");
    } finally {
      setBusy(false);
    }
  };

  return (
    <article id={`post-${post.id}`} className="tweet-card" data-spa-post={post.id}>
      <div className="tweet-layout">
        {post.author ? (
          <Link
            className="tweet-avatar"
            to={`/users/${post.author.id}/posts`}
            aria-hidden="true"
            onClick={() => saveScrollPosition("/")}
          >
            {post.author.avatar_url ? (
              <img
                className="user-avatar--image tweet-avatar__img"
                src={post.author.avatar_url}
                alt=""
              />
            ) : (
              post.author.initial
            )}
          </Link>
        ) : (
          <span className="tweet-avatar tweet-avatar--deleted" aria-hidden="true">
            退
          </span>
        )}

        <div className="tweet-main">
          <header className="tweet-header">
            <div className="tweet-identity">
              {post.author ? (
                <>
                  <Link
                    className="tweet-author"
                    to={`/users/${post.author.id}/posts`}
                    onClick={() => saveScrollPosition("/")}
                  >
                    {post.author.display_name}
                  </Link>
                  <Link
                    className="tweet-handle"
                    to={`/users/${post.author.id}/posts`}
                    onClick={() => saveScrollPosition("/")}
                  >
                    @{post.author.username}
                  </Link>
                </>
              ) : (
                <span className="tweet-author tweet-author--deleted">削除済みユーザー</span>
              )}
              <span className="tweet-meta-dot" aria-hidden="true">
                ·
              </span>
              <time className="tweet-time" dateTime={post.created_at}>
                {formatRelative(post.created_at)}
              </time>
            </div>
            <div className="tweet-header-menu">
              {authenticated && post.can_delete ? (
                <button
                  type="button"
                  className="tweet-menu-btn tweet-menu-btn--danger"
                  disabled={busy}
                  onClick={() =>
                    guard(() => {
                      if (!window.confirm("この投稿を削除しますか？")) return;
                      void run(async () => {
                        await deletePost(post.id);
                        onRemove(post.id);
                      });
                    })
                  }
                >
                  削除
                </button>
              ) : null}
              <BookmarkButton
                bookmarked={post.user_has_bookmarked}
                disabled={busy}
                onClick={() =>
                  guard(() => {
                    void run(async () => {
                      const bookmarked = await toggleBookmark(post.id);
                      onChange({ ...post, user_has_bookmarked: bookmarked });
                    });
                  })
                }
              />
              {!(authenticated && post.can_delete) ? (
                <div className="tweet-overflow" ref={menuRef}>
                  <button
                    type="button"
                    className="tweet-menu-btn tweet-menu-btn--icon"
                    aria-label="その他"
                    aria-expanded={menuOpen}
                    aria-haspopup="menu"
                    onClick={() => setMenuOpen((v) => !v)}
                  >
                    <SfIcon name="ellipsis" />
                  </button>
                  {menuOpen ? (
                    <div className="tweet-overflow-menu" role="menu">
                      <a
                        className="tweet-overflow-item"
                        role="menuitem"
                        href={`/report/post/${post.id}/`}
                        onClick={() => setMenuOpen(false)}
                      >
                        <SfIcon name="flag" />
                        通報
                      </a>
                    </div>
                  ) : null}
                </div>
              ) : null}
            </div>
          </header>

          {(post.course_name || post.faculty || post.professor_name) && (
            <div className="tweet-tags">
              {post.course_name ? (
                <span className="course-tag">{post.course_name}</span>
              ) : null}
              {post.faculty ? (
                <span className="tag tag-faculty">{post.faculty}</span>
              ) : null}
              {post.professor_name ? (
                <span className="tweet-professor">
                  教授: {post.professor_name}先生
                </span>
              ) : null}
            </div>
          )}

          <div
            className="tweet-body"
            dangerouslySetInnerHTML={{ __html: bodyHtml }}
          />

          {post.quoted_post ? (
            <div className="quoted-post-card">
              {post.quoted_post.is_removed ? (
                <p className="tweet-body">この投稿は削除されました</p>
              ) : (
                <>
                  <div className="tweet-identity">
                    {post.quoted_post.author ? (
                      <span className="tweet-author">
                        {post.quoted_post.author.display_name}
                      </span>
                    ) : null}
                  </div>
                  <div className="tweet-body">{post.quoted_post.body}</div>
                </>
              )}
            </div>
          ) : null}

          {post.image_url ? (
            <a
              className="tweet-media"
              href={post.image_url}
              target="_blank"
              rel="noopener noreferrer"
            >
              <img className="tweet-image" src={post.image_url} alt="" loading="lazy" />
            </a>
          ) : null}

          <div className="tweet-actionbar" role="group" aria-label="投稿アクション">
            <button
              type="button"
              className="tweet-action tweet-action--comment"
              aria-label={`コメント ${post.comment_count}`}
              aria-expanded={commentsOpen}
              onClick={() => setCommentsOpen((v) => !v)}
            >
              <SfIcon name="bubble_left" />
              <span className="tweet-action-count">
                {formatCount(post.comment_count)}
              </span>
            </button>
            <button
              type="button"
              className="tweet-action tweet-action--quote"
              aria-label={`リポスト ${post.quote_count || 0}`}
              disabled={busy}
              onClick={() => guard(() => onQuote(post))}
            >
              <SfIcon name="arrow_2_squarepath" />
              <span className="tweet-action-count">
                {formatCount(post.quote_count || 0)}
              </span>
            </button>
            <button
              type="button"
              className={`tweet-action tweet-action--like${
                post.user_has_liked ? " is-liked" : ""
              }`}
              aria-label={`いいね ${post.like_count}`}
              aria-pressed={post.user_has_liked}
              disabled={busy}
              onClick={() =>
                guard(() => {
                  void run(async () => {
                    const { liked, like_count } = await toggleLike(post.id);
                    onChange({
                      ...post,
                      user_has_liked: liked,
                      like_count,
                    });
                  });
                })
              }
            >
              <SfIcon name={post.user_has_liked ? "heart_fill" : "heart"} />
              <span className="tweet-action-count">
                {formatCount(post.like_count)}
              </span>
            </button>
            <span
              className="tweet-action tweet-action--view tweet-action--static"
              aria-label={`閲覧数 ${post.view_count || 0}`}
            >
              <SfIcon name="chart_bar" />
              <span className="tweet-action-count">
                {formatCount(post.view_count || 0)}
              </span>
            </span>
          </div>

          {commentsOpen ? (
            <div className="tweet-comments">
              <ul className="tweet-comment-list">
                {post.comments.map((c) => (
                  <li key={c.id} className="tweet-comment">
                    <div className="tweet-comment__meta">
                      {c.author ? c.author.display_name : "削除済み"} ·{" "}
                      {formatRelative(c.created_at)}
                      {c.can_delete ? (
                        <button
                          type="button"
                          className="tweet-menu-btn tweet-menu-btn--danger"
                          disabled={busy}
                          onClick={() =>
                            void run(async () => {
                              const comment_count = await deleteComment(c.id);
                              onChange({
                                ...post,
                                comments: post.comments.filter((x) => x.id !== c.id),
                                comment_count,
                              });
                            })
                          }
                        >
                          削除
                        </button>
                      ) : null}
                    </div>
                    <div className="tweet-comment__body">{c.body}</div>
                  </li>
                ))}
              </ul>
              {authenticated ? (
                <form
                  className="tweet-comment-form"
                  onSubmit={(e) => {
                    e.preventDefault();
                    const body = commentBody.trim();
                    if (!body) return;
                    void run(async () => {
                      const { comment, comment_count } = await addComment(
                        post.id,
                        body
                      );
                      onChange({
                        ...post,
                        comments: [...post.comments, comment],
                        comment_count,
                      });
                      setCommentBody("");
                    });
                  }}
                >
                  <input
                    type="text"
                    value={commentBody}
                    onChange={(e) => setCommentBody(e.target.value)}
                    placeholder="コメントを入力..."
                    maxLength={500}
                  />
                  <button type="submit" disabled={busy || !commentBody.trim()}>
                    送信
                  </button>
                </form>
              ) : (
                <p className="spa-placeholder__note">
                  コメントにはログインが必要です。
                </p>
              )}
            </div>
          ) : null}
        </div>
      </div>
    </article>
  );
}
