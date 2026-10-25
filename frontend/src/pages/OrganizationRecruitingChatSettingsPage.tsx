import { useCallback, useEffect, useLayoutEffect, useRef, useState, type FormEvent } from "react";
import { Link, Navigate, useNavigate, useParams } from "react-router-dom";
import { spaLoginPath } from "../features/auth/api";
import { OrganizationRequestError } from "../features/orgs/api";
import { RecruitingManageNav } from "../features/orgs/RecruitingManageNav";
import {
  RECRUITING_CHAT_DESCRIPTION_MAX,
  RECRUITING_CHAT_NAME_MAX,
  autoApproveConfirmMessage,
  canShowRecruitingManageNav,
  formFromRecruitingChat,
  recruitingChatPath,
  shouldConfirmAutoApprove,
  validateRecruitingChatForm,
  type RecruitingChat,
  type RecruitingChatForm,
} from "../features/orgs/recruitingChat";
import {
  createRecruitingChat,
  fetchRecruitingChat,
  updateRecruitingChat,
} from "../features/orgs/recruitingChatApi";
import { isBrowsePreview, useSession } from "../lib/session";
import { FormSkeleton } from "../components/skeleton";
import {
  isLatestRequest,
  isSameUserScope,
  nextRequestId,
} from "../lib/userScopedResult";

function errorText(err: unknown, fallback: string): string {
  if (err instanceof OrganizationRequestError) return err.message;
  if (err instanceof Error && err.message) return err.message;
  return fallback;
}

