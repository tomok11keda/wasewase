import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useSession } from "../lib/session";
import { spaLoginPath } from "../features/auth/api";
import {
  fetchProfile,
  updatePrivacy,
} from "../features/profile/api";

export function SettingsPage() {
  const { me, loading: sessionLoading } = useSession();
  const navigate = useNavigate();
  const [isPrivate, setIsPrivate] = useState(false);
  const [loading, setLoading] = useState(true);
  const [privacyReady, setPrivacyReady] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savedMsg, setSavedMsg] = useState<string | null>(null);

  useEffect(() => {
    if (sessionLoading) return;
    if (!me?.authenticated || !me.user) {
      navigate(spaLoginPath("/app/settings"), { replace: true });
      return;
    }
    let cancelled = false;
    setLoading(true);
    setPrivacyReady(false);
    void fetchProfile(me.user.id)
      .then((data) => {
        if (cancelled) return;
        setIsPrivate(Boolean(data.is_private));
        setPrivacyReady(true);
        setError(null);
      })
      .catch((err) => {
        if (cancelled) return;
        setPrivacyReady(false);
        setError(err instanceof Error ? err.message : "load_failed");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [sessionLoading, me?.authenticated, me?.user, navigate]);

  const onChangePrivacy = async (next: boolean) => {
    if (!privacyReady || busy || next === isPrivate) return;
    setBusy(true);
    setSavedMsg(null);
    setError(null);
    try {
      const result = await updatePrivacy(next);
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

  if (sessionLoading || loading) {
    return (
      <div className="settings-page" data-spa-page="設定">
        <div className="main-inner">
          <p>読み込み中…</p>
        </div>
      </div>
    );
  }

  return (
    <div className="settings-page" data-spa-page="設定">
      <div className="main-inner">
        <Link className="profile-back" to="/">
          ← タイムラインへ戻る
        </Link>
        <h1 className="page-title">アカウント設定</h1>

        {error ? <p className="settings-flash settings-flash--error">{error}</p> : null}
        {savedMsg ? (
          <p className="settings-flash settings-flash--ok">{savedMsg}</p>
        ) : null}

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
              <a className="more-link" href="/mypage/settings/">
                退会など
                <small className="more-link-note">（従来ページ）</small>
              </a>
            </li>
          </ul>
        </section>
      </div>
    </div>
  );
}
