import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useSession } from "../lib/session";
import { spaLoginPath } from "../features/auth/api";
import { deleteLinkedProfile } from "../features/linkedProfiles/api";
import { linkedProfilesFromMe } from "../features/linkedProfiles/linkedProfiles";
import {
  fetchProfile,
  updatePrivacy,
} from "../features/profile/api";
import { invalidateOwnProfileCacheAfterEdit } from "../features/profile/ownProfileCache";
import { SettingsSkeleton } from "../components/skeleton";
import {
  isLatestRequest,
  isSameUserScope,
  nextRequestId,
} from "../lib/userScopedResult";

export function SettingsPage() {
  const { me, loading: sessionLoading, setMeFromAuth } = useSession();
  const navigate = useNavigate();
  const sessionUserId =
    me?.authenticated && me.user?.id != null ? me.user.id : null;
  const userIdRef = useRef(sessionUserId);
  userIdRef.current = sessionUserId;
  const prevUserIdRef = useRef(sessionUserId);
  const fetchGen = useRef(0);
  const [isPrivate, setIsPrivate] = useState(false);
  const [loading, setLoading] = useState(true);
  const [privacyReady, setPrivacyReady] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savedMsg, setSavedMsg] = useState<string | null>(null);
  const [deleteBusy, setDeleteBusy] = useState(false);
  const profiles = linkedProfilesFromMe(me);
  const hasSibling = profiles.length > 1;
  const currentHandle = me?.user?.username || "";

  const resetPrivacy = useCallback(() => {
    nextRequestId(fetchGen);
    setIsPrivate(false);
    setPrivacyReady(false);
    setLoading(true);
    setError(null);
    setSavedMsg(null);
  }, []);

  useLayoutEffect(() => {
    if (prevUserIdRef.current === sessionUserId) return;
    prevUserIdRef.current = sessionUserId;
    resetPrivacy();
  }, [sessionUserId, resetPrivacy]);

  const load = useCallback(async () => {
    if (sessionUserId == null) return;
    const gen = nextRequestId(fetchGen);
    const startedUserId = userIdRef.current;
    setLoading(true);
    setError(null);
    try {
      const data = await fetchProfile(sessionUserId);
      if (!isLatestRequest(fetchGen, gen)) return;
      if (!isSameUserScope(startedUserId, userIdRef.current)) return;
      setIsPrivate(Boolean(data.is_private));
      setPrivacyReady(true);
      setError(null);
    } catch (err) {
      if (!isLatestRequest(fetchGen, gen)) return;
      if (!isSameUserScope(startedUserId, userIdRef.current)) return;
      setPrivacyReady(false);
      setIsPrivate(false);
      setError(err instanceof Error ? err.message : "load_failed");
    } finally {
      if (isLatestRequest(fetchGen, gen)) setLoading(false);
    }
  }, [sessionUserId]);

  useEffect(() => {
    if (sessionLoading) return;
    if (!me?.authenticated || !me.user) {
      navigate(spaLoginPath("/app/settings"), { replace: true });
      return;
    }
    void load();
  }, [sessionLoading, me?.authenticated, sessionUserId, navigate, load]);

  const onChangePrivacy = async (next: boolean) => {
    if (!privacyReady || busy || next === isPrivate) return;
    setBusy(true);
    setSavedMsg(null);
    setError(null);
    try {
      const result = await updatePrivacy(next);
      if (me?.user?.id) invalidateOwnProfileCacheAfterEdit(me.user.id);
      setIsPrivate(result.is_private);
      setSavedMsg(
        result.is_private
          ? "非公開アカウントに変更しました。"
          : "公開アカウントに変更しました。"
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存に失敗しました");
    } finally {
      setBusy(false);
    }
  };

  const showSkeleton = sessionLoading || (!privacyReady && loading);

  const runDelete = async (entireIdentity: boolean) => {
    if (deleteBusy) return;
    const confirmed = window.confirm(
      entireIdentity
        ? "WaseWaseから完全退会しますか？紐づくすべてのプロフィールが削除されます。"
        : hasSibling
          ? `@${currentHandle} を削除しますか？もう一方のプロフィールは残ります。`
          : `@${currentHandle} を削除して WaseWase を退会しますか？この操作は取り消せません。`
    );
    if (!confirmed) return;
    setDeleteBusy(true);
    setError(null);
    try {
      const { res, data } = await deleteLinkedProfile({ entireIdentity });
      if (!res.ok || !data.ok) {
        setError(data.message || "削除できませんでした。");
        return;
      }
      if (data.me) setMeFromAuth(data.me);
      if (!data.me?.authenticated) {
        navigate("/login", { replace: true });
        return;
      }
      setSavedMsg(
        entireIdentity
          ? "退会が完了しました。"
          : `@${currentHandle} を削除しました。`
      );
    } catch {
      setError("削除できませんでした。");
    } finally {
      setDeleteBusy(false);
    }
  };

  return (
    <div className="settings-page" data-spa-page="設定">
      <div className="main-inner">
        {error ? (
          <p className="settings-flash settings-flash--error">
            {error}
            {!privacyReady ? (
              <>
                {" "}
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={() => void load()}
                >
                  再試行
                </button>
              </>
            ) : null}
          </p>
        ) : null}
        {savedMsg ? (
          <p className="settings-flash settings-flash--ok">{savedMsg}</p>
        ) : null}

        {showSkeleton ? (
          <SettingsSkeleton />
        ) : (
          <section className="settings-card">
            <h2>アカウントの公開設定</h2>
            <p className="settings-lead">
              {!privacyReady
                ? "公開設定を読み込めませんでした。しばらくしてから再度お試しください。"
                : isPrivate
                  ? "承認したフォロワーだけがあなたの投稿や出品を見ることができます。"
                  : "すべての早稲田生があなたの投稿や出品を見ることができます。"}
            </p>

            <fieldset
              className="settings-privacy"
              disabled={!privacyReady || busy}
            >
              <legend className="visually-hidden">公開設定</legend>
              <label className="settings-radio">
                <input
                  type="radio"
                  name="account_privacy"
                  checked={privacyReady && !isPrivate}
                  disabled={!privacyReady || busy}
                  onChange={() => void onChangePrivacy(false)}
                />
                <span>
                  <strong>公開アカウント</strong>
                  <small>誰でもフォローでき、投稿・出品を閲覧できます。</small>
                </span>
              </label>
              <label className="settings-radio">
                <input
                  type="radio"
                  name="account_privacy"
                  checked={privacyReady && isPrivate}
                  disabled={!privacyReady || busy}
                  onChange={() => void onChangePrivacy(true)}
                />
                <span>
                  <strong>非公開アカウント</strong>
                  <small>
                    フォローにはリクエストが必要で、承認した人だけが投稿・出品を見られます。
                  </small>
                </span>
              </label>
            </fieldset>
          </section>
        )}

        <section className="settings-card">
          <h2>その他の設定</h2>
          <ul className="more-list settings-classic-list">
            <li>
              <a className="more-link" href="/mypage/settings/blocked/">
                ブロック一覧
                <small className="more-link-note">（従来ページ）</small>
              </a>
            </li>
            <li>
              <button
                type="button"
                className="more-link more-link-button"
                disabled={deleteBusy}
                onClick={() => void runDelete(false)}
              >
                {hasSibling
                  ? `@${currentHandle} を削除`
                  : "アカウントを削除"}
              </button>
            </li>
            {hasSibling ? (
              <li>
                <button
                  type="button"
                  className="more-link more-link-button"
                  disabled={deleteBusy}
                  onClick={() => void runDelete(true)}
                >
                  WaseWaseから完全退会
                </button>
              </li>
            ) : null}
            <li>
              <a className="more-link" href="/mypage/settings/">
                退会など（従来ページ）
                <small className="more-link-note">（従来ページ）</small>
              </a>
            </li>
            {me?.is_staff || me?.is_superuser ? (
              <>
                <li>
                  <Link className="more-link" to="/internal/push-diag">
                    内部: プッシュ診断
                  </Link>
                </li>
                <li>
                  <Link className="more-link" to="/dm?chat_kb_diag=1">
                    内部: チャットKB診断
                    <small className="more-link-note">
                      会話画面の上部に座標を表示
                    </small>
                  </Link>
                </li>
                <li>
                  <Link className="more-link" to="/settings?chat_kb_diag=0">
                    内部: チャットKB診断をオフ
                  </Link>
                </li>
              </>
            ) : null}
          </ul>
        </section>
      </div>
    </div>
  );
}
