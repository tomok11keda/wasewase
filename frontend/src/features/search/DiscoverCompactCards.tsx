import { Link } from "react-router-dom";
import { AccountDisplayName } from "../../components/VerifiedAccountBadge";
import { VerifiedOrganizationBadge } from "../../components/VerifiedOrganizationBadge";
import type { TimelinePost } from "../timeline/api";
import { organizationPostDisplay } from "../timeline/organizationActor";
import type {
  SearchProductResult,
  SearchThreadResult,
} from "../profile/api";
import { CommunityReportMenu } from "../community/CommunityReportMenu";
import {
  OfficialBadge,
  officialBoardClass,
  shouldShowOfficialBadge,
} from "../community/OfficialBadge";
import { participantLabel } from "../community/api";
import {
  communityThreadDetailState,
  threadSummaryFromSearch,
} from "../community/threadNav";
import {
  productCardFromSearch,
  productDetailState,
} from "../flea/productNav";

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
  const org = organizationPostDisplay(post);
  const name = org?.name || post.author?.display_name || "ユーザー";
  const handle = org
    ? org.kindLabel
    : post.author?.username
      ? `@${post.author.username}`
      : "";
  const avatarUrl = org ? org.avatarUrl : post.author?.avatar_url || "";
  const initial = org ? org.initial : post.author?.initial || "?";
  const preview = (post.body || "").replace(/\s+/g, " ").trim();
  const truncated =
    preview.length > 110 ? `${preview.slice(0, 107)}…` : preview;

  return (
    <Link
      className="discover-compact-card"
      to={{ pathname: "/", hash: `#post-${post.id}` }}
    >
      <div className="discover-compact-card__main">
        <div className="discover-compact-card__head">
          {avatarUrl ? (
            <img
              className="discover-compact-card__avatar"
              src={avatarUrl}
              alt=""
            />
          ) : (
            <span className="discover-compact-card__avatar is-initial">
              {initial}
            </span>
          )}
          <div className="discover-compact-card__who">
            <span className="discover-compact-card__name">
              {org ? (
                <span className="account-verified-name">
                  <span className="account-verified-name__text">{name}</span>
                  <VerifiedOrganizationBadge
                    verified={org.isVerified}
                    compact
                  />
                </span>
              ) : (
                <AccountDisplayName
                  name={name}
                  verified={post.author?.is_operator_verified}
                />
              )}
            </span>
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
  const preview = (thread.body_preview || thread.body || "")
    .replace(/\s+/g, " ")
    .trim();
  const truncated =
    preview.length > 90 ? `${preview.slice(0, 87)}…` : preview;

  return (
    <article className="discover-compact-card-row">
      <Link
        className="discover-compact-card"
        to={`/communities/${thread.community.slug}/threads/${thread.id}`}
        state={communityThreadDetailState(threadSummaryFromSearch(thread))}
      >
        <div className="discover-compact-card__main">
          <div className="discover-compact-card__head">
            <div className="discover-compact-card__who">
              <span className="discover-compact-card__name">
                {participantLabel(thread.anonymous_label)}
              </span>
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
            <span
              className={officialBoardClass(
                "discover-compact-card__board",
                thread.community.is_official
              )}
            >
              {shouldShowOfficialBadge(thread.community.is_official) ? (
                <span className="discover-compact-card__board-name">
                  {thread.community.name}
                </span>
              ) : (
                thread.community.name
              )}
              <OfficialBadge official={thread.community.is_official} />
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
      <CommunityReportMenu
        targetType="community_thread"
        targetId={thread.id}
        canReport={Boolean(thread.can_report)}
        ariaLabel="この投稿を通報"
      />
    </article>
  );
}

/** Compact discovery card for flea products. */
export function DiscoverProductCard({
  product,
  layout = "inline",
}: {
  product: SearchProductResult;
  /** `stack` = portrait image-first card for trending mosaic right column. */
  layout?: "inline" | "stack";
}) {
  const priceLabel = product.is_sold
    ? "売り切れ"
    : product.is_pending
      ? "取引中"
      : `¥${product.price.toLocaleString()}`;

  if (layout === "stack") {
    return (
      <Link
        className="discover-product-stack"
        to={`/flea/products/${product.id}`}
        state={productDetailState(productCardFromSearch(product))}
      >
        <div className="discover-product-stack__media">
          {product.image_url ? (
            <img src={product.image_url} alt="" loading="lazy" />
          ) : (
            <span className="discover-product-stack__empty">No Image</span>
          )}
          {product.is_sold || product.is_pending ? (
            <span className="discover-product-stack__mask" aria-hidden="true" />
          ) : null}
        </div>
        <div className="discover-product-stack__body">
          <strong className="discover-product-stack__title">{product.name}</strong>
          <p className="discover-product-stack__price">{priceLabel}</p>
        </div>
      </Link>
    );
  }

  return (
    <Link
      className="discover-compact-card discover-compact-card--product"
      to={`/flea/products/${product.id}`}
      state={productDetailState(productCardFromSearch(product))}
    >
      <div className="discover-compact-card__thumb is-product">
        {product.image_url ? (
          <img src={product.image_url} alt="" loading="lazy" />
        ) : (
          <span className="discover-compact-card__thumb-empty">No Image</span>
        )}
      </div>
      <div className="discover-compact-card__main">
        <p className="discover-compact-card__badge-row">
          <span className="discover-compact-card__badge is-flea">フリマ</span>
        </p>
        <strong className="discover-compact-card__title">{product.name}</strong>
        <p className="discover-compact-card__price">{priceLabel}</p>
      </div>
    </Link>
  );
}
