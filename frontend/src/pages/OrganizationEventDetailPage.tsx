import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { Link, Navigate, useNavigate, useParams } from "react-router-dom";
import { ListRowSkeleton } from "../components/skeleton";
import { spaLoginPath } from "../features/auth/api";
import { OrganizationRequestError } from "../features/orgs/api";
import {
  canShowEventManage,
  eventCapacityLabel,
  eventPageView,
  eventStatusLabel,
  formatTokyoDateTime,
  lotteryResultLabel,
  viewerLotteryRegistrationLabel,
  organizationEventEditPath,
  organizationEventErrorMessage,
  organizationEventLotteryPath,
  organizationEventManagePath,
  organizationEventRegistrationsPath,
  type OrganizationEvent,
} from "../features/orgs/orgEvents";
import {
  cancelOrganizationEvent,
  deleteOrganizationEvent,
  fetchOrganizationEvent,
  patchEventRegistrationOpen,
  publishOrganizationEvent,
  registerOrganizationEvent,
  unpublishOrganizationEvent,
  unregisterOrganizationEvent,
} from "../features/orgs/orgEventsApi";
import { isBrowsePreview, useSession } from "../lib/session";
import {
  isLatestRequest,
  isSameUserScope,
  nextRequestId,
} from "../lib/userScopedResult";

function errorCode(err: unknown): string {
  return err instanceof OrganizationRequestError ? err.code : "load_failed";
}

