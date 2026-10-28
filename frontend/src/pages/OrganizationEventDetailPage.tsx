import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { Link, Navigate, useNavigate, useParams } from "react-router-dom";
import { ListRowSkeleton } from "../components/skeleton";
import { spaLoginPath } from "../features/auth/api";
import { OrganizationRequestError } from "../features/orgs/api";
import { OrganizationEventDetailView } from "../features/orgs/OrganizationEventDetailView";
import {
  canShowEventManage,
  eventPageView,
  organizationEventEditPath,
  organizationEventErrorMessage,
  organizationEventManagePath,
  type OrganizationEvent,
} from "../features/orgs/orgEvents";
import {
  cancelOrganizationEvent,
  deleteOrganizationEvent,
  duplicateOrganizationEvent,
  fetchOrganizationEvent,
  patchEventRegistrationOpen,
  publishOrganizationEvent,
  registerOrganizationEvent,
  shareOrganizationEventToChat,
  shareOrganizationEventToTimeline,
  unpublishOrganizationEvent,
  unregisterOrganizationEvent,
} from "../features/orgs/orgEventsApi";
import { invalidateTimelineFeed } from "../features/timeline/feedInvalidation";
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
  const [shareBusy, setShareBusy] = useState(false);
  const [shareNote, setShareNote] = useState<string | null>(null);
  const [sharePostPath, setSharePostPath] = useState<string | null>(null);
  const [timelineBody, setTimelineBody] = useState("");
  const [timelineBusy, setTimelineBusy] = useState(false);

  useLayoutEffect(() => {
    nextRequestId(fetchGen);
    setEvent(null);
    setError(null);
    setActionError(null);
    setShareNote(null);
    setSharePostPath(null);
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
    <div className="org-edit-page org-event-detail-page" data-spa-page="イベント">
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
          <OrganizationEventDetailView
            slug={slug}
            event={event}
            showManage={showManage}
            busy={busy}
            actionError={actionError}
            shareNote={shareNote}
            sharePostPath={sharePostPath}
            shareBusy={shareBusy}
            timelineBody={timelineBody}
            timelineBusy={timelineBusy}
            onTimelineBodyChange={setTimelineBody}
            onPublish={() =>
              void run(() => publishOrganizationEvent(slug, event.id))
            }
            onUnpublish={() =>
              void run(() => unpublishOrganizationEvent(slug, event.id))
            }
            onToggleRegistration={() =>
              void run(() =>
                patchEventRegistrationOpen(slug, event.id, !event.registration_open)
              )
            }
            onRegister={() =>
              void run(() => registerOrganizationEvent(slug, event.id))
            }
            onUnregister={() => {
              const message = event.has_lottery
                ? "抽選結果は残ります。参加を辞退しますか？"
                : "申し込みを取り消しますか？";
              if (!window.confirm(message)) return;
              void run(() => unregisterOrganizationEvent(slug, event.id));
            }}
            onDuplicate={() =>
              void run(async () => {
                const copy = await duplicateOrganizationEvent(slug, event.id);
                navigate(organizationEventEditPath(slug, copy.id));
                return event;
              })
            }
            onCancelEvent={() => {
              if (!window.confirm("このイベントを中止します。申込者に通知されます。")) {
                return;
              }
              void run(() => cancelOrganizationEvent(slug, event.id));
            }}
            onDelete={() => {
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
            onTimelineShare={() =>
              void run(async () => {
                setTimelineBusy(true);
                setShareNote(null);
                setSharePostPath(null);
                try {
                  const shared = await shareOrganizationEventToTimeline(
                    slug,
                    event.id,
                    timelineBody
                  );
                  invalidateTimelineFeed();
                  setShareNote("タイムラインにシェアしました。");
                  setSharePostPath(shared.postPath);
                  setTimelineBody("");
                  return shared.event || event;
                } finally {
                  setTimelineBusy(false);
                }
              })
            }
            onChatShare={async (chatIds) => {
              setShareBusy(true);
              setShareNote(null);
              setActionError(null);
              try {
                let shared = 0;
                for (const chatId of chatIds) {
                  try {
                    await shareOrganizationEventToChat(slug, event.id, chatId);
                    shared += 1;
                  } catch (err) {
                    if (
                      err instanceof OrganizationRequestError &&
                      err.code === "already_shared"
                    ) {
                      continue;
                    }
                    throw err;
                  }
                }
                setShareNote(
                  shared
                    ? `${shared}件の団体チャットに共有しました。`
                    : "選択したチャットにはすでに共有済みです。"
                );
              } catch (err) {
                setActionError(
                  err instanceof OrganizationRequestError
                    ? err.message
                    : "共有できませんでした。"
                );
              } finally {
                setShareBusy(false);
              }
            }}
          />
        ) : null}
      </div>
    </div>
  );
}
