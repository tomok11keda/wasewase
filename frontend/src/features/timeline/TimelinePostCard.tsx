import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { BookmarkButton } from "../../components/BookmarkButton";
import { SfIcon } from "../../components/SfIcon";
import type { TimelineAuthor, TimelineComment, TimelinePost } from "./api";
import {
  addComment,
  deleteComment,
  deletePost,
  REPORT_REASONS,
  submitContentReport,
  toggleBookmark,
  toggleLike,
} from "./api";
import { ImageLightbox } from "./ImageLightbox";
import { TimelineFleaShareCard } from "./TimelineFleaShareCard";
import { LikerListModal } from "./LikerListModal";
import { ShareActionSheet } from "../../components/ShareActionSheet";
import { timelineSharePayload } from "../../lib/share";
import {
  hasRecordedImpression,
  IMPRESSION_DWELL_MS,
  queueImpression,
} from "./impressions";
import {
  isQuotedPostInnerIgnoreTarget,
  isTimelinePostDetailIgnoreTarget,
  quotedPostDetailState,
  timelinePostDetailState,
} from "./postAnchor";
import { saveScrollPosition } from "../profile/api";
import { analytics } from "../../lib/analytics/events";
import { MOTION_FAST_MS } from "../../lib/motion";
import {
  COMMENT_FLASH_MS,
  canJumpToReplyParent,
  groupTimelineComments,
  insertThreadedComment,
  replyToLabel,
  timelineCommentDomId,
} from "./commentThread";

type TimelinePostCardVariant = "feed" | "detail";