export function OrganizationRecruitingChatSettingsPage() {
  const { slug } = useParams();
  const navigate = useNavigate();
  const { me, loading: sessionLoading } = useSession();
  const browsePreview = isBrowsePreview(me);
  const sessionUserId =
    me?.authenticated && me.user?.id != null ? me.user.id : null;
  const userIdRef = useRef(sessionUserId);
  userIdRef.current = sessionUserId;
  const fetchGen = useRef(0);
  const [chat, setChat] = useState<RecruitingChat | null>(null);
  const [canCreate, setCanCreate] = useState(false);
  const [canManage, setCanManage] = useState(false);
  const [form, setForm] = useState<RecruitingChatForm>(formFromRecruitingChat(null));
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const busyRef = useRef(false);

  useLayoutEffect(() => {
    nextRequestId(fetchGen);
    setChat(null);
    setCanCreate(false);
    setCanManage(false);
    setForm(formFromRecruitingChat(null));
    setLoading(true);
    setLoadError(null);
    setError(null);
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
      const envelope = await fetchRecruitingChat(slug);
      if (!isLatestRequest(fetchGen, gen)) return;
      if (!isSameUserScope(startedUserId, userIdRef.current)) return;
      setChat(envelope.recruiting_chat);
      setCanCreate(envelope.can_create);
      setCanManage(envelope.can_manage || Boolean(envelope.recruiting_chat?.can_manage));
      setForm(formFromRecruitingChat(envelope.recruiting_chat));
    } catch (err) {
      if (!isLatestRequest(fetchGen, gen)) return;
      if (!isSameUserScope(startedUserId, userIdRef.current)) return;
      setChat(null);
      setCanCreate(false);
      setCanManage(false);
      setLoadError(
        err instanceof OrganizationRequestError ? err.code : "load_failed"
      );
    } finally {
      if (isLatestRequest(fetchGen, gen)) setLoading(false);
    }
  }, [slug]);

  useEffect(() => {
    if (sessionLoading || browsePreview) return;
    void load();
  }, [sessionLoading, browsePreview, load, sessionUserId]);

  if (!slug) return <Navigate to="/" replace />;
  const loginNext = `/app/organizations/${slug}/recruiting-chat/settings`;

  if (browsePreview || (!sessionLoading && !me?.authenticated)) {
    return (
      <div className="org-edit-page" data-spa-page="団体チャット設定">
        <div className="main-inner">
          <p>団体チャットの設定にはログインが必要です。</p>
          <Link className="btn btn-primary" to={spaLoginPath(loginNext)}>
            ログイン
          </Link>
        </div>
      </div>
    );
  }

  if (loading || sessionLoading) {
    return (
      <div className="org-edit-page org-recruiting-manage-page" data-spa-page="団体チャット設定">
        <div className="main-inner">
          <FormSkeleton />
        </div>
      </div>
    );
  }

  if (loadError === "unauthorized") {
    return <Navigate to={spaLoginPath(loginNext)} replace />;
  }

  if (loadError === "not_found") {
    return (
      <div className="org-edit-page" data-spa-page="団体チャット設定">
        <div className="main-inner">
          <p>この団体は見つからないか、表示できません。</p>
          <Link to={`/orgs/${slug}`}>団体プロフィールへ戻る</Link>
        </div>
      </div>
    );
  }

  if (!canManage && !canCreate) {
    return (
      <div className="org-edit-page" data-spa-page="団体チャット設定">
        <div className="main-inner">
          <p>団体チャットを管理する権限がありません。</p>
          <Link to={`/orgs/${slug}`}>団体プロフィールへ戻る</Link>
        </div>
      </div>
    );
  }

  const isCreate = !chat && canCreate;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (busyRef.current) return;
    const errors = validateRecruitingChatForm(form);
    setFieldErrors(errors);
    if (Object.keys(errors).length) return;

    let confirmAutoApprove = false;
    if (!isCreate && shouldConfirmAutoApprove(chat, form.join_mode)) {
      const pending = chat?.pending_count || 0;
      if (!window.confirm(autoApproveConfirmMessage(pending))) return;
      confirmAutoApprove = true;
    }

    busyRef.current = true;
    setBusy(true);
    setError(null);
    try {
      const next = isCreate
        ? await createRecruitingChat(slug, form)
        : await updateRecruitingChat(slug, {
            ...form,
            confirm_auto_approve: confirmAutoApprove,
          });
      setChat(next);
      setForm(formFromRecruitingChat(next));
      navigate(recruitingChatPath(slug));
    } catch (err) {
      if (
        err instanceof OrganizationRequestError &&
        err.code === "confirm_auto_approve_required"
      ) {
        const pending = Number(err.extra.pending_count || chat?.pending_count || 0);
        if (window.confirm(autoApproveConfirmMessage(pending))) {
          try {
            const next = await updateRecruitingChat(slug, {
              ...form,
              confirm_auto_approve: true,
            });
            setChat(next);
            setForm(formFromRecruitingChat(next));
            navigate(recruitingChatPath(slug));
            return;
          } catch (retryErr) {
            setError(errorText(retryErr, "設定を保存できませんでした。"));
            return;
          }
        }
        setError("自動承認の確認が必要なため、設定は変更していません。");
        return;
      }
      setError(errorText(err, "設定を保存できませんでした。"));
    } finally {
      busyRef.current = false;
      setBusy(false);
    }
  };

  return (
    <div className="org-edit-page org-recruiting-manage-page" data-spa-page="団体チャット設定">
      <div className="main-inner">
        <p className="form-lead">
          {isCreate
            ? "団体につき有効な団体チャットは1件です。作成後、学生が団体プロフィールから参加できます。"
            : "チャット名・説明・参加方式・募集状態を変更できます。"}
        </p>
        {!isCreate &&
        canShowRecruitingManageNav({ hydrated: true, canManage }) ? (
          <RecruitingManageNav slug={slug} pendingCount={chat?.pending_count} />
        ) : null}
        <form className="form-card" onSubmit={(e) => void submit(e)}>
          {error ? (
            <p className="org-edit-error" role="alert">
              {error}
            </p>
          ) : null}
          <div className="form-group">
            <label htmlFor="recruiting-name">チャット名</label>
            <input
              id="recruiting-name"
              value={form.name}
              maxLength={RECRUITING_CHAT_NAME_MAX}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              autoComplete="off"
            />
            {fieldErrors.name ? (
              <p className="org-edit-field-error">{fieldErrors.name}</p>
            ) : null}
          </div>
          <div className="form-group">
            <label htmlFor="recruiting-description">説明</label>
            <textarea
              id="recruiting-description"
              value={form.description}
              maxLength={RECRUITING_CHAT_DESCRIPTION_MAX}
              rows={5}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
            />
            <p className="org-edit-counter">
              {form.description.length}/{RECRUITING_CHAT_DESCRIPTION_MAX}
            </p>
            {fieldErrors.description ? (
              <p className="org-edit-field-error">{fieldErrors.description}</p>
            ) : null}
          </div>
          <div className="form-group">
            <label htmlFor="recruiting-join-mode">参加方式</label>
            <select
              id="recruiting-join-mode"
              value={form.join_mode}
              onChange={(e) =>
                setForm({
                  ...form,
                  join_mode: e.target.value === "approval" ? "approval" : "open",
                })
              }
            >
              <option value="open">自由参加</option>
              <option value="approval">承認制</option>
            </select>
            {chat?.would_auto_approve_on_open && form.join_mode === "open" ? (
              <p className="org-recruiting-warn">
                承認待ちが{chat.pending_count || 0}件あります。自由参加に切り替えると全員が自動承認されます。
              </p>
            ) : null}
          </div>
          <div className="form-group">
            <label htmlFor="recruiting-listing">募集状態</label>
            <select
              id="recruiting-listing"
              value={form.listing_status}
              onChange={(e) =>
                setForm({
                  ...form,
                  listing_status: e.target.value === "closed" ? "closed" : "open",
                })
              }
            >
              <option value="open">募集中</option>
              <option value="closed">募集停止</option>
            </select>
          </div>
          <button type="submit" className="btn-submit" disabled={busy}>
            {busy ? "保存中…" : isCreate ? "作成する" : "保存する"}
          </button>
        </form>
        <Link className="org-edit-back" to={`/orgs/${slug}`}>
          団体プロフィールへ戻る
        </Link>
      </div>
    </div>
  );
}
