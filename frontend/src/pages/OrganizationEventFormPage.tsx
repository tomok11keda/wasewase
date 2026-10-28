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
  const pageTitle = isEdit ? "イベントを編集" : "イベントを作成";

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
      <div className="org-edit-page" data-spa-page={pageTitle}>
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

  const setField = <K extends keyof OrganizationEventForm>(
    key: K,
    value: OrganizationEventForm[K]
  ) => {
    setForm((prev) => ({ ...prev, [key]: value }));
  };

  return (
    <div className="org-edit-page" data-spa-page={pageTitle}>
      <div className="main-inner">
        {loading || sessionLoading ? (
          <FormSkeleton rows={8} />
        ) : error === "not_found" || error === "forbidden" || !showManage ? (
          <p>このページは団体の管理者だけが利用できます。</p>
        ) : (
          <>
            <p className="form-lead">
              {isEdit
                ? "内容を更新します。公開や抽選の操作は詳細画面から行います。"
                : "まずは下書きを保存します。公開と抽選は作成後に設定できます。"}
            </p>
            <form className="form-card org-event-form" onSubmit={onSubmit} noValidate>
              {error && error !== "invalid_payload" ? (
                <p className="org-edit-error" role="alert">
                  {organizationEventErrorMessage(error, "保存できませんでした。入力内容は残しています。")}
                </p>
              ) : null}

              <div className="form-group">
                <label htmlFor="event-title">イベント名</label>
                <input
                  id="event-title"
                  value={form.title}
                  onChange={(e) => setField("title", e.target.value)}
                  maxLength={120}
                  autoComplete="off"
                  required
                />
                {fieldErrors.title ? (
                  <p className="org-edit-field-error">{fieldErrors.title}</p>
                ) : null}
              </div>

              <fieldset className="form-group org-event-signup-mode">
                <legend>申込方式</legend>
                <label className="org-event-check">
                  <input
                    type="radio"
                    name="event-signup-mode"
                    checked={form.signup_mode === "registration"}
                    disabled={hasLottery}
                    onChange={() => setField("signup_mode", "registration")}
                  />
                  <span>参加申込あり（締切後に抽選も可）</span>
                </label>
                <label className="org-event-check">
                  <input
                    type="radio"
                    name="event-signup-mode"
                    checked={form.signup_mode === "announcement"}
                    disabled={hasLottery}
                    onChange={() => setField("signup_mode", "announcement")}
                  />
                  <span>告知のみ（申込・抽選なし）</span>
                </label>
              </fieldset>

              <div className="form-group">
                <label htmlFor="event-description">説明</label>
                <textarea
                  id="event-description"
                  value={form.description}
                  onChange={(e) => setField("description", e.target.value)}
                  rows={6}
                />
                {fieldErrors.description ? (
                  <p className="org-edit-field-error">{fieldErrors.description}</p>
                ) : null}
              </div>

              <div className="org-event-form__when">
                <div className="form-group">
                  <label htmlFor="event-starts-at">開始日時（日本時間）</label>
                  <input
                    id="event-starts-at"
                    type="datetime-local"
                    value={form.starts_at}
                    onChange={(e) => setField("starts_at", e.target.value)}
                    required
                  />
                  {fieldErrors.starts_at ? (
                    <p className="org-edit-field-error">{fieldErrors.starts_at}</p>
                  ) : null}
                </div>
                <div className="form-group">
                  <label htmlFor="event-ends-at">終了日時（日本時間）</label>
                  <input
                    id="event-ends-at"
                    type="datetime-local"
                    value={form.ends_at}
                    onChange={(e) => setField("ends_at", e.target.value)}
                    required
                  />
                  {fieldErrors.ends_at ? (
                    <p className="org-edit-field-error">{fieldErrors.ends_at}</p>
                  ) : null}
                </div>
              </div>

              <div className="form-group">
                <label htmlFor="event-venue-name">会場</label>
                <input
                  id="event-venue-name"
                  value={form.venue_name}
                  onChange={(e) => setField("venue_name", e.target.value)}
                  autoComplete="off"
                  required
                />
                {fieldErrors.venue_name ? (
                  <p className="org-edit-field-error">{fieldErrors.venue_name}</p>
                ) : null}
              </div>

              <div className="form-group">
                <label htmlFor="event-venue-address">住所（任意）</label>
                <input
                  id="event-venue-address"
                  value={form.venue_address}
                  onChange={(e) => setField("venue_address", e.target.value)}
                  autoComplete="street-address"
                />
                {fieldErrors.venue_address ? (
                  <p className="org-edit-field-error">{fieldErrors.venue_address}</p>
                ) : null}
              </div>

              {form.signup_mode === "registration" ? (
                <>
              <div className="form-group">
                <label htmlFor="event-registration-deadline">申込締切（任意・日本時間）</label>
                <input
                  id="event-registration-deadline"
                  type="datetime-local"
                  value={form.registration_deadline}
                  onChange={(e) => setField("registration_deadline", e.target.value)}
                />
                {fieldErrors.registration_deadline ? (
                  <p className="org-edit-field-error">{fieldErrors.registration_deadline}</p>
                ) : null}
              </div>

              <div className="form-group">
                <label className="org-event-check" htmlFor="event-registration-open">
                  <input
                    id="event-registration-open"
                    type="checkbox"
                    checked={form.registration_open}
                    disabled={hasLottery}
                    onChange={(e) => setField("registration_open", e.target.checked)}
                  />
                  <span>
                    {hasLottery
                      ? "抽選確定後は申し込みを再開できません"
                      : "申し込みを受け付ける"}
                  </span>
                </label>
              </div>
                </>
              ) : (
                <p className="org-event-privacy">
                  告知のみでは申込ボタンと抽選は使いません。早稲田祭の屋台・公演などに使えます。
                </p>
              )}

              <div className="org-event-form__actions">
                <button type="submit" className="btn-submit" disabled={busy}>
                  {busy ? "保存中…" : isEdit ? "変更を保存" : "下書きを保存"}
                </button>
                <Link className="org-edit-back" to={organizationEventManagePath(slug)}>
                  キャンセル
                </Link>
              </div>
            </form>
          </>
        )}
      </div>
    </div>
  );
}
