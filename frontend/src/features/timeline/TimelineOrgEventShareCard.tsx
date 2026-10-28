import { Link } from "react-router-dom";
import { formatTokyoDateTime } from "../orgs/orgEvents";
import type { SharedOrganizationEvent } from "./api";

export function TimelineOrgEventShareCard({
  event,
}: {
  event: SharedOrganizationEvent;
}) {
  const to =
    event.path ||
    (event.organization_slug && event.id
      ? `/organizations/${event.organization_slug}/events/${event.id}`
      : "/");
  return (
    <Link
      className="share-card share-card--event timeline-org-event-share"
      to={to}
      aria-label={`イベント ${event.title}`}
    >
      <p className="share-card__brand">イベント</p>
      <p className="share-card__title">{event.title}</p>
      {event.starts_at ? (
        <p className="share-card__body">{formatTokyoDateTime(event.starts_at)}</p>
      ) : null}
      {event.venue_name ? (
        <p className="share-card__body">{event.venue_name}</p>
      ) : null}
      {event.status_label ? (
        <p className="share-card__meta">{event.status_label}</p>
      ) : null}
      <span className="share-card__cta">イベントを見る</span>
    </Link>
  );
}
