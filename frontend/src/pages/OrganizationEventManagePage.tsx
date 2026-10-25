import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { Link, Navigate, useParams } from "react-router-dom";
import { ListRowSkeleton } from "../components/skeleton";
import { spaLoginPath } from "../features/auth/api";
import { OrganizationRequestError } from "../features/orgs/api";
import {
  canShowEventManage,
  eventCapacityLabel,
  eventStatusLabel,
  formatTokyoDateTime,
  organizationEventErrorMessage,
  organizationEventNewPath,
  organizationEventPath,
  type OrganizationEvent,
} from "../features/orgs/orgEvents";
import { fetchOrganizationEvents } from "../features/orgs/orgEventsApi";
import { isBrowsePreview, useSession } from "../lib/session";
import {
  isLatestRequest,
  isSameUserScope,
  nextRequestId,
} from "../lib/userScopedResult";

export function OrganizationEventManagePage() {
  const { slug } = useParams();
  const { me, loading: sessionLoading } = useSession();
  const browsePreview = isBrowsePreview(me);
  const sessionUserId =
    me?.authenticated && me.user?.id != null ? me.user.id : null;
  const userIdRef = useRef(sessionUserId);
  userIdRef.current = sessionUserId;
  const fetchGen = useRef(0);
  const [events, setEvents] = useState<OrganizationEvent[]>([]);
  const [canManage, setCanManage] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [hasMore, setHasMore] = useState(false);
  const [nextOffset, setNextOffset] = useState(0);

  useLayoutEffect(() => {
    nextRequestId(fetchGen);
    setEvents([]);
    setCanManage(false);
    setError(null);
    setLoading(true);
  }, [slug, sessionUserId]);

  const load = useCallback(
    async (offset = 0) => {
      if (!slug) return;
      const gen = nextRequestId(fetchGen);
      const startedUserId = userIdRef.current;
      if (offset === 0) setLoading(true);
      setError(null);
      try {
        const payload = await fetchOrganizationEvents(slug, {
          manage: true,
          offset,
        });
        if (!isLatestRequest(fetchGen, gen)) return;
        if (!isSameUserScope(startedUserId, userIdRef.current)) return;
        setCanManage(payload.can_manage);
        setEvents((prev) => (offset === 0 ? payload.events : [...prev, ...payload.events]));
        setHasMore(payload.has_more);
        setNextOffset(payload.next_offset);
      } catch (err) {
        if (!isLatestRequest(fetchGen, gen)) return;
        if (!isSameUserScope(startedUserId, userIdRef.current)) return;
        setCanManage(false);
        setEvents([]);
        setError(err instanceof OrganizationRequestError ? err.code : "load_failed");
      } finally {
        if (isLatestRequest(fetchGen, gen)) setLoading(false);
      }
    },
    [slug]
  );

  useEffect(() => {
    if (sessionLoading || browsePreview) return;
    void load(0);
  }, [browsePreview, load, sessionLoading, sessionUserId]);

  if (!slug) return <Navigate to="/" replace />;
  if (browsePreview || (!sessionLoading && !me?.authenticated)) {
    return (
      <div className="org-edit-page" data-spa-page="イベント管理">
        <div className="main-inner">
          <p>イベント管理にはログインが必要です。</p>
          <Link
            className="btn btn-primary"
            to={spaLoginPath(`/app/organizations/${slug}/events/manage`)}
          >
            ログイン
          </Link>
        </div>
      </div>
    );
  }

  const showManage = canShowEventManage({
    hydrated: !loading && !sessionLoading,
    canManage,
  });

  return (
    <div className="org-edit-page" data-spa-page="イベント管理">
      <div className="main-inner">
        {loading || sessionLoading ? (
          <ListRowSkeleton rows={5} />
        ) : error === "forbidden" || error === "not_found" || (!showManage && !error) ? (
          <p>このページは団体の管理者だけが利用できます。</p>
        ) : error ? (
          <>
            <p role="alert">
              {organizationEventErrorMessage(error, "通信に失敗しました。")}
            </p>
            <button type="button" className="btn btn-secondary" onClick={() => void load(0)}>
              再試行
            </button>
          </>
        ) : (
          <section className="org-recruiting-card" aria-label="イベント管理">
            <h1 className="org-recruiting-card__title">イベント管理</h1>
            <p className="org-recruiting-card__actions">
              <Link className="btn btn-primary" to={organizationEventNewPath(slug)}>
                イベントを作成
              </Link>
            </p>
            {events.length === 0 ? (
              <p className="org-profile-empty">イベントはまだありません。</p>
            ) : (
              <ul className="org-event-list">
                {events.map((event) => (
                  <li key={event.id}>
                    <Link className="org-event-row" to={organizationEventPath(slug, event.id)}>
                      <span className="org-event-row__title">{event.title}</span>
                      <span className="org-event-row__meta">
                        {formatTokyoDateTime(event.starts_at)} · {eventStatusLabel(event)} ·{" "}
                        {eventCapacityLabel(event)}
                      </span>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
            {hasMore ? (
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => void load(nextOffset)}
              >
                さらに表示
              </button>
            ) : null}
          </section>
        )}
      </div>
    </div>
  );
}
