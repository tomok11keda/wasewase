import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { Link, Navigate, useParams } from "react-router-dom";
import { PeopleListSkeleton } from "../components/skeleton";
import { spaLoginPath } from "../features/auth/api";
import { OrganizationRequestError } from "../features/orgs/api";
import {
  canShowEventManage,
  eventCapacityLabel,
  formatTokyoDateTime,
  organizationEventErrorMessage,
  organizationEventPath,
  type OrganizationEvent,
  type OrganizationEventRegistrant,
} from "../features/orgs/orgEvents";
import { fetchOrganizationEventRegistrations } from "../features/orgs/orgEventsApi";
import { isBrowsePreview, useSession } from "../lib/session";
import {
  isLatestRequest,
  isSameUserScope,
  nextRequestId,
} from "../lib/userScopedResult";

export function OrganizationEventRegistrationsPage() {
  const { slug, eventId: eventIdRaw } = useParams();
  const eventId = Number(eventIdRaw);
  const { me, loading: sessionLoading } = useSession();
  const browsePreview = isBrowsePreview(me);
  const sessionUserId =
    me?.authenticated && me.user?.id != null ? me.user.id : null;
  const userIdRef = useRef(sessionUserId);
  userIdRef.current = sessionUserId;
  const fetchGen = useRef(0);
  const [event, setEvent] = useState<OrganizationEvent | null>(null);
  const [rows, setRows] = useState<OrganizationEventRegistrant[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [hasMore, setHasMore] = useState(false);
  const [nextOffset, setNextOffset] = useState(0);
  const [total, setTotal] = useState(0);

  useLayoutEffect(() => {
    nextRequestId(fetchGen);
    setEvent(null);
    setRows([]);
    setError(null);
    setLoading(true);
  }, [slug, eventId, sessionUserId]);

  const load = useCallback(
    async (offset = 0) => {
      if (!slug || !Number.isInteger(eventId) || eventId <= 0) return;
      const gen = nextRequestId(fetchGen);
      const startedUserId = userIdRef.current;
      if (offset === 0) setLoading(true);
      setError(null);
      try {
        const payload = await fetchOrganizationEventRegistrations(slug, eventId, offset);
        if (!isLatestRequest(fetchGen, gen)) return;
        if (!isSameUserScope(startedUserId, userIdRef.current)) return;
        setEvent(payload.event);
        setRows((prev) =>
          offset === 0 ? payload.registrations : [...prev, ...payload.registrations]
        );
        setHasMore(payload.has_more);
        setNextOffset(payload.next_offset);
        setTotal(payload.total);
      } catch (err) {
        if (!isLatestRequest(fetchGen, gen)) return;
        if (!isSameUserScope(startedUserId, userIdRef.current)) return;
        setEvent(null);
        setRows([]);
        setError(err instanceof OrganizationRequestError ? err.code : "load_failed");
      } finally {
        if (isLatestRequest(fetchGen, gen)) setLoading(false);
      }
    },
    [eventId, slug]
  );

  useEffect(() => {
    if (sessionLoading || browsePreview) return;
    void load(0);
  }, [browsePreview, load, sessionLoading, sessionUserId]);

  if (!slug || !Number.isInteger(eventId) || eventId <= 0) {
    return <Navigate to="/" replace />;
  }
  if (browsePreview || (!sessionLoading && !me?.authenticated)) {
    return (
      <div className="org-edit-page" data-spa-page="申込者">
        <div className="main-inner">
          <p>申込者一覧にはログインが必要です。</p>
          <Link
            className="btn btn-primary"
            to={spaLoginPath(`/app/organizations/${slug}/events/${eventId}/registrations`)}
          >
            ログイン
          </Link>
        </div>
      </div>
    );
  }

  const showManage = canShowEventManage({
    hydrated: !loading && !sessionLoading,
    canManage: Boolean(event?.can_manage),
  });

  return (
    <div className="org-edit-page" data-spa-page="申込者">
      <div className="main-inner">
        {loading || sessionLoading ? (
          <PeopleListSkeleton />
        ) : error && error !== "forbidden" && error !== "not_found" ? (
          <>
            <p role="alert">
              {organizationEventErrorMessage(error, "通信に失敗しました。")}
            </p>
            <button type="button" className="btn btn-secondary" onClick={() => void load(0)}>
              再試行
            </button>
          </>
        ) : !showManage ? (
          <p>このページは団体の管理者だけが利用できます。</p>
        ) : event ? (
          <section className="org-recruiting-card" aria-label="申込者一覧">
            <h1 className="org-recruiting-card__title">{event.title}</h1>
            <p className="org-recruiting-count">
              {eventCapacityLabel(event)}
              {total ? `（一覧 ${total}人）` : ""}
            </p>
            {rows.length === 0 ? (
              <p className="org-profile-empty">まだ申し込みはありません。</p>
            ) : (
              <ul className="org-recruiting-people">
                {rows.map((row) => (
                  <li key={row.id} className="org-recruiting-person">
                    <div className="org-recruiting-person__identity">
                      {row.user.avatar_url ? (
                        <img src={row.user.avatar_url} alt="" />
                      ) : (
                        <span>{row.user.initial}</span>
                      )}
                      <div>
                        <strong>{row.user.display_name || row.user.username}</strong>
                        <p>{formatTokyoDateTime(row.created_at)}</p>
                      </div>
                    </div>
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
            <p>
              <Link to={organizationEventPath(slug, event.id)}>イベント詳細へ</Link>
            </p>
          </section>
        ) : null}
      </div>
    </div>
  );
}
