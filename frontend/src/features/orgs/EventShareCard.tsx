import { Link } from "react-router-dom";
import {
  formatTokyoDateTime,
  parseOrganizationEventShareCard,
  type OrganizationEventShareCard,
} from "./orgEvents";

export function EventShareCard({
  share,
}: {
  share: OrganizationEventShareCard | unknown;
}) {
  const parsed =
    share && typeof share === "object" && "type" in share && share.type === "org_event"
      ? parseOrganizationEventShareCard(share)
      : parseOrganizationEventShareCard(share);
  if (!parsed || !parsed.content || !parsed.available) {
    return <div className="share-card share-card--unavailable">イベントを表示できません</div>;
  }
  const content = parsed.content;
  const to =
    content.path ||
    (content.organization_slug && content.event_id
      ? `/organizations/${content.organization_slug}/events/${content.event_id}`
      : "/dm");
  return (
    <Link className="share-card share-card--event" to={to}>
      <p className="share-card__brand">イベント</p>
      <p className="share-card__title">{content.title || "イベント"}</p>
      {content.starts_at ? (
        <p className="share-card__body">{formatTokyoDateTime(content.starts_at)}</p>
      ) : null}
      {content.venue_name ? (
        <p className="share-card__body">{content.venue_name}</p>
      ) : null}
      {content.status_label ? (
        <p className="share-card__meta">{content.status_label}</p>
      ) : null}
      <span className="share-card__cta">イベントを見る</span>
    </Link>
  );
}
