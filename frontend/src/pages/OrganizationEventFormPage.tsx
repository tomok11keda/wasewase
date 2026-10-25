import { useCallback, useEffect, useLayoutEffect, useRef, useState, type FormEvent } from "react";
import { Link, Navigate, useNavigate, useParams } from "react-router-dom";
import { FormSkeleton } from "../components/skeleton";
import { spaLoginPath } from "../features/auth/api";
import { OrganizationRequestError } from "../features/orgs/api";
import {
  canShowEventManage,
  emptyEventForm,
  formFromOrganizationEvent,
  organizationEventErrorMessage,
  organizationEventManagePath,
  organizationEventPath,
  validateEventForm,
  type OrganizationEventForm,
} from "../features/orgs/orgEvents";
import {
  createOrganizationEvent,
  fetchOrganizationEvent,
  fetchOrganizationEvents,
  updateOrganizationEvent,
} from "../features/orgs/orgEventsApi";
import { isBrowsePreview, useSession } from "../lib/session";
import {
  isLatestRequest,
  isSameUserScope,
  nextRequestId,
} from "../lib/userScopedResult";

export function OrganizationEventFormPage() {
  const { slug, eventId: eventIdRaw } = useParams();
  const eventId = eventIdRaw ? Number(eventIdRaw) : null;
  const isEdit = eventId != null && Number.isInteger(eventId) && eventId > 0;
  const navigate = useNavigate();
  const { me, loading: sessionLoading } = useSession();
  const browsePreview = isBrowsePreview(me);
  const sessionUserId =
    me?.authenticated && me.user?.id != null ? me.user.id : null;
  const userIdRef = useRef(sessionUserId);
  userIdRef.current = sessionUserId;
  const fetchGen = useRef(0);
  const busyRef = useRef(false);
  const [form, setForm] = useState<OrganizationEventForm>(emptyEventForm());
  const [canManage, setCanManage] = useState(false);
  const [hasLottery, setHasLottery] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);

  useLayoutEffect(() => {
    nextRequestId(fetchGen);
    setForm(emptyEventForm());
    setCanManage(false);
    setHasLottery(false);
    setError(null);
    setFieldErrors({});
    setLoading(true);
  }, [slug, eventId, sessionUserId, isEdit]);

  const load = useCallback(async () => {
    if (!slug) return;
    const gen = nextRequestId(fetchGen);
    const startedUserId = userIdRef.current;
    setLoading(true);
    setError(null);
    try {
      if (isEdit && eventId != null) {
        const event = await fetchOrganizationEvent(slug, eventId);
        if (!isLatestRequest(fetchGen, gen)) return;
        if (!isSameUserScope(startedUserId, userIdRef.current)) return;
        setCanManage(event.can_manage);
        setHasLottery(event.has_lottery);
        setForm(formFromOrganizationEvent(event));
      } else {
        const payload = await fetchOrganizationEvents(slug, { manage: true });
        if (!isLatestRequest(fetchGen, gen)) return;
        if (!isSameUserScope(startedUserId, userIdRef.current)) return;
        setCanManage(payload.can_manage);
      }
    } catch (err) {
      if (!isLatestRequest(fetchGen, gen)) return;
      if (!isSameUserScope(startedUserId, userIdRef.current)) return;
      setCanManage(false);
      setHasLottery(false);
      setError(err instanceof OrganizationRequestError ? err.code : "load_failed");
    } finally {
      if (isLatestRequest(fetchGen, gen)) setLoading(false);
    }
  }, [eventId, isEdit, slug]);

  useEffect(() => {
    if (sessionLoading || browsePreview) return;
    void load();
  }, [browsePreview, load, sessionLoading, sessionUserId]);

  if (!slug) return <Navigate to="/" replace />;
  const loginNext = isEdit
    ? `/app/organizations/${slug}/events/${eventId}/edit`
    : `/app/organizations/${slug}/events/new`;
  if (browsePreview || (!sessionLoading && !me?.authenticated)) {
    return (
      <div className="org-edit-page" data-spa-page="イベント編集">
        <div className="main-inner">
          <p>イベントの作成・編集にはログインが必要です。</p>
          <Link className="btn btn-primary" to={spaLoginPath(loginNext)}>
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

  const onSubmit = (ev: FormEvent) => {
    ev.preventDefault();
    if (busyRef.current || !slug) return;
    const errors = validateEventForm(form);
    setFieldErrors(errors);
    if (Object.keys(errors).length) return;
    busyRef.current = true;
    setBusy(true);
    setError(null);
    void (async () => {
      try {
        const saved = isEdit && eventId != null
          ? await updateOrganizationEvent(slug, eventId, form)
          : await createOrganizationEvent(slug, form);
        navigate(organizationEventPath(slug, saved.id), { replace: true });
      } catch (err) {
        if (err instanceof OrganizationRequestError) {
          setFieldErrors(err.fieldErrors);
          setError(err.code);
        } else {
          setError("load_failed");
        }
      } finally {
        busyRef.current = false;
        setBusy(false);
      }
    })();
  };

  const setField = (key: keyof OrganizationEventForm, value: string | boolean) => {
    setForm((prev) => ({ ...prev, [key]: value }));
  };

  return (
    <div className="org-edit-page" data-spa-page="イベント編集">
      <div className="main-inner">
        {loading || sessionLoading ? (
          <FormSkeleton />
        ) : error === "not_found" || error === "forbidden" || !showManage ? (
          <p>このページは団体の管理者だけが利用できます。</p>
        ) : (
          <form className="org-edit-form" onSubmit={onSubmit}>
            <h1 className="org-recruiting-card__title">
              {isEdit ? "イベントを編集" : "イベントを作成"}
            </h1>
            {error && error !== "invalid_payload" ? (
              <p className="org-edit-error" role="alert">
                {organizationEventErrorMessage(error, "保存できませんでした。")}
              </p>
            ) : null}
            <label>
              イベント名
              <input
                value={form.title}
                onChange={(e) => setField("title", e.target.value)}
                maxLength={120}
                required
              />
              {fieldErrors.title ? <span className="org-edit-error">{fieldErrors.title}</span> : null}
            </label>
            <label>
              説明
              <textarea
                value={form.description}
                onChange={(e) => setField("description", e.target.value)}
                rows={5}
              />
              {fieldErrors.description ? (
                <span className="org-edit-error">{fieldErrors.description}</span>
              ) : null}
            </label>
            <label>
              開始日時（日本時間）
              <input
                type="datetime-local"
                value={form.starts_at}
                onChange={(e) => setField("starts_at", e.target.value)}
                required
              />
              {fieldErrors.starts_at ? (
                <span className="org-edit-error">{fieldErrors.starts_at}</span>
              ) : null}
            </label>
            <label>
              終了日時（日本時間）
              <input
                type="datetime-local"
                value={form.ends_at}
                onChange={(e) => setField("ends_at", e.target.value)}
                required
              />
              {fieldErrors.ends_at ? <span className="org-edit-error">{fieldErrors.ends_at}</span> : null}
            </label>
            <label>
              会場
              <input
                value={form.venue_name}
                onChange={(e) => setField("venue_name", e.target.value)}
                required
              />
              {fieldErrors.venue_name ? (
                <span className="org-edit-error">{fieldErrors.venue_name}</span>
              ) : null}
            </label>
            <label>
              住所（任意）
              <input
                value={form.venue_address}
                onChange={(e) => setField("venue_address", e.target.value)}
              />
            </label>
            <label>
              申込締切（任意・日本時間）
              <input
                type="datetime-local"
                value={form.registration_deadline}
                onChange={(e) => setField("registration_deadline", e.target.value)}
              />
              {fieldErrors.registration_deadline ? (
                <span className="org-edit-error">{fieldErrors.registration_deadline}</span>
              ) : null}
            </label>
            <label className="org-event-check">
              <input
                type="checkbox"
                checked={form.registration_open}
                disabled={hasLottery}
                onChange={(e) => setField("registration_open", e.target.checked)}
              />
              {hasLottery
                ? "抽選確定後は申し込みを再開できません"
                : "申し込みを受け付ける"}
            </label>
            <div className="org-recruiting-card__actions">
              <button type="submit" className="btn btn-primary" disabled={busy}>
                {busy ? "保存中…" : "保存する"}
              </button>
              <Link className="btn btn-secondary" to={organizationEventManagePath(slug)}>
                キャンセル
              </Link>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
