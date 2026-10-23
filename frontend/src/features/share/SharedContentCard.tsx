import { Link } from "react-router-dom";
import {
  productCardFromFleaShare,
  productDetailState,
} from "../flea/productNav";
import type {
  FleaShareContent,
  ShareCardPayload,
  TimelineShareContent,
} from "./api";
import { AccountDisplayName } from "../../components/VerifiedAccountBadge";
import { VerifiedOrganizationBadge } from "../../components/VerifiedOrganizationBadge";
import { organizationPostDisplay } from "../timeline/organizationActor";

function yen(price: number): string {
  return `¥${Number(price || 0).toLocaleString("ja-JP")}`;
}

function TimelineShareCard({
  content,
  targetId,
}: {
  content: TimelineShareContent;
  targetId: number;
}) {
  const org = organizationPostDisplay(content);
  const name = org?.name || content.author?.display_name || "わせわせ";
  const handle = org
    ? org.kindLabel
    : content.author?.username
      ? `@${content.author.username}`
      : "";
  const avatarUrl = org ? org.avatarUrl : content.author?.avatar_url || "";
  const initial = org
    ? org.initial
    : content.author?.initial || name.slice(0, 1);
  return (
    <Link className="share-card share-card--timeline" to={`/posts/${targetId}`} state={{ fromWaseWase: true }}>
      <p className="share-card__brand">わせわせ</p>
      <div className="share-card__author">
        <span className="share-card__avatar" aria-hidden="true">
          {avatarUrl ? (
            <img src={avatarUrl} alt="" />
          ) : (
            <span>{initial}</span>
          )}
        </span>
        <span className="share-card__author-text">
          <strong>
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
                verified={content.author?.is_operator_verified}
              />
            )}
          </strong>
          {handle ? <span className="share-card__handle">{handle}</span> : null}
        </span>
      </div>
      {content.body_preview ? (
        <p className="share-card__body">{content.body_preview}</p>
      ) : null}
      {content.image_url ? (
        <img className="share-card__media" src={content.image_url} alt="" />
      ) : null}
      <span className="share-card__cta">投稿を見る →</span>
    </Link>
  );
}

function FleaShareCard({
  content,
  targetId,
}: {
  content: FleaShareContent;
  targetId: number;
}) {
  const seller = content.seller?.display_name || "";
  return (
    <Link
      className="share-card share-card--flea"
      to={`/flea/products/${targetId}`}
      state={productDetailState(productCardFromFleaShare({ ...content, id: targetId }))}
    >
      <p className="share-card__brand">わせわせ フリマ</p>
      {content.image_url ? (
        <img className="share-card__media" src={content.image_url} alt="" />
      ) : null}
      <p className="share-card__title">{content.name}</p>
      <p className="share-card__price">{yen(content.price)}</p>
      {seller ? (
        <p className="share-card__seller">
          <AccountDisplayName
            name={seller}
            verified={content.seller?.is_operator_verified}
          />
        </p>
      ) : null}
      <span className="share-card__cta">商品を見る →</span>
    </Link>
  );
}

export function SharedContentCard({ share }: { share: ShareCardPayload }) {
  if (!share.available || !share.content) {
    const unavailable =
      share.type === "flea"
        ? "この商品は表示できません"
        : "この投稿は表示できません";
    return (
      <div className="share-card share-card--unavailable" role="status">
        {unavailable}
      </div>
    );
  }
  if (share.type === "flea") {
    return (
      <FleaShareCard
        content={share.content as FleaShareContent}
        targetId={share.id}
      />
    );
  }
  return (
    <TimelineShareCard
      content={share.content as TimelineShareContent}
      targetId={share.id}
    />
  );
}