export function OrganizationEventDetailPage() {
  const { slug, eventId: eventIdRaw } = useParams();
  const eventId = Number(eventIdRaw);
  const navigate = useNavigate();
  const { me, loading: sessionLoading } = useSession();
  const browsePreview = isBrowsePreview(me);
  const sessionUserId =
    me?.authenticated && me.user?.id != null ? me.user.id : null;
  const userIdRef = useRef(sessionUserId);
  userIdRef.current = sessionUserId;
  const fetchGen = useRef(0);
  const busyRef = useRef(false);
  const [event, setEvent] = useState<OrganizationEvent | null>(null);
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
  }, [slug, eventId, sessionUserId]);

  const load = useCallback(async () => {
    if (!slug || !Number.isInteger(eventId) || eventId <= 0) {
      setError("not_found");
      setLoading(false);
      return;
    }
    const gen = nextRequestId(fetchGen);
    const startedUserId = userIdRef.current;
    setLoading(true);
    setError(null);
    try {
      const data = await fetchOrganizationEvent(slug, eventId);
      if (!isLatestRequest(fetchGen, gen)) return;
      if (!isSameUserScope(startedUserId, userIdRef.current)) return;
      setEvent(data);
    } catch (err) {
      if (!isLatestRequest(fetchGen, gen)) return;
      if (!isSameUserScope(startedUserId, userIdRef.current)) return;
      setEvent(null);
      setError(errorCode(err));
    } finally {
      if (isLatestRequest(fetchGen, gen)) setLoading(false);
    }
  }, [eventId, slug]);

  useEffect(() => {
    if (sessionLoading || browsePreview) return;
    void load();
  }, [browsePreview, load, sessionLoading, sessionUserId]);

  if (!slug || !Number.isInteger(eventId) || eventId <= 0) {
    return <Navigate to="/" replace />;
  }

  const loginNext = `/app/organizations/${slug}/events/${eventId}`;
  if (browsePreview || (!sessionLoading && !me?.authenticated)) {
    return (
      <div className="org-edit-page" data-spa-page="イベント">
        <div className="main-inner">
          <p>イベントの確認・申し込みにはログインが必要です。</p>
          <Link className="btn btn-primary" to={spaLoginPath(loginNext)}>
            ログイン
          </Link>
        </div>
      </div>
    );
  }

  const run = async (fn: () => Promise<OrganizationEvent>) => {
    if (busyRef.current) return;
    busyRef.current = true;
    setBusy(true);
    setActionError(null);
    try {
      setEvent(await fn());
    } catch (err) {
      setActionError(
        err instanceof OrganizationRequestError
          ? err.message
          : "操作に失敗しました。"
      );
    } finally {
      busyRef.current = false;
      setBusy(false);
    }
  };

  const view = eventPageView({ loading: loading || sessionLoading, error, event });
  const showManage = canShowEventManage({
    hydrated: !loading && !sessionLoading,
    canManage: Boolean(event?.can_manage),
  });

  return (
    <div className="org-edit-page" data-spa-page="イベント">
      <div className="main-inner">
        {view === "loading" ? (
          <ListRowSkeleton rows={5} />
        ) : view === "missing" ? (
          <p>イベントが見つからないか、表示できません。</p>
        ) : view === "error" ? (
          <>
            <p role="alert">
              {organizationEventErrorMessage(error || undefined, "通信に失敗しました。")}
            </p>
            <button type="button" className="btn btn-secondary" onClick={() => void load()}>
              再試行
            </button>
          </>
        ) : event ? (
          <section className="org-recruiting-card" aria-label="イベント詳細">
            <p className="org-event-kicker">{event.organization_name}</p>
            <h1 className="org-recruiting-card__title">{event.title}</h1>
            <ul className="org-recruiting-card__meta">
              <li>{eventStatusLabel(event)}</li>
              <li>{eventCapacityLabel(event)}</li>
            </ul>
            <p className="org-recruiting-card__lead">
              {formatTokyoDateTime(event.starts_at)} 〜 {formatTokyoDateTime(event.ends_at)}
            </p>
            <p className="org-recruiting-card__lead">
              {event.venue_name}
              {event.venue_address ? `（${event.venue_address}）` : ""}
            </p>
            {event.description ? (
              <p className="org-recruiting-card__description">{event.description}</p>
            ) : null}
            {actionError ? (
              <p className="org-edit-error" role="alert">
                {actionError}
              </p>
            ) : null}
            <div className="org-recruiting-card__actions">
              {event.viewer_lottery_result ? (
                <p className="org-recruiting-card__pending">
                  抽選結果：{lotteryResultLabel(event.viewer_lottery_result)}
                  {viewerLotteryRegistrationLabel(event)
                    ? `（${viewerLotteryRegistrationLabel(event)}）`
                    : ""}
                </p>
              ) : null}
              {event.can_view_lottery ? (
                <p className="org-recruiting-card__actions">
                  <Link
                    className="btn btn-secondary"
                    to={organizationEventLotteryPath(slug, event.id)}
                  >
                    抽選結果を見る
                  </Link>
                </p>
              ) : null}
              {event.can_register ? (
                <button
                  type="button"
                  className="btn btn-primary"
                  disabled={busy}
                  onClick={() => void run(() => registerOrganizationEvent(slug, event.id))}
                >
                  {busy ? "送信中…" : "参加を申し込む"}
                </button>
              ) : null}
              {event.can_cancel_registration ? (
                <button
                  type="button"
                  className="btn btn-secondary"
                  disabled={busy}
                  onClick={() => {
                    const message = event.has_lottery
                      ? "抽選結果は残ります。参加を辞退しますか？"
                      : "申し込みを取り消しますか？";
                    if (!window.confirm(message)) return;
                    void run(() => unregisterOrganizationEvent(slug, event.id));
                  }}
                >
                  {busy
                    ? "送信中…"
                    : event.has_lottery
                      ? "参加を辞退"
                      : "申し込みを取り消す"}
                </button>
              ) : null}
              {event.viewer_registered && !event.viewer_lottery_result ? (
                <p className="org-recruiting-card__pending">申し込み済みです。</p>
              ) : null}
              {event.can_register || event.can_cancel_registration ? (
                <p className="org-event-privacy">
                  抽選を行う場合、氏名・アバター・除外備考が新歓チャット内で公開されることがあります。健康情報や連絡先など機微な内容は入力しないでください。
                </p>
              ) : null}
            </div>
            {showManage ? (
              <>
                <p className="org-recruiting-card__actions">
                  {event.status === "draft" ? (
                    <button
                      type="button"
                      className="btn btn-primary"
                      disabled={busy}
                      onClick={() =>
                        void run(() => publishOrganizationEvent(slug, event.id))
                      }
                    >
                      公開する
                    </button>
                  ) : null}
                  {event.status === "published" ? (
                    <button
                      type="button"
                      className="btn btn-secondary"
                      disabled={busy}
                      onClick={() =>
                        void run(() => unpublishOrganizationEvent(slug, event.id))
                      }
                    >
                      非公開にする
                    </button>
                  ) : null}
                  {event.status !== "cancelled" &&
                  (event.registration_open || event.can_reopen_registration) ? (
                    <button
                      type="button"
                      className="btn btn-secondary"
                      disabled={busy || (event.has_lottery && !event.registration_open)}
                      onClick={() =>
                        void run(() =>
                          patchEventRegistrationOpen(
                            slug,
                            event.id,
                            !event.registration_open
                          )
                        )
                      }
                    >
                      {event.registration_open ? "申込を停止" : "申込を再開"}
                    </button>
                  ) : null}
                </p>
                <p className="org-recruiting-card__actions">
                  <Link className="btn btn-secondary" to={organizationEventEditPath(slug, event.id)}>
                    編集
                  </Link>
                  <Link
                    className="btn btn-secondary"
                    to={organizationEventRegistrationsPath(slug, event.id)}
                  >
                    申込者
                  </Link>
                  {event.can_run_lottery ? (
                    <Link
                      className="btn btn-primary"
                      to={organizationEventLotteryPath(slug, event.id)}
                    >
                      抽選する
                    </Link>
                  ) : null}
                  {event.has_lottery ? (
                    <Link
                      className="btn btn-secondary"
                      to={organizationEventLotteryPath(slug, event.id)}
                    >
                      抽選結果
                    </Link>
                  ) : null}
                  <Link className="btn btn-secondary" to={organizationEventManagePath(slug)}>
                    イベント管理
                  </Link>
                </p>
                {event.status !== "cancelled" ? (
                  <p className="org-recruiting-card__actions">
                    <button
                      type="button"
                      className="btn btn-secondary"
                      disabled={busy}
                      onClick={() => {
                        if (!window.confirm("このイベントを中止します。申込者に通知されます。")) {
                          return;
                        }
                        void run(() => cancelOrganizationEvent(slug, event.id));
                      }}
                    >
                      イベントを中止
                    </button>
                    <button
                      type="button"
                      className="btn btn-secondary"
                      disabled={busy}
                      onClick={() => {
                        if (!window.confirm("このイベントを削除しますか？公開一覧から消えます。")) {
                          return;
                        }
                        void (async () => {
                          if (busyRef.current) return;
                          busyRef.current = true;
                          setBusy(true);
                          try {
                            await deleteOrganizationEvent(slug, event.id);
                            navigate(organizationEventManagePath(slug), { replace: true });
                          } catch (err) {
                            setActionError(
                              err instanceof OrganizationRequestError
                                ? err.message
                                : "削除できませんでした。"
                            );
                          } finally {
                            busyRef.current = false;
                            setBusy(false);
                          }
                        })();
                      }}
                    >
                      削除
                    </button>
                  </p>
                ) : null}
              </>
            ) : null}
            <p>
              <Link to={`/orgs/${slug}`}>団体プロフィールへ</Link>
            </p>
          </section>
        ) : null}
      </div>
    </div>
  );
}
