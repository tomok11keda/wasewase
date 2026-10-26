import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type FormEvent,
} from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { BrowsePreviewNotice } from "../components/BrowsePreviewNotice";
import { ImagePickField } from "../components/ImagePickField";
import { FormSkeleton } from "../components/skeleton";
import { spaLoginPath } from "../features/auth/api";
import { invalidateOwnProfileCacheAfterEdit } from "../features/profile/ownProfileCache";
import {
  formFromOwnProfile,
  isOwnProfileFormDirty,
  OWN_PROFILE_NAME_MAX,
  validateOwnProfileAvatar,
  validateOwnProfileForm,
  type OwnProfileForm,
  type OwnProfilePayload,
} from "../features/profile/meProfile";
import {
  fetchOwnProfile,
  OwnProfileRequestError,
  updateOwnProfile,
} from "../features/profile/meProfileApi";
import { ProfileLinksEditor } from "../features/profileLinks/ProfileLinksEditor";
import { isBrowsePreview, useSession } from "../lib/session";
import {
  isLatestRequest,
  isSameUserScope,
  nextRequestId,
} from "../lib/userScopedResult";
import {
  confirmDiscardUnsavedChanges,
  isSpaDocumentLink,
  setUnsavedChangesGuard,
  spaLinkLeavesPath,
} from "../lib/unsavedChangesGuard";

function statusFromError(err: unknown): string {
  if (err instanceof OwnProfileRequestError) return err.code;
  return "load_failed";
}

