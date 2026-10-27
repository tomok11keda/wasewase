import { useEffect, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { createLinkedProfile } from "../features/linkedProfiles/api";
import {
  canAddLinkedProfile,
  linkedProfileMax,
} from "../features/linkedProfiles/linkedProfiles";
import { useSession } from "../lib/session";
import { spaLoginPath } from "../features/auth/api";

export function LinkedAccountCreatePage() {
  const { me, loading, setMeFromAuth } = useSession();
  const navigate = useNavigate();
  const [username, setUsername] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const maxProfiles = linkedProfileMax(me);

  useEffect(() => {
    if (loading) return;
    if (!me?.authenticated) {
      navigate(spaLoginPath("/app/settings/linked-account"), { replace: true });
      return;
    }
    if (!canAddLinkedProfile(me)) {
      navigate("/more", { replace: true });
    }
  }, [loading, me, navigate]);

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const { res, data } = await createLinkedProfile({
        username,
        display_name: displayName,
      });
      if (!res.ok || !data.ok) {
        setError(data.message || "アカウントを追加できませんでした。");
        return;
      }
      if (data.me) setMeFromAuth(data.me);
      navigate("/", { replace: true });
    } catch {
      setError("アカウントを追加できませんでした。");
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="main-inner linked-account-page" data-spa-page="アカウントを追加">
      <div className="form-card linked-account-card">
        <header className="linked-account-header">
          <h1>アカウントを追加</h1>
          <p className="linked-account-sub">サブアカウントを作成できます</p>
        </header>

        <ul className="linked-account-points">
          <li>大学メールの再認証は不要です</li>
          <li>新しいパスワードの設定も不要です</li>
          <li>1人{maxProfiles}アカウントまで作成できます</li>
        </ul>

        {error ? <p className="errors">{error}</p> : null}

        <form
          className="linked-account-form"
          onSubmit={(event) => void onSubmit(event)}
        >
          <div className="form-group">
            <label htmlFor="linked-username">ユーザー名</label>
            <input
              id="linked-username"
              type="text"
              autoComplete="username"
              autoCapitalize="none"
              autoCorrect="off"
              spellCheck={false}
              placeholder="例）wase_sub"
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              required
              disabled={busy}
            />
          </div>

          <div className="form-group">
            <label htmlFor="linked-display-name">表示名</label>
            <input
              id="linked-display-name"
              type="text"
              autoComplete="nickname"
              placeholder="例）わせわせサブ"
              value={displayName}
              onChange={(event) => setDisplayName(event.target.value)}
              required
              disabled={busy}
            />
          </div>

          <button
            type="submit"
            className="btn linked-account-submit"
            disabled={busy}
          >
            {busy ? "追加中…" : "アカウントを追加して切り替える"}
          </button>
        </form>

        <p className="linked-account-footnote">
          アイコンは追加後にプロフィール設定から変更できます。
        </p>
      </div>
    </main>
  );
}
