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
    <main className="main-inner" data-spa-page="アカウントを追加">
      <div className="form-card">
        <h1>アカウントを追加</h1>
        <p className="form-lead">
          大学メールの再認証と新しいパスワードは不要です。1人あたり
          {linkedProfileMax(me)}つまで作れます。
          アイコンは追加後のプロフィール設定から変更できます。
        </p>
        {error ? <p className="errors">{error}</p> : null}
        <form onSubmit={(event) => void onSubmit(event)}>
          <label htmlFor="linked-username">ユーザー名</label>
          <input
            id="linked-username"
            type="text"
            autoComplete="username"
            value={username}
            onChange={(event) => setUsername(event.target.value)}
            required
          />
          <label htmlFor="linked-display-name">表示名</label>
          <input
            id="linked-display-name"
            type="text"
            autoComplete="nickname"
            value={displayName}
            onChange={(event) => setDisplayName(event.target.value)}
            required
          />
          <button type="submit" className="btn" disabled={busy}>
            追加して切り替える
          </button>
        </form>
      </div>
    </main>
  );
}
