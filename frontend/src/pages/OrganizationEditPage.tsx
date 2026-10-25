import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { Link, Navigate, useNavigate, useParams } from "react-router-dom";
import { BrowsePreviewNotice } from "../components/BrowsePreviewNotice";
import { ImagePickField } from "../components/ImagePickField";
import { spaLoginPath } from "../features/auth/api";
import {
  fetchOrganizationProfile,
  OrganizationRequestError,
  updateOrganizationProfile,
} from "../features/orgs/api";
import {
  formFromOrganization,
  ORGANIZATION_CATEGORIES,
  ORGANIZATION_DESCRIPTION_MAX,
  ORGANIZATION_NAME_MAX,
  organizationInitial,
  validateOrganizationAvatar,
  validateOrganizationProfileForm,
  type OrganizationProfileForm,
  type OrganizationProfilePayload,
} from "../features/orgs/orgProfile";
import { useAccount } from "../lib/accountContext";
import { isBrowsePreview, useSession } from "../lib/session";
import { FormSkeleton } from "../components/skeleton";
import {
  isLatestRequest,
  isSameUserScope,
  nextRequestId,
} from "../lib/userScopedResult";

function statusFromError(err: unknown): string {
  if (err instanceof OrganizationRequestError) return err.code;
  return "load_failed";
}