type Props = {
  post: TimelinePost;
  authenticated: boolean;
  onChange: (post: TimelinePost) => void;
  onRemove: (postId: number) => void;
  onQuote: (post: TimelinePost) => void;
  onRequireLogin: () => void;
  variant?: TimelinePostCardVariant;
  focusComposer?: boolean;
  commentsPending?: boolean;
  composerUser?: { avatar_url: string; initial: string } | null;
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

function ThreadAvatar({
  author,
  className,
}: {
  author: TimelineAuthor;
  className: string;
}) {
  if (author) {
    return (
      <Link
        className={className}
        to={`/users/${author.id}/posts`}
        aria-hidden="true"
        onClick={() => saveScrollPosition("/")}
      >
        {author.avatar_url ? (
          <img
            className="user-avatar--image tweet-avatar__img"
            src={author.avatar_url}
            alt=""
          />
        ) : (
          author.initial
        )}
      </Link>
    );
  }
  return (
    <span className={`${className} tweet-avatar--deleted`} aria-hidden="true">
      退
    </span>
  );
}

type ReplyTarget = {
  id: number;
  username: string;
  display_name: string;
};

function TimelineCommentBody({
  comment,
  busy,
  onJumpToParent,
  onReply,
  onDelete,
}: {
  comment: TimelineComment;
  busy: boolean;
  onJumpToParent: (comment: TimelineComment) => void;
  onReply: (comment: TimelineComment) => void;
  onDelete: (comment: TimelineComment) => void;
}) {
  const label = replyToLabel(comment);
  const canJump = canJumpToReplyParent(comment);
  return (
    <>
      <div className="tweet-avatar-col">
        <ThreadAvatar
          author={comment.author}
          className="tweet-avatar tweet-comment__avatar"
        />
      </div>
      <div className="tweet-comment__content">
        <div className="tweet-comment__identity">
          {comment.author ? (
            <>
              <Link
                className="tweet-comment__name"
                to={`/users/${comment.author.id}/posts`}
                onClick={() => saveScrollPosition("/")}
              >
                {comment.author.display_name}
              </Link>
              <Link
                className="tweet-comment__handle"
                to={`/users/${comment.author.id}/posts`}
                onClick={() => saveScrollPosition("/")}
              >
                @{comment.author.username}
              </Link>
            </>
          ) : (
            <span className="tweet-comment__name tweet-comment__name--deleted">
              削除済みユーザー
            </span>
          )}
          <span className="tweet-meta-dot" aria-hidden="true">
            ·
          </span>
          <time className="tweet-comment__time" dateTime={comment.created_at}>
            {formatRelative(comment.created_at)}
          </time>
        </div>
        {label ? (
          <button
            type="button"
            className={`tweet-comment__reply-to${
              canJump ? "" : " is-unavailable"
            }`}
            disabled={!canJump}
            onClick={(event) => {
              event.preventDefault();
              event.stopPropagation();
              if (canJump) onJumpToParent(comment);
            }}
          >
            {label}
          </button>
        ) : null}
        <div className="tweet-comment__body">{comment.body}</div>
        <div
          className="tweet-comment__actions"
          role="group"
          aria-label="返信アクション"
        >
          {!comment.is_deleted ? (
            <button
              type="button"
              className="tweet-action tweet-action--comment"
              aria-label="返信"
              onClick={(event) => {
                event.stopPropagation();
                onReply(comment);
              }}
            >
              <SfIcon name="bubble_left" size={16} />
              {comment.reply_count ? (
                <span className="tweet-action-count">
                  {formatCount(comment.reply_count)}
                </span>
              ) : null}
            </button>
          ) : null}
          {comment.can_delete ? (
            <button
              type="button"
              className="tweet-action tweet-action--delete"
              disabled={busy}
              aria-label="削除"
              onClick={(event) => {
                event.stopPropagation();
                onDelete(comment);
              }}
            >
              削除
            </button>
          ) : null}
        </div>
      </div>
    </>
  );
}

export function TimelinePostCard({
  post,
  authenticated,
  onChange,
  onRemove,
  onQuote,
  onRequireLogin,
  variant = "feed",
  focusComposer = false,
  commentsPending = false,
  composerUser = null,
}: Props) {
  const navigate = useNavigate();
  const [commentBody, setCommentBody] = useState("");
  const [replyTarget, setReplyTarget] = useState<ReplyTarget | null>(null);
  const [busy, setBusy] = useState(false);
  const [likersOpen, setLikersOpen] = useState(false);
  const [likePopping, setLikePopping] = useState(false);
  const [shareOpen, setShareOpen] = useState(false);
  const [lightboxOpen, setLightboxOpen] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [reportChoosing, setReportChoosing] = useState(false);
  const menuRef = useRef<HTMLDivElement | null>(null);
  const likePopTimerRef = useRef(0);
  const articleRef = useRef<HTMLElement | null>(null);
  const composerRef = useRef<HTMLInputElement | null>(null);
  const flashTimerRef = useRef(0);
  const postRef = useRef(post);
  postRef.current = post;
  const bodyHtml = useMemo(() => linkifyMentions(post.body), [post.body]);
  const showComments = variant === "detail";
  const hasThreadLine = showComments && post.comments.length > 0;
  const commentGroups = useMemo(
    () => groupTimelineComments(post.comments),
    [post.comments]
  );

  const focusReplyComposer = (target?: ReplyTarget | null) => {
    if (target !== undefined) {
      setReplyTarget(target);
    }
    const el = composerRef.current;
    if (!el) return;
    el.focus();
    el.scrollIntoView({ block: "nearest" });
  };

  const clearReplyTarget = () => {
    setReplyTarget(null);
  };

  const startReplyToComment = (row: TimelineComment) => {
    guard(() => {
      focusReplyComposer(
        row.author
          ? {
              id: row.id,
              username: row.author.username,
              display_name: row.author.display_name,
            }
          : {
              id: row.id,
              username: "",
              display_name: "削除済みユーザー",
            }
      );
    });
  };

  const deleteOneComment = (row: TimelineComment) => {
    void run(async () => {
      const { comment_count, comment } = await deleteComment(row.id);
      onChange({
        ...post,
        comments: comment
          ? post.comments.map((item) =>
              item.id === comment.id ? comment : item
            )
          : post.comments.filter((item) => item.id !== row.id),
        comment_count,
      });
      if (replyTarget?.id === row.id) {
        clearReplyTarget();
      }
    });
  };

  const scrollToParentComment = (comment: TimelineComment) => {
    if (!canJumpToReplyParent(comment) || !comment.parent_comment_id) return;
    const el = document.getElementById(
      timelineCommentDomId(comment.parent_comment_id)
    );
    if (!el) return;
    const reduceMotion =
      typeof window.matchMedia === "function" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    el.scrollIntoView({
      behavior: reduceMotion ? "auto" : "smooth",
      block: "center",
    });
    el.classList.add("is-flash");
    window.clearTimeout(flashTimerRef.current);
    flashTimerRef.current = window.setTimeout(() => {
      el.classList.remove("is-flash");
    }, COMMENT_FLASH_MS);
  };

  const openDetail = (opts?: { focusComposer?: boolean }) => {
    if (variant === "detail") {
      if (opts?.focusComposer) focusReplyComposer(null);
      return;
    }
    saveScrollPosition("/");
    navigate(`/posts/${post.id}`, {
      state: timelinePostDetailState(post, opts),
    });
  };

  useEffect(() => {
    if (!focusComposer || variant !== "detail") return;
    const timer = window.setTimeout(() => {
      focusReplyComposer();
    }, 50);
    return () => window.clearTimeout(timer);
  }, [focusComposer, variant]);

  useEffect(() => {
    if (!menuOpen) {
      setReportChoosing(false);
      return;
    }
    const onPointer = (e: MouseEvent) => {
      if (!menuRef.current?.contains(e.target as Node)) {
        setMenuOpen(false);
      }
    };
    document.addEventListener("mousedown", onPointer);
    return () => document.removeEventListener("mousedown", onPointer);
  }, [menuOpen]);

  useEffect(() => {
    return () => {
      window.clearTimeout(likePopTimerRef.current);
      window.clearTimeout(flashTimerRef.current);
    };
  }, []);

  // Impression observer (separate from HomePage infinite-scroll sentinel IO)
  useEffect(() => {
    const el = articleRef.current;
    if (!el) return;
    if (hasRecordedImpression(post.id)) return;

    let dwellTimer: number | null = null;
    let intersectingEnough = false;

    const clearDwell = () => {
      if (dwellTimer != null) {
        window.clearTimeout(dwellTimer);
        dwellTimer = null;
      }
    };

    const tryStartDwell = () => {
      if (!intersectingEnough) return;
      if (document.visibilityState !== "visible") return;
      if (hasRecordedImpression(post.id)) return;
      if (dwellTimer != null) return;
      dwellTimer = window.setTimeout(() => {
        dwellTimer = null;
        if (document.visibilityState !== "visible") return;
        if (!intersectingEnough) return;
        queueImpression(post.id, (_id, viewCount) => {
          const current = postRef.current;
          if (current.id !== post.id) return;
          onChange({ ...current, view_count: viewCount });
        });
      }, IMPRESSION_DWELL_MS);
    };

    const obs = new IntersectionObserver(
      (entries) => {
        const entry = entries[0];
        if (!entry) return;
        intersectingEnough =
          entry.isIntersecting && entry.intersectionRatio >= 0.5;
        if (intersectingEnough) {
          tryStartDwell();
        } else {
          clearDwell();
        }
      },
      { threshold: [0, 0.5, 1] }
    );
    obs.observe(el);

    const onVisibility = () => {
      if (document.visibilityState !== "visible") {
        clearDwell();
        return;
      }
      tryStartDwell();
    };
    document.addEventListener("visibilitychange", onVisibility);

    return () => {
      obs.disconnect();
      clearDwell();
      document.removeEventListener("visibilitychange", onVisibility);
    };
    // onChange is read via postRef / stable enough; avoid re-observe on inline parent callbacks
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [post.id]);

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
    <>
    <article
      ref={articleRef}
      id={`post-${post.id}`}
      className={`tweet-card${variant === "feed" ? " tweet-card--openable" : ""}${
        variant === "detail" ? " tweet-card--detail" : ""
      }`}
      data-spa-post={post.id}
      onClick={(event) => {
        if (variant === "detail") return;
        if (isTimelinePostDetailIgnoreTarget(event.target)) return;
        openDetail();
      }}
    >
      <div className={`tweet-layout${variant === "detail" ? " tweet-thread-root" : ""}`}>
        {variant === "detail" ? (
          <div className="tweet-avatar-col">
            <ThreadAvatar author={post.author} className="tweet-avatar" />
            {hasThreadLine ? (
              <span className="tweet-thread-line" aria-hidden="true" />
            ) : null}
          </div>
        ) : (
          <ThreadAvatar author={post.author} className="tweet-avatar" />
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
              {variant !== "detail" ? (
                <>
                  <span className="tweet-meta-dot" aria-hidden="true">
                    ·
                  </span>
                  <Link
                    className="tweet-time tweet-time--detail-link"
                    to={`/posts/${post.id}`}
                    state={timelinePostDetailState(post)}
                    onClick={() => saveScrollPosition("/")}
                    aria-label="投稿の詳細を見る"
                  >
                    <time dateTime={post.created_at}>
                      {formatRelative(post.created_at)}
                    </time>
                  </Link>
                </>
              ) : null}
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
              {variant !== "detail" ? (
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
              ) : null}
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
                      {reportChoosing ? (
                        <>
                          <p className="tweet-overflow-heading">通報理由</p>
                          {REPORT_REASONS.map((reason) => (
                            <button
                              key={reason.value}
                              type="button"
                              className="tweet-overflow-item"
                              role="menuitem"
                              disabled={busy}
                              onClick={() =>
                                guard(() => {
                                  void run(async () => {
                                    const message = await submitContentReport(
                                      "post",
                                      post.id,
                                      reason.value
                                    );
                                    setMenuOpen(false);
                                    setReportChoosing(false);
                                    window.alert(message);
                                  });
                                })
                              }
                            >
                              {reason.label}
                            </button>
                          ))}
                          <button
                            type="button"
                            className="tweet-overflow-item tweet-overflow-item--muted"
                            role="menuitem"
                            onClick={() => setReportChoosing(false)}
                          >
                            戻る
                          </button>
                        </>
                      ) : (
                        <button
                          type="button"
                          className="tweet-overflow-item"
                          role="menuitem"
                          onClick={() =>
                            guard(() => {
                              setReportChoosing(true);
                            })
                          }
                        >
                          <SfIcon name="flag" />
                          通報
                        </button>
                      )}
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
            <div
              className={
                post.quoted_post.is_removed
                  ? "quoted-post-card quoted-post-card--unavailable"
                  : "quoted-post-card"
              }
              onClick={(event) => {
                event.stopPropagation();
                const quoted = post.quoted_post;
                if (!quoted || quoted.is_removed) return;
                if (isQuotedPostInnerIgnoreTarget(event.target)) return;
                saveScrollPosition("/");
                navigate(`/posts/${quoted.id}`, {
                  state: quotedPostDetailState(),
                });
              }}
            >
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

          {post.shared_product ? (
            <TimelineFleaShareCard product={post.shared_product} />
          ) : null}

          {post.image_url ? (
            <button
              type="button"
              className="tweet-media"
              onClick={(event) => {
                event.preventDefault();
                event.stopPropagation();
                setLightboxOpen(true);
              }}
            >
              <img
                className="tweet-image"
                src={post.image_url}
                alt="投稿の画像"
                loading="lazy"
              />
            </button>
          ) : null}

          {variant === "detail" ? (
            <div className="tweet-metadata">
              <time className="tweet-metadata__time" dateTime={post.created_at}>
                {formatRelative(post.created_at)}
              </time>
            </div>
          ) : null}

          <div className="tweet-actionbar" role="group" aria-label="投稿アクション">
            <button
              type="button"
              className="tweet-action tweet-action--comment"
              aria-label={`コメント ${post.comment_count}`}
              aria-expanded={showComments}
              onClick={() => openDetail({ focusComposer: true })}
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
            <div className="tweet-action-cluster">
              <button
                type="button"
                className={`tweet-action tweet-action--like${
                  post.user_has_liked ? " is-liked" : ""
                }${likePopping ? " is-popping" : ""}`}
                aria-label="いいね"
                aria-pressed={post.user_has_liked}
                disabled={busy}
                onClick={() =>
                  guard(() => {
                    void run(async () => {
                      const { liked, like_count } = await toggleLike(post.id);
                      if (liked) {
                        analytics.likeCreated();
                        setLikePopping(true);
                        window.clearTimeout(likePopTimerRef.current);
                        likePopTimerRef.current = window.setTimeout(() => {
                          setLikePopping(false);
                        }, MOTION_FAST_MS + 40);
                      }
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
              </button>
              {post.like_count > 0 ? (
                <button
                  type="button"
                  className={`tweet-action tweet-action--likers${
                    post.user_has_liked ? " is-liked" : ""
                  }`}
                  aria-label={`いいねした人 ${post.like_count}人`}
                  onClick={(event) => {
                    event.stopPropagation();
                    guard(() => setLikersOpen(true));
                  }}
                >
                  <span className="tweet-action-count">
                    {formatCount(post.like_count)}
                  </span>
                </button>
              ) : null}
            </div>
            <span
              className="tweet-action tweet-action--view tweet-action--static"
              aria-label={`閲覧数 ${post.view_count || 0}`}
            >
              <SfIcon name="chart_bar" />
              <span className="tweet-action-count">
                {formatCount(post.view_count || 0)}
              </span>
            </span>
            {variant === "detail" ? (
              <BookmarkButton
                className="tweet-action tweet-action--bookmark"
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
            ) : null}
            <button
              type="button"
              className="tweet-action tweet-action--share"
              aria-label="シェア"
              onClick={(event) => {
                event.stopPropagation();
                event.preventDefault();
                setShareOpen(true);
              }}
            >
              <SfIcon name="square_and_arrow_up" />
            </button>
          </div>
        </div>
      </div>

          {showComments ? (
            <div className="tweet-comments">
              {commentsPending ? (
                <p className="tweet-comments__empty">返信を読み込み中…</p>
              ) : post.comments.length === 0 ? (
                <p className="tweet-comments__empty">まだ返信はありません</p>
              ) : (
                <ul className="tweet-comment-list">
                  {commentGroups.map((group) => (
                    <li
                      key={group.root.id}
                      className="tweet-comment-thread"
                      data-thread-root={group.root.id}
                    >
                      <div
                        id={timelineCommentDomId(group.root.id)}
                        className={`tweet-comment${
                          group.root.is_deleted ? " is-deleted" : ""
                        }`}
                      >
                        <TimelineCommentBody
                          comment={group.root}
                          busy={busy}
                          onJumpToParent={scrollToParentComment}
                          onReply={startReplyToComment}
                          onDelete={deleteOneComment}
                        />
                      </div>
                      {group.replies.length > 0 ? (
                        <ul className="tweet-comment-replies">
                          {group.replies.map((reply) => (
                            <li
                              key={reply.id}
                              id={timelineCommentDomId(reply.id)}
                              className={`tweet-comment is-reply${
                                reply.is_deleted ? " is-deleted" : ""
                              }`}
                            >
                              <TimelineCommentBody
                                comment={reply}
                                busy={busy}
                                onJumpToParent={scrollToParentComment}
                                onReply={startReplyToComment}
                                onDelete={deleteOneComment}
                              />
                            </li>
                          ))}
                        </ul>
                      ) : null}
                    </li>
                  ))}
                </ul>
              )}
              {authenticated ? (
                <form
                  className="tweet-comment-form tweet-comment-form--dock"
                  onSubmit={(e) => {
                    e.preventDefault();
                    const body = commentBody.trim();
                    if (!body) return;
                    void run(async () => {
                      const { comment, comment_count } = await addComment(
                        post.id,
                        body,
                        replyTarget?.id ?? null
                      );
                      analytics.commentCreated();
                      onChange({
                        ...post,
                        comments: insertThreadedComment(post.comments, comment),
                        comment_count,
                      });
                      setCommentBody("");
                      clearReplyTarget();
                    });
                  }}
                >
                  {replyTarget ? (
                    <div className="tweet-comment-form__target">
                      <span>
                        {replyTarget.username
                          ? `@${replyTarget.username} に返信`
                          : `${replyTarget.display_name} に返信`}
                      </span>
                      <button
                        type="button"
                        onClick={clearReplyTarget}
                        aria-label="返信先を解除"
                      >
                        ×
                      </button>
                    </div>
                  ) : null}
                  <div className="tweet-comment-form__row">
                  {composerUser ? (
                    <span className="tweet-comment-form__avatar" aria-hidden="true">
                      {composerUser.avatar_url ? (
                        <img
                          className="user-avatar--image tweet-avatar__img"
                          src={composerUser.avatar_url}
                          alt=""
                        />
                      ) : (
                        composerUser.initial
                      )}
                    </span>
                  ) : null}
                  <input
                    ref={composerRef}
                    type="text"
                    value={commentBody}
                    onChange={(e) => setCommentBody(e.target.value)}
                    placeholder={
                      replyTarget?.username
                        ? `@${replyTarget.username} に返信`
                        : "返信を入力..."
                    }
                    maxLength={500}
                    aria-label="返信を入力"
                  />
                  <button
                    type="submit"
                    className="tweet-comment-form__send"
                    disabled={busy || !commentBody.trim()}
                    aria-label="送信"
                  >
                    <SfIcon name="paperplane" size={16} />
                  </button>
                  </div>
                </form>
              ) : (
                <p className="tweet-comments__empty tweet-comments__login">
                  返信にはログインが必要です。
                </p>
              )}
            </div>
          ) : null}
    </article>
    <LikerListModal
      postId={post.id}
      open={likersOpen}
      onClose={() => setLikersOpen(false)}
    />
    <ShareActionSheet
      open={shareOpen}
      payload={timelineSharePayload(post.id)}
      shareTarget={{ type: "timeline", id: post.id }}
      onClose={() => setShareOpen(false)}
    />
    {post.image_url ? (
      <ImageLightbox
        src={post.image_url}
        alt="投稿の画像"
        open={lightboxOpen}
        onClose={() => setLightboxOpen(false)}
      />
    ) : null}
    </>
  );
}
