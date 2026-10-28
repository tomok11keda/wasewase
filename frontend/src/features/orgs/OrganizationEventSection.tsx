import { Link } from "react-router-dom";
import { ListRowSkeleton } from "../../components/skeleton";
import {
  canShowEventManage,
  eventCapacityLabel,
  eventStatusLabel,
  formatTokyoDateTime,
  organizationEventManagePath,
  organizationEventPath,
  type OrganizationEvent,
} from "./orgEvents";

type Props = {
  slug: string;
  events: OrganizationEvent[];
  loading: boolean;
  error: string | null;
  canManage: boolean;
  hydrated: boolean;
  onRetry: () => void;
};

export function OrganizationEventSection({
  slug,
  events,
  loading,
  error,
  canManage,
  hydrated,
  onRetry,
}: Props) {
  const showManage = canShowEventManage({ hydrated, canManage });
  if (loading && events.length === 0 && !error) {
    return (
      <section className="org-recruiting-card" aria-label="イベント">
        <h2 className="org-recruiting-card__title">イベント</h2>
        <ListRowSkeleton rows={3} />
      </section>
    );
  }
  if (error && events.length === 0) {
    return (
      <section className="org-recruiting-card" aria-label="イベント">
        <h2 className="org-recruiting-card__title">イベント</h2>
        <p className="org-recruiting-card__error">イベントを読み込めませんでした。</p>
        <button type="button" className="btn btn-secondary" onClick={onRetry}>
          再試行
        </button>
      </section>
    );
  }
  if (!showManage && events.length === 0) {
    return null;
  }
  return (
    <section className="org-recruiting-card" aria-label="イベント">
      <h2 className="org-recruiting-card__title">イベント</h2>
      {showManage ? (
        <p className="org-recruiting-card__actions">
          <Link className="btn btn-secondary" to={organizationEventManagePath(slug)}>
            イベント管理
          </Link>
        </p>
      ) : null}
      {events.length === 0 ? (
        <p className="org-profile-empty">公開中のイベントはまだありません。</p>
      ) : (
        <ul className="org-event-list">
          {events.map((event) => (
            <li key={event.id}>
              <Link
                className="org-event-row"
                to={organizationEventPath(slug, event.id)}
              >
                {event.image_url ? (
                  <img
                    className="org-event-row__thumb"
                    src={event.image_url}
                    alt=""
                  />
                ) : null}
                <span className="org-event-row__text">
                  <span className="org-event-row__title">{event.title}</span>
                  <span className="org-event-row__meta">
                    {formatTokyoDateTime(event.starts_at)} · {eventStatusLabel(event)} ·{" "}
                    {eventCapacityLabel(event)}
                  </span>
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
