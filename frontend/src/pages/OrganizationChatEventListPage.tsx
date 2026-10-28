import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { Link, Navigate, useParams, useSearchParams } from "react-router-dom";
import { ListRowSkeleton } from "../components/skeleton";
import { spaLoginPath } from "../features/auth/api";
import { OrganizationRequestError } from "../features/orgs/api";
import {
  chatEventBackPath,
  chatEventStatusLabel,
  recruitingChatEventNewPath,
  recruitingChatEventPath,
  type OrganizationChatEvent,
} from "../features/orgs/orgChatEvents";
import { fetchOrganizationChatEvents } from "../features/orgs/orgChatEventsApi";
import { formatTokyoDateTime } from "../features/orgs/orgEvents";
import { parseRecruitingChatIdFromSearch } from "../features/orgs/recruitingChat";
import { isBrowsePreview, useSession } from "../lib/session";
import {
  isLatestRequest,
  isSameUserScope,
  nextRequestId,
} from "../lib/userScopedResult";

export function OrganizationChatEventListPage() {
  const { slug } = useParams();
  const [searchParams] = useSearchParams();
  const chatId = parseRecruitingChatIdFromSearch(searchParams.toString());
  const { me, loading: sessionLoading } = useSession();
  const browsePreview = isBrowsePreview(me);
  const sessionUserId =
    me?.authenticated && me.user?.id != null ? me.user.id : null;
  const userIdRef = useRef(sessionUserId);
  userIdRef.current = sessionUserId;
  const fetchGen = useRef(0);
  const [events, setEvents] = useState<OrganizationChatEvent[]>([]);
  const [canManage, setCanManage] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useLayoutEffect(() => {
    nextRequestId(fetchGen);
    setEvents([]);
    setCanManage(false);
    setError(null);
    setLoading(true);
  }, [slug, chatId, sessionUserId]);

  const load = useCallback(async () => {
    if (!slug || chatId == null) {
      setError("not_found");
      setLoading(false);
      return;
    }
    const gen = nextRequestId(fetchGen);
    const startedUserId = userIdRef.current;
    try {
      const payload = await fetchOrganizationChatEvents(slug, chatId);
      if (!isLatestRequest(fetchGen, gen)) return;
      if (!isSameUserScope(startedUserId, userIdRef.current)) return;
      setEvents(payload.events);
      setCanManage(payload.can_manage);
    } catch (err) {
      if (!isLatestRequest(fetchGen, gen)) return;
      if (!isSameUserScope(startedUserId, userIdRef.current)) return;
      setError(err instanceof OrganizationRequestError ? err.code : "load_failed");
    } finally {
      if (isLatestRequest(fetchGen, gen)) setLoading(false);
    }
  }, [chatId, slug]);

  useEffect(() => {
    if (sessionLoading || browsePreview) return;
    void load();
  }, [browsePreview, load, sessionLoading, sessionUserId]);

  if (!slug || chatId == null) {
    return <Navigate to="/" replace />;
  }

  const loginNext = `/app/organizations/${slug}/recruiting-chat/events?chat=${chatId}`;
  if (browsePreview || (!sessionLoading && !me?.authenticated)) {
    return (
      <div className="org-edit-page" data-spa-page="チャット内イベント">
        <div className="main-inner">
          <p>チャット内イベントの確認にはログインが必要です。</p>
          <Link className="btn btn-primary" to={spaLoginPath(loginNext)}>
            ログイン
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="org-edit-page" data-spa-page="チャット内イベント">
      <div className="main-inner">
        <p className="org-event-kicker">このチャットの参加者だけに表示</p>
        <h1>チャット内イベント</h1>
        {loading || sessionLoading ? (
          <ListRowSkeleton rows={4} />
        ) : error ? (
          <p>このチャットのイベントを表示できません。</p>
        ) : (
          <>
            {canManage ? (
              <p>
                <Link
                  className="btn btn-primary"
                  to={recruitingChatEventNewPath(slug, chatId)}
                >
                  イベントを作成
                </Link>
              </p>
            ) : null}
            {events.length === 0 ? (
              <p>今後のチャット内イベントはありません。</p>
            ) : (
              <ul className="org-event-person-list">
                {events.map((event) => (
                  <li key={event.id}>
                    <Link to={recruitingChatEventPath(slug, event.id, chatId)}>
                      {event.title}
                      <span>
                        {formatTokyoDateTime(event.starts_at)} ·{" "}
                        {chatEventStatusLabel(event)}
                      </span>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
            <p>
              <Link to={chatEventBackPath(slug, chatId)}>チャットへ戻る</Link>
            </p>
          </>
        )}
      </div>
    </div>
  );
}
