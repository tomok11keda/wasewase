import { useCallback, useEffect, useLayoutEffect, useRef, useState, type FormEvent } from "react";
import { Link, Navigate, useNavigate, useParams } from "react-router-dom";
import { ImagePickField } from "../components/ImagePickField";
import { FormSkeleton } from "../components/skeleton";
import { spaLoginPath } from "../features/auth/api";
import { OrganizationRequestError } from "../features/orgs/api";
import {
  canShowEventManage,
  emptyEventForm,
  EVENT_SIGNUP_MODE_OPTIONS,
  formFromOrganizationEvent,
  organizationEventErrorMessage,
  organizationEventManagePath,
  organizationEventPath,
  validateEventForm,
  type OrganizationEventForm,
} from "../features/orgs/orgEvents";
import { TokyoDateTimeFields } from "../features/orgs/TokyoDateTimeFields";
import { suggestedEndFromStart } from "../features/orgs/tokyoDateTime.ts";
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
  const endTouchedRef = useRef(false);
  const [form, setForm] = useState<OrganizationEventForm>(emptyEventForm());
  const [canManage, setCanManage] = useState(false);
  const [hasLottery, setHasLottery] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [imageFile, setImageFile] = useState<File | null>(null);
  const [existingImageUrl, setExistingImageUrl] = useState("");
  const [clearImage, setClearImage] = useState(false);
  const pageTitle = isEdit ? "イベントを編集" : "イベントを作成";

  useLayoutEffect(() => {
    nextRequestId(fetchGen);
    setForm(emptyEventForm());
    setCanManage(false);
    setHasLottery(false);
    setError(null);
    setFieldErrors({});
    setLoading(true);
    setImageFile(null);
    setExistingImageUrl("");
    setClearImage(false);
    endTouchedRef.current = false;
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
        setExistingImageUrl(event.image_url || "");
        setClearImage(false);
        setImageFile(null);
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
          ? await updateOrganizationEvent(slug, eventId, form, {
              image: imageFile,
              clearImage,
            })
          : await createOrganizationEvent(slug, form, imageFile);
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

  const setStartAt = (value: string) => {
    setForm((prev) => ({
      ...prev,
      starts_at: value,
      ends_at: suggestedEndFromStart({
        start: value,
        end: prev.ends_at,
        endTouched: endTouchedRef.current,
      }),
    }));
  };

  const setEndAt = (value: string) => {
    endTouchedRef.current = true;
    setField("ends_at", value);
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
                <div
                  className="org-event-signup-mode__options"
                  role="radiogroup"
                  aria-label="申込方式"
                >
                  {EVENT_SIGNUP_MODE_OPTIONS.map((option) => {
                    const selected = form.signup_mode === option.value;
                    return (
                      <label
                        key={option.value}
                        className={`org-event-choice${
                          selected ? " is-selected" : ""
                        }`}
                      >
                        <input
                          type="radio"
                          name="event-signup-mode"
                          value={option.value}
                          checked={selected}
                          disabled={hasLottery}
                          onChange={() => setField("signup_mode", option.value)}
                        />
                        <span className="org-event-choice__text">
                          <strong>{option.title}</strong>
                          <small>{option.description}</small>
                        </span>
                      </label>
                    );
                  })}
                </div>
              </fieldset>

              <div className="form-group">
                <label>イベント画像（任意）</label>
                {existingImageUrl && !clearImage && !imageFile ? (
                  <div className="org-event-image-edit">
                    <img
                      className="org-event-image-edit__preview"
                      src={existingImageUrl}
                      alt="現在のイベント画像"
                    />
                    <button
                      type="button"
                      className="btn btn-secondary"
                      disabled={busy}
                      onClick={() => {
                        setClearImage(true);
                        setImageFile(null);
                      }}
                    >
                      画像を削除
                    </button>
                  </div>
                ) : null}
                <ImagePickField
                  id="event-image"
                  value={imageFile}
                  onChange={(file) => {
                    setImageFile(file);
                    if (file) setClearImage(false);
                  }}
                  disabled={busy}
                  hint="JPEG / PNG / GIF / WebP（任意）"
                />
                {fieldErrors.image ? (
                  <p className="org-edit-field-error">{fieldErrors.image}</p>
                ) : null}
              </div>

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
                <TokyoDateTimeFields
                  id="event-starts-at"
                  legend="開始（日本時間）"
                  value={form.starts_at}
                  onChange={setStartAt}
                  required
                  error={fieldErrors.starts_at}
                />
                <TokyoDateTimeFields
                  id="event-ends-at"
                  legend="終了（日本時間）"
                  value={form.ends_at}
                  onChange={setEndAt}
                  required
                  error={fieldErrors.ends_at}
                />
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
              <TokyoDateTimeFields
                id="event-registration-deadline"
                legend="申込締切（任意・日本時間）"
                value={form.registration_deadline}
                onChange={(value) => setField("registration_deadline", value)}
                error={fieldErrors.registration_deadline}
              />

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
                  {busy
                    ? imageFile
                      ? "画像をアップロード中…"
                      : "保存中…"
                    : isEdit
                      ? "変更を保存"
                      : "下書きを保存"}
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