export function ProfileEditPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const { me, loading: sessionLoading, refresh } = useSession();
  const browsePreview = isBrowsePreview(me);
  const sessionUserId =
    me?.authenticated && me.user?.id != null ? me.user.id : null;
  const userIdRef = useRef(sessionUserId);
  userIdRef.current = sessionUserId;
  const fetchGen = useRef(0);
  const [payload, setPayload] = useState<OwnProfilePayload | null>(null);
  const [form, setForm] = useState<OwnProfileForm | null>(null);
  const [original, setOriginal] = useState<OwnProfileForm | null>(null);
  const [avatar, setAvatar] = useState<File | null>(null);
  const [avatarError, setAvatarError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const savingOk = useRef(false);

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
    setOriginal(null);
    setAvatar(null);
    setAvatarError(null);
    setFieldErrors({});
    setError(null);
    setLoadError(null);
    setLoading(true);
    savingOk.current = false;
  }, [sessionUserId]);

  const load = useCallback(async () => {
    const gen = nextRequestId(fetchGen);
    const startedUserId = userIdRef.current;
    setLoading(true);
    setLoadError(null);
    try {
      const data = await fetchOwnProfile();
      if (!isLatestRequest(fetchGen, gen)) return;
      if (!isSameUserScope(startedUserId, userIdRef.current)) return;
      if (startedUserId != null && data.profile.id !== startedUserId) return;
      const nextForm = formFromOwnProfile(data.profile);
      setPayload(data);
      setForm(nextForm);
      setOriginal(nextForm);
      setAvatar(null);
      setAvatarError(null);
    } catch (err) {
      if (!isLatestRequest(fetchGen, gen)) return;
      if (!isSameUserScope(startedUserId, userIdRef.current)) return;
      setPayload(null);
      setForm(null);
      setOriginal(null);
      setLoadError(statusFromError(err));
    } finally {
      if (isLatestRequest(fetchGen, gen)) setLoading(false);
    }
  }, []);

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
      navigate(spaLoginPath("/app/settings/profile"), { replace: true });
      return;
    }
    void load();
  }, [
    sessionLoading,
    browsePreview,
    me?.authenticated,
    load,
    navigate,
    sessionUserId,
  ]);

  const dirty =
    Boolean(form && original && isOwnProfileFormDirty(form, original, avatar));
  const dirtyRef = useRef(dirty);
  dirtyRef.current = dirty;

  useEffect(() => {
    setUnsavedChangesGuard(() =>
      confirmDiscardUnsavedChanges({
        dirty: dirtyRef.current,
        bypass: savingOk.current,
      })
    );
    return () => setUnsavedChangesGuard(null);
  }, []);

  useEffect(() => {
    if (!dirty || busy || savingOk.current) return;
    const onBeforeUnload = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    const onDocumentClick = (event: MouseEvent) => {
      if (event.defaultPrevented || event.button !== 0) return;
      if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) {
        return;
      }
      const target = event.target;
      if (!(target instanceof Element)) return;
      const anchor = target.closest("a[href]");
      if (!(anchor instanceof HTMLAnchorElement)) return;
      if (!isSpaDocumentLink(anchor)) return;
      if (!spaLinkLeavesPath(anchor, location.pathname)) return;
      if (
        confirmDiscardUnsavedChanges({
          dirty: dirtyRef.current,
          bypass: savingOk.current,
        })
      ) {
        return;
      }
      event.preventDefault();
      event.stopPropagation();
    };
    window.addEventListener("beforeunload", onBeforeUnload);
    document.addEventListener("click", onDocumentClick, true);
    return () => {
      window.removeEventListener("beforeunload", onBeforeUnload);
      document.removeEventListener("click", onDocumentClick, true);
    };
  }, [dirty, busy, location.pathname]);

  const loginNext = "/app/settings/profile";

  if (browsePreview) {
    return (
      <div className="org-edit-page" data-spa-page="プロフィール設定">
        <div className="main-inner">
          <BrowsePreviewNotice nextPath={loginNext}>
            プロフィールの編集はログイン後に利用できます。
          </BrowsePreviewNotice>
        </div>
      </div>
    );
  }

  if (loading || sessionLoading || !me?.authenticated) {
    return (
      <div className="org-edit-page" data-spa-page="プロフィール設定">
        <div className="main-inner">
          <FormSkeleton rows={6} />
        </div>
      </div>
    );
  }

  if (loadError === "unauthorized") {
    return (
      <div className="org-edit-page" data-spa-page="プロフィール設定">
        <div className="main-inner">
          <p>編集するにはログインが必要です。</p>
          <Link className="btn-submit" to={spaLoginPath(loginNext)}>
            ログイン
          </Link>
        </div>
      </div>
    );
  }

  if (loadError || !payload || !form) {
    return (
      <div className="org-edit-page" data-spa-page="プロフィール設定">
        <div className="main-inner">
          <p>プロフィールを読み込めませんでした。</p>
          <button
            type="button"
            className="btn-submit"
            onClick={() => void load()}
          >
            再試行
          </button>
        </div>
      </div>
    );
  }

  const avatarSrc = previewUrl || payload.profile.avatar_url || "";
  const fieldError = (key: string) => fieldErrors[key] || null;
  const departmentChoices = payload.choices.department;
  const gradeChoices = payload.choices.grade;

  const onAvatarChange = (file: File | null) => {
    if (!file) {
      setAvatar(null);
      setAvatarError(null);
      return;
    }
    const message = validateOwnProfileAvatar(file);
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
    if (busy) return;
    const nextErrors = validateOwnProfileForm(form);
    if (avatar) {
      const imageMessage = validateOwnProfileAvatar(avatar);
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
      const updated = await updateOwnProfile(form, avatar);
      savingOk.current = true;
      setPayload(updated);
      const nextForm = formFromOwnProfile(updated.profile);
      setForm(nextForm);
      setOriginal(nextForm);
      setAvatar(null);
      invalidateOwnProfileCacheAfterEdit(updated.profile.id);
      await refresh();
      navigate(`/users/${updated.profile.id}/posts`, { replace: true });
    } catch (err) {
      if (err instanceof OwnProfileRequestError) {
        setFieldErrors(err.fieldErrors);
        setError(err.message);
        if (err.code === "unauthorized") {
          navigate(spaLoginPath(loginNext), { replace: true });
        }
      } else {
        setError("保存に失敗しました。入力内容は保持されています。");
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="org-edit-page" data-spa-page="プロフィール設定">
      <div className="main-inner">
        <p className="form-lead">
          <strong>表示名</strong>は投稿などに、
          <strong>@ユーザー名</strong>はプロフィールの @
          の後ろに表示されます。英数字と _ のみ、3〜30文字です。
        </p>
        {error ? <p className="org-edit-error">{error}</p> : null}
        <form className="form-card" onSubmit={(event) => void onSubmit(event)}>
          <div className="form-group">
            <span className="org-edit-avatar-label">プロフィール画像</span>
            <div className="org-edit-avatar-row profile-edit-avatar">
              {avatarSrc ? (
                <img
                  className="org-edit-avatar-preview"
                  src={avatarSrc}
                  alt=""
                />
              ) : (
                <span className="org-edit-avatar-preview is-empty">
                  {payload.profile.initial || "?"}
                </span>
              )}
              <ImagePickField
                id="own-avatar"
                value={avatar}
                onChange={onAvatarChange}
                disabled={busy}
                hint="JPEG / PNG / GIF / WebP、5MB以下。未設定の場合は名前の頭文字が表示されます。"
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
            <label htmlFor="own-name">表示名</label>
            <input
              id="own-name"
              value={form.name}
              maxLength={OWN_PROFILE_NAME_MAX}
              autoComplete="nickname"
              disabled={busy}
              placeholder="例：田中太郎"
              onChange={(event) =>
                setForm({ ...form, name: event.target.value })
              }
            />
            <p className="org-edit-hint">
              タイムラインなどに表示される名前です。空欄の場合は
              @ユーザー名が表示されます。
            </p>
            {fieldError("name") ? (
              <p className="org-edit-field-error">{fieldError("name")}</p>
            ) : null}
          </div>

          <div className="form-group">
            <label htmlFor="own-user-id">@ユーザー名</label>
            <input
              id="own-user-id"
              value={form.user_id}
              autoCapitalize="none"
              autoCorrect="off"
              spellCheck={false}
              autoComplete="off"
              disabled={busy}
              placeholder="例：tanaka_taro"
              onChange={(event) =>
                setForm({ ...form, user_id: event.target.value })
              }
              required
            />
            <p className="org-edit-hint">
              英数字とアンダースコア（_）のみ、3〜30文字。他のユーザーに @
              付きで表示されます。
            </p>
            {fieldError("user_id") ? (
              <p className="org-edit-field-error">{fieldError("user_id")}</p>
            ) : null}
          </div>

          <div className="form-group">
            <label htmlFor="own-bio">自己紹介</label>
            <textarea
              id="own-bio"
              rows={4}
              value={form.bio}
              disabled={busy}
              placeholder="自己紹介や取引の希望など（任意）"
              onChange={(event) =>
                setForm({ ...form, bio: event.target.value })
              }
            />
            {fieldError("bio") ? (
              <p className="org-edit-field-error">{fieldError("bio")}</p>
            ) : null}
          </div>

          <ProfileLinksEditor
            drafts={form.links || []}
            disabled={busy}
            errors={fieldErrors}
            onChange={(links) => setForm({ ...form, links })}
          />

          <div className="form-group">
            <label htmlFor="own-department">学部</label>
            <select
              id="own-department"
              value={form.department}
              disabled={busy}
              onChange={(event) =>
                setForm({ ...form, department: event.target.value })
              }
            >
              {departmentChoices.length ? (
                departmentChoices.map((item) => (
                  <option key={item.value || "blank"} value={item.value}>
                    {item.label}
                  </option>
                ))
              ) : (
                <option value="">未設定</option>
              )}
            </select>
            {fieldError("department") ? (
              <p className="org-edit-field-error">{fieldError("department")}</p>
            ) : null}
          </div>

          <div className="form-group">
            <label htmlFor="own-grade">学年</label>
            <select
              id="own-grade"
              value={form.grade}
              disabled={busy}
              onChange={(event) =>
                setForm({ ...form, grade: event.target.value })
              }
            >
              {gradeChoices.length ? (
                gradeChoices.map((item) => (
                  <option key={item.value || "blank"} value={item.value}>
                    {item.label}
                  </option>
                ))
              ) : (
                <option value="">未設定</option>
              )}
            </select>
            {fieldError("grade") ? (
              <p className="org-edit-field-error">{fieldError("grade")}</p>
            ) : null}
          </div>

          <button className="btn-submit" type="submit" disabled={busy}>
            {busy ? "保存中…" : "保存する"}
          </button>
        </form>
      </div>
    </div>
  );
}
