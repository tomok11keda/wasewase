import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { Link, Navigate, useParams, useSearchParams } from "react-router-dom";
import { ListRowSkeleton } from "../components/skeleton";
import { spaLoginPath } from "../features/auth/api";
import { OrganizationRequestError } from "../features/orgs/api";
import {
  chatEventAnswerLabel,
  chatEventBackPath,
  chatEventSafeFallbackPath,
  chatEventStatusLabel,
  recruitingChatEventEditPath,
  recruitingChatEventNewPath,
  type ChatEventAnswer,
  type OrganizationChatEvent,
} from "../features/orgs/orgChatEvents";
import {
  cancelOrganizationChatEvent,
  fetchOrganizationChatEvent,
  rsvpOrganizationChatEvent,
} from "../features/orgs/orgChatEventsApi";
import { formatTokyoDateTime, organizationEventErrorMessage } from "../features/orgs/orgEvents";
import { parseRecruitingChatIdFromSearch } from "../features/orgs/recruitingChat";
import { isBrowsePreview, useSession } from "../lib/session";
import {
  isLatestRequest,
  isSameUserScope,
  nextRequestId,
} from "../lib/userScopedResult";

const ANSWERS: ChatEventAnswer[] = ["going", "not_going", "maybe"];

export function OrganizationChatEventDetailPage() {
  const { slug, eventId: eventIdRaw } = useParams();
  const [searchParams] = useSearchParams();
  const chatId = parseRecruitingChatIdFromSearch(searchParams.toString());
  const eventId = Number(eventIdRaw);
  const { me, loading: sessionLoading } = useSession();
  const browsePreview = isBrowsePreview(me);
  const sessionUserId =
    me?.authenticated && me.user?.id != null ? me.user.id : null;
  const userIdRef = useRef(sessionUserId);
  userIdRef.current = sessionUserId;
  const fetchGen = useRef(0);
  const busyRef = useRef(false);
  const [event, setEvent] = useState<OrganizationChatEvent | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  useLayoutEffect(() => {
    nextRequestId(fetchGen);
    setEvent(null);
    setError(null);
    setActionError(null);
    setLoading(true);
  }, [slug, eventId, chatId, sessionUserId]);

  const load = useCallback(async () => {
    if (!slug || !Number.isInteger(eventId) || eventId <= 0 || chatId == null) {
      setError("not_found");
      setLoading(false);
      return;
    }
    const gen = nextRequestId(fetchGen);
    const startedUserId = userIdRef.current;
    try {
      const data = await fetchOrganizationChatEvent(slug, eventId, chatId);
      if (!isLatestRequest(fetchGen, gen)) return;
      if (!isSameUserScope(startedUserId, userIdRef.current)) return;
      setEvent(data);
    } catch (err) {
      if (!isLatestRequest(fetchGen, gen)) return;
      if (!isSameUserScope(startedUserId, userIdRef.current)) return;
      setEvent(null);
      setError(err instanceof OrganizationRequestError ? err.code : "load_failed");
    } finally {
      if (isLatestRequest(fetchGen, gen)) setLoading(false);
    }
  }, [chatId, eventId, slug]);

  useEffect(() => {
    if (sessionLoading || browsePreview) return;
    void load();
  }, [browsePreview, load, sessionLoading, sessionUserId]);

  if (!slug) {
    return <Navigate to="/" replace />;
  }
  if (!Number.isInteger(eventId) || eventId <= 0 || chatId == null) {
    return <Navigate to={chatEventSafeFallbackPath(slug)} replace />;
  }

  const loginNext = `/app/organizations/${slug}/recruiting-chat/events/${eventId}?chat=${chatId}`;
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

  async function run(task: () => Promise<OrganizationChatEvent>) {
    if (busyRef.current) return;
    busyRef.current = true;
    setBusy(true);
    setActionError(null);
    try {
      setEvent(await task());
    } catch (err) {
      setActionError(
        err instanceof OrganizationRequestError
          ? err.message
          : organizationEventErrorMessage("load_failed", "操作できませんでした。")
      );
    } finally {
      busyRef.current = false;
      setBusy(false);
    }
  }

  return (
    <div className="org-edit-page" data-spa-page="チャット内イベント">
      <div className="main-inner">
        {loading || sessionLoading ? (
          <ListRowSkeleton rows={6} />
        ) : error === "not_found" || error === "forbidden" ? (
          <Navigate to={chatEventSafeFallbackPath(slug)} replace />
        ) : error || !event ? (
          <p>このチャット内イベントを表示する権限がありません。</p>
        ) : (
          <>
            <p className="org-event-kicker">チャット内 · {chatEventStatusLabel(event)}</p>
            <h1>{event.title}</h1>
            <p>{formatTokyoDateTime(event.starts_at)}</p>
            {event.ends_at ? <p>〜 {formatTokyoDateTime(event.ends_at)}</p> : null}
            {event.venue_name ? <p>{event.venue_name}</p> : null}
            {event.description ? (
              <p className="org-event-description">{event.description}</p>
            ) : null}
            {event.rsvp_deadline ? (
              <p>回答期限 {formatTokyoDateTime(event.rsvp_deadline)}</p>
            ) : null}
            <p className="org-event-counts">
              参加 {event.going_count} · 不参加 {event.not_going_count} · 未定{" "}
              {event.maybe_count} · 未回答 {event.unanswered_count}
            </p>
            {actionError ? (
              <p className="org-edit-error" role="alert">
                {actionError}
              </p>
            ) : null}
            {event.can_rsvp ? (
              <div className="org-chat-event-rsvp">
                {ANSWERS.map((answer) => (
                  <button
                    key={answer}
                    type="button"
                    className={
                      event.viewer_answer === answer
                        ? "btn btn-primary"
                        : "btn btn-secondary"
                    }
                    disabled={busy}
                    onClick={() =>
                      void run(() =>
                        rsvpOrganizationChatEvent(slug, event.id, chatId, answer)
                      )
                    }
                  >
                    {chatEventAnswerLabel(answer)}
                  </button>
                ))}
              </div>
            ) : event.viewer_answer ? (
              <p>回答：{chatEventAnswerLabel(event.viewer_answer)}</p>
            ) : null}
            {event.can_manage && event.respondents ? (
              <section className="org-chat-event-respondents">
                <h2>回答者</h2>
                {(
                  [
                    ["going", "参加"],
                    ["not_going", "不参加"],
                    ["maybe", "未定"],
                    ["unanswered", "未回答"],
                  ] as const
                ).map(([key, label]) => (
                  <div key={key}>
                    <h3>
                      {label}（{event.respondents?.[key].length || 0}）
                    </h3>
                    <ul className="org-event-person-list">
                      {(event.respondents?.[key] || []).map((row) => (
                        <li key={`${key}-${row.user.id}`}>
                          {row.user.display_name}
                        </li>
                      ))}
                    </ul>
                  </div>
                ))}
              </section>
            ) : null}
            <p className="org-recruiting-card__actions">
              <Link className="btn btn-secondary" to={chatEventBackPath(slug, chatId)}>
                チャットへ戻る
              </Link>
              {event.can_manage && event.chat_is_active && !event.is_cancelled ? (
                <Link
                  className="btn btn-secondary"
                  to={recruitingChatEventEditPath(slug, event.id, chatId)}
                >
                  編集
                </Link>
              ) : null}
              {event.can_manage && event.chat_is_active && !event.is_cancelled ? (
                <button
                  type="button"
                  className="btn btn-secondary"
                  disabled={busy}
                  onClick={() => {
                    if (!window.confirm("このチャット内イベントを中止しますか？")) return;
                    void run(() =>
                      cancelOrganizationChatEvent(slug, event.id, chatId)
                    );
                  }}
                >
                  中止する
                </button>
              ) : null}
              {event.can_manage ? (
                <Link
                  className="btn btn-secondary"
                  to={recruitingChatEventNewPath(slug, chatId)}
                >
                  別のイベントを作る
                </Link>
              ) : null}
            </p>
          </>
        )}
      </div>
    </div>
  );
}