export function OrganizationEditPage() {
  const { slug } = useParams();
  const navigate = useNavigate();
  const { me, loading: sessionLoading } = useSession();
  const { refreshOrganizations } = useAccount();
  const browsePreview = isBrowsePreview(me);
  const sessionUserId =
    me?.authenticated && me.user?.id != null ? me.user.id : null;
  const userIdRef = useRef(sessionUserId);
  userIdRef.current = sessionUserId;
  const fetchGen = useRef(0);
  const [payload, setPayload] = useState<OrganizationProfilePayload | null>(
    null
  );
  const [form, setForm] = useState<OrganizationProfileForm | null>(null);
  const [avatar, setAvatar] = useState<File | null>(null);
  const [avatarError, setAvatarError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [permissionLost, setPermissionLost] = useState(false);

  const previewUrl = useMemo(
    () => (avatar ? URL.createObjectURL(avatar) : null),
    [avatar]
  );

  useEffect(() => {
    return () => {
      if (previewUrl) URL.revokeObjectURL(previewUrl);
    };
  }, [previewUrl]);

  useLayoutEffect(() => {
    nextRequestId(fetchGen);
    setPayload(null);
    setForm(null);
    setAvatar(null);
    setLoading(true);
    setLoadError(null);
    setError(null);
    setPermissionLost(false);
  }, [slug, sessionUserId]);

  const load = useCallback(async () => {
    if (!slug) {
      setLoadError("not_found");
      setLoading(false);
      return;
    }
    const gen = nextRequestId(fetchGen);
    const startedUserId = userIdRef.current;
    setLoading(true);
    setLoadError(null);
    try {
      const data = await fetchOrganizationProfile(slug);
      if (!isLatestRequest(fetchGen, gen)) return;
      if (!isSameUserScope(startedUserId, userIdRef.current)) return;
      setPayload(data);
      setForm(formFromOrganization(data.organization));
      setAvatar(null);
      setAvatarError(null);
    } catch (err) {
      if (!isLatestRequest(fetchGen, gen)) return;
      if (!isSameUserScope(startedUserId, userIdRef.current)) return;
      setPayload(null);
      setForm(null);
      setLoadError(statusFromError(err));
    } finally {
      if (isLatestRequest(fetchGen, gen)) setLoading(false);
    }
  }, [slug]);

  useEffect(() => {
    if (sessionLoading) return;
    if (browsePreview) {
      setLoading(false);
      setPayload(null);
      setForm(null);
      setLoadError(null);
      return;
    }
    if (!me?.authenticated) {
      navigate(spaLoginPath(`/app/orgs/${slug || ""}/edit`), { replace: true });
      return;
    }
    void load();
  }, [sessionLoading, browsePreview, me?.authenticated, load, navigate, slug, sessionUserId]);

  useEffect(() => {
    if (payload && !payload.can_manage) {
      void refreshOrganizations();
    }
  }, [payload, refreshOrganizations]);

  useEffect(() => {
    if (loadError === "not_found" || loadError === "forbidden") {
      void refreshOrganizations();
    }
  }, [loadError, refreshOrganizations]);

  if (!slug) {
    return <Navigate to="/" replace />;
  }

  const loginNext = `/app/orgs/${slug}/edit`;

  if (browsePreview) {
    return (
      <div className="org-edit-page" data-spa-page="団体を編集">
        <div className="main-inner">
          <BrowsePreviewNotice nextPath={loginNext}>
            団体プロフィールの編集はログイン後に利用できます。
          </BrowsePreviewNotice>
        </div>
      </div>
    );
  }

  if (loading || sessionLoading || !me?.authenticated) {
    return (
      <div className="org-edit-page" data-spa-page="団体を編集">
        <div className="main-inner">
          <FormSkeleton rows={5} />
        </div>
      </div>
    );
  }

  if (loadError === "unauthorized") {
    return (
      <div className="org-edit-page" data-spa-page="団体を編集">
        <div className="main-inner">
          <p>編集するにはログインが必要です。</p>
          <Link className="btn-submit" to={spaLoginPath(loginNext)}>
            ログイン
          </Link>
        </div>
      </div>
    );
  }

  if (loadError === "not_found" || (!payload && loadError)) {
    return (
      <div className="org-edit-page" data-spa-page="団体を編集">
        <div className="main-inner">
          <p>
            {loadError === "not_found"
              ? "この団体は見つからないか、表示できません。"
              : "団体プロフィールを読み込めませんでした。"}
          </p>
          {loadError !== "not_found" ? (
            <button
              type="button"
              className="btn-submit"
              onClick={() => void load()}
            >
              再試行
            </button>
          ) : (
            <Link className="org-edit-back" to="/">
              ホームへ戻る
            </Link>
          )}
        </div>
      </div>
    );
  }

  if (!payload || !form) {
    return (
      <div className="org-edit-page" data-spa-page="団体を編集">
        <div className="main-inner">
          <p>団体プロフィールを読み込めませんでした。</p>
        </div>
      </div>
    );
  }

  if (!payload.can_manage) {
    return (
      <div className="org-edit-page" data-spa-page="団体を編集">
        <div className="main-inner">
          <p>この団体を編集する権限がありません。</p>
          <Link className="org-edit-back" to={`/orgs/${payload.organization.slug}`}>
            プロフィールへ戻る
          </Link>
        </div>
      </div>
    );
  }

  const org = payload.organization;
  const avatarSrc = previewUrl || org.avatar_url || "";
  const fieldError = (key: string) => fieldErrors[key] || null;

  const onAvatarChange = (file: File | null) => {
    if (!file) {
      setAvatar(null);
      setAvatarError(null);
      return;
    }
    const message = validateOrganizationAvatar(file);
    if (message) {
      setAvatar(null);
      setAvatarError(message);
      return;
    }
    setAvatar(file);
    setAvatarError(null);
  };

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault();
    if (busy || permissionLost) return;
    const nextErrors = validateOrganizationProfileForm(form);
    if (avatar) {
      const imageMessage = validateOrganizationAvatar(avatar);
      if (imageMessage) nextErrors.avatar = imageMessage;
    }
    if (Object.keys(nextErrors).length) {
      setFieldErrors(nextErrors);
      setError("入力内容を確認してください。");
      return;
    }
    setBusy(true);
    setError(null);
    setFieldErrors({});
    try {
      const updated = await updateOrganizationProfile(org.slug, form, avatar);
      setPayload(updated);
      setForm(formFromOrganization(updated.organization));
      setAvatar(null);
      navigate(`/orgs/${updated.organization.slug}`, { replace: true });
    } catch (err) {
      if (err instanceof OrganizationRequestError) {
        setFieldErrors(err.fieldErrors);
        setError(err.message);
        if (err.code === "forbidden") {
          setPermissionLost(true);
          void refreshOrganizations();
        }
      } else {
        setError("保存に失敗しました。入力内容は保持されています。");
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="org-edit-page" data-spa-page="団体を編集">
      <div className="main-inner">
        <p className="form-lead">
          公開プロフィールを編集します。識別子や公開状態はここでは変更できません。
        </p>
        {error ? <p className="org-edit-error">{error}</p> : null}
        {permissionLost ? (
          <p className="org-edit-error">
            編集権限がなくなりました。内容は残していますが、保存はできません。
          </p>
        ) : null}
        <form className="form-card" onSubmit={(event) => void onSubmit(event)}>
          <div className="form-group">
            <span className="org-edit-avatar-label">団体アイコン</span>
            <div className="org-edit-avatar-row">
              {avatarSrc ? (
                <img
                  className="org-edit-avatar-preview"
                  src={avatarSrc}
                  alt=""
                />
              ) : (
                <span className="org-edit-avatar-preview is-empty">
                  {organizationInitial(form.name || org.name)}
                </span>
              )}
              <ImagePickField
                id="org-avatar"
                value={avatar}
                onChange={onAvatarChange}
                disabled={busy || permissionLost}
                hint="JPEG / PNG / GIF / WebP（5MBまで）。保存するまで公開画像は変わりません。"
                allowClear={Boolean(avatar)}
              />
            </div>
            {avatarError || fieldError("avatar") ? (
              <p className="org-edit-field-error">
                {avatarError || fieldError("avatar")}
              </p>
            ) : null}
          </div>

          <div className="form-group">
            <label htmlFor="org-name">団体名</label>
            <input
              id="org-name"
              value={form.name}
              maxLength={ORGANIZATION_NAME_MAX}
              disabled={busy || permissionLost}
              onChange={(event) =>
                setForm({ ...form, name: event.target.value })
              }
              required
            />
            <p className="org-edit-counter">
              {form.name.trim().length}/{ORGANIZATION_NAME_MAX}
            </p>
            {fieldError("name") ? (
              <p className="org-edit-field-error">{fieldError("name")}</p>
            ) : null}
          </div>

          <div className="form-group">
            <label htmlFor="org-category">カテゴリ</label>
            <select
              id="org-category"
              value={form.category}
              disabled={busy || permissionLost}
              onChange={(event) =>
                setForm({ ...form, category: event.target.value })
              }
            >
              {ORGANIZATION_CATEGORIES.map((item) => (
                <option key={item.value} value={item.value}>
                  {item.label}
                </option>
              ))}
            </select>
            {fieldError("category") ? (
              <p className="org-edit-field-error">{fieldError("category")}</p>
            ) : null}
          </div>

          <div className="form-group">
            <label htmlFor="org-description">説明文</label>
            <textarea
              id="org-description"
              rows={6}
              value={form.description}
              maxLength={ORGANIZATION_DESCRIPTION_MAX}
              disabled={busy || permissionLost}
              onChange={(event) =>
                setForm({ ...form, description: event.target.value })
              }
            />
            <p className="org-edit-counter">
              {form.description.trim().length}/{ORGANIZATION_DESCRIPTION_MAX}
            </p>
            {fieldError("description") ? (
              <p className="org-edit-field-error">{fieldError("description")}</p>
            ) : null}
          </div>

          <div className="form-group">
            <label htmlFor="org-instagram">Instagram URL</label>
            <input
              id="org-instagram"
              type="url"
              inputMode="url"
              value={form.instagram_url}
              disabled={busy || permissionLost}
              placeholder="https://instagram.com/..."
              onChange={(event) =>
                setForm({ ...form, instagram_url: event.target.value })
              }
            />
            {fieldError("instagram_url") ? (
              <p className="org-edit-field-error">
                {fieldError("instagram_url")}
              </p>
            ) : null}
          </div>

          <div className="form-group">
            <label htmlFor="org-website">Webサイト URL</label>
            <input
              id="org-website"
              type="url"
              inputMode="url"
              value={form.website_url}
              disabled={busy || permissionLost}
              placeholder="https://"
              onChange={(event) =>
                setForm({ ...form, website_url: event.target.value })
              }
            />
            {fieldError("website_url") ? (
              <p className="org-edit-field-error">{fieldError("website_url")}</p>
            ) : null}
          </div>

          <button
            className="btn-submit"
            type="submit"
            disabled={busy || permissionLost}
          >
            {busy ? "保存中…" : "保存する"}
          </button>
        </form>
      </div>
    </div>
  );
}
