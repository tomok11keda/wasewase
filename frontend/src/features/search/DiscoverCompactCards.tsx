import { Link } from "react-router-dom";
import type { TimelinePost } from "../timeline/api";
import type { SearchThreadResult } from "../profile/api";

function formatRelative(iso: string): string {
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return "";
  const sec = Math.max(0, Math.floor((Date.now() - t) / 1000));
  if (sec < 60) return "数秒前";
  if (sec < 3600) return `${Math.floor(sec / 60)}分前`;
  if (sec < 86400) return `${Math.floor(sec / 3600)}時間前`;
  if (sec < 86400 * 30) return `${Math.floor(sec / 86400)}日前`;
  return new Date(iso).toLocaleDateString("ja-JP");
}

function formatCount(n: number): string {
  if (!n) return "0";
  if (n < 1000) return String(n);
  return `${(n / 1000).toFixed(n < 10000 ? 1 : 0)}千`;
}

/** Compact discovery card for timeline posts (search empty state only). */
export function DiscoverPostCard({ post }: { post: TimelinePost }) {
  const name = post.author?.display_name || "ユーザー";
  const handle = post.author?.username ? `@${post.author.username}` : "";
  const preview = (post.body || "").replace(/\s+/g, " ").trim();
  const truncated =
    preview.length > 110 ? `${preview.slice(0, 107)}…` : preview;

  return (
    <Link
      className="discover-compact-card"
      to={{ pathname: "/", hash: `post-${post.id}` }}
    >
      <div className="discover-compact-card__main">
        <div className="discover-compact-card__head">
          {post.author?.avatar_url ? (
            <img
              className="discover-compact-card__avatar"
              src={post.author.avatar_url}
              alt=""
            />
          ) : (
            <span className="discover-compact-card__avatar is-initial">
              {post.author?.initial || "?"}
            </span>
          )}
          <div className="discover-compact-card__who">
            <span className="discover-compact-card__name">{name}</span>
            {handle ? (
              <span className="discover-compact-card__handle">{handle}</span>
            ) : null}
          </div>
          <time
            className="discover-compact-card__time"
            dateTime={post.created_at}
          >
            {formatRelative(post.created_at)}
          </time>
        </div>
        <p className="discover-compact-card__badge-row">
          <span className="discover-compact-card__badge">タイムライン</span>
        </p>
        {truncated ? (
          <p className="discover-compact-card__text">{truncated}</p>
        ) : (
          <p className="discover-compact-card__text is-muted">（画像の投稿）</p>
        )}
        <p className="discover-compact-card__stats" aria-label="反応">
          <span>♡ {formatCount(post.like_count)}</span>
          <span>💬 {formatCount(post.comment_count)}</span>
          <span>↻ {formatCount(post.quote_count || 0)}</span>
          {post.view_count > 0 ? (
            <span>👁 {formatCount(post.view_count)}</span>
          ) : null}
        </p>
      </div>
      {post.image_url ? (
        <div className="discover-compact-card__thumb">
          <img src={post.image_url} alt="" loading="lazy" />
        </div>
      ) : null}
    </Link>
  );
}

/** Compact discovery card for community threads. */
export function DiscoverThreadCard({ thread }: { thread: SearchThreadResult }) {
  const name = thread.author?.display_name || "ユーザー";
  const preview = (thread.body_preview || thread.body || "")
    .replace(/\s+/g, " ")
    .trim();
  const truncated =
    preview.length > 90 ? `${preview.slice(0, 87)}…` : preview;

  return (
    <Link
      className="discover-compact-card"
      to={`/communities/${thread.community.slug}/threads/${thread.id}`}
    >
      <div className="discover-compact-card__main">
        <div className="discover-compact-card__head">
          {thread.author?.avatar_url ? (
            <img
              className="discover-compact-card__avatar"
              src={thread.author.avatar_url}
              alt=""
            />
          ) : (
            <span className="discover-compact-card__avatar is-initial">
              {thread.author?.initial || "?"}
            </span>
          )}
          <div className="discover-compact-card__who">
            <span className="discover-compact-card__name">{name}</span>
          </div>
          <time
            className="discover-compact-card__time"
            dateTime={thread.created_at}
          >
            {formatRelative(thread.created_at)}
          </time>
        </div>
        <p className="discover-compact-card__badge-row">
          <span className="discover-compact-card__badge is-community">
            コミュニティ
          </span>
          <span className="discover-compact-card__board">
            {thread.community.name}
          </span>
        </p>
        <strong className="discover-compact-card__title">{thread.title}</strong>
        {truncated ? (
          <p className="discover-compact-card__text">{truncated}</p>
        ) : null}
        <p className="discover-compact-card__stats" aria-label="反応">
          <span>💬 返信 {formatCount(thread.replies_count)}</span>
        </p>
      </div>
    </Link>
  );
}
