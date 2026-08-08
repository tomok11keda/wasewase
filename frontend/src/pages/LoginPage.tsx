import { useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useSession } from "../lib/session";
import {
  browseRequest,
  ensureAuthCsrf,
  loginRequest,
} from "../features/auth/api";
import type { MeResponse } from "../lib/api";

export function LoginPage() {
  const { me, loading, setMeFromAuth, refresh } = useSession();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const next = params.get("next") || "/app/";
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    void ensureAuthCsrf();
  }, []);

  useEffect(() => {
    if (!loading && me?.authenticated) {
      const target = next.startsWith("/app")
        ? next.slice(4) || "/"
        : next.startsWith("/")
          ? next
          : "/";
      navigate(target || "/", { replace: true });
    }
  }, [loading, me?.authenticated, navigate, next]);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const { res, data } = await loginRequest({ email, password, next });
      if (!res.ok || !data.ok) {
        setError(data.message || "メールアドレスまたはパスワードが正しくありません。");
        return;
      }
      if (data.me) {
        setMeFromAuth(data.me as MeResponse);
      } else {
        await refresh();
      }
      const redirect = (data.redirect as string) || next;
      if (redirect.startsWith("/app")) {
        navigate(redirect.slice(4) || "/", { replace: true });
      } else {
        window.location.href = redirect;
      }
    } catch {
      setError("ログインに失敗しました。");
    } finally {
      setBusy(false);
    }
  };

  const onBrowse = async () => {
    setBusy(true);
    try {
      const { data } = await browseRequest(next);
      if (data.me) setMeFromAuth(data.me as MeResponse);
      else await refresh();
      const redirect = (data.redirect as string) || "/app/";
      if (redirect.startsWith("/app")) {
        navigate(redirect.slice(4) || "/", { replace: true });
      } else {
        window.location.href = redirect;
      }
    } catch {
      setError("閲覧モードの開始に失敗しました。");
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="main-inner" data-spa-page="ログイン">
      <div className="form-card">
        <h1>ログイン</h1>
        {error ? <p className="errors">{error}</p> : null}
        <form onSubmit={(e) => void onSubmit(e)}>
          <label htmlFor="login-email">メールアドレス</label>
          <input
            id="login-email"
            type="email"
            autoComplete="email"
            placeholder="example@waseda.jp"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />
          <label htmlFor="login-password">パスワード</label>
          <input
            id="login-password"
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
          <button type="submit" className="btn" disabled={busy}>
            ログイン
          </button>
        </form>
        <p className="footer-link browse-cta">
          <button
            type="button"
            className="linkish"
            disabled={busy}
            onClick={() => void onBrowse()}
          >
            ログインせずに閲覧モードで始める（受験生の方など）
          </button>
        </p>
        <p className="footer-link">
          <Link to="/password-reset">パスワードを忘れた方はこちら</Link>
        </p>
        <p className="footer-link">
          アカウントをお持ちでない方は <Link to="/signup">新規登録</Link>
        </p>
      </div>
    </main>
  );
}
