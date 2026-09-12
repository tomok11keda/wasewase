import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useSession } from "../lib/session";
import {
  browseRequest,
  ensureAuthCsrf,
  loginRequest,
} from "../features/auth/api";
import { analytics } from "../lib/analytics/events";
import type { MeResponse } from "../lib/api";

/**
 * After auth: stay in the React SPA. Never window.location.replace to a
 * non-/app path — Capacitor treats those as external and opens Safari.
 * Unmapped next/redirect values fall back to Home.
 */
function spaPathFromAppRedirect(redirect: string): string {
  const target = (redirect || "/app/").trim() || "/app/";
  if (target.startsWith("/app/")) {
    return target.slice(4) || "/";
  }
  if (target === "/app" || target.startsWith("/app?") || target.startsWith("/app#")) {
    return target.slice(4) || "/";
  }
  return "/";
}

function goAfterAuth(
  redirect: string,
  navigate: ReturnType<typeof useNavigate>
) {
  const spaPath = spaPathFromAppRedirect(redirect);
  navigate(spaPath.startsWith("/") ? spaPath : `/${spaPath}`, { replace: true });
}

export function LoginPage() {
  const { me, loading, setMeFromAuth, refresh } = useSession();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const next = params.get("next") || "/app/";
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  /** Avoid racing raw `next` full-load after login API already returned /app/…. */
  const skipQueryNextRedirect = useRef(false);

  useEffect(() => {
    void ensureAuthCsrf();
  }, []);

  useEffect(() => {
    if (!loading && me?.authenticated) {
      if (skipQueryNextRedirect.current) return;
      if (me.onboarding_required) {
        navigate("/onboarding", { replace: true });
        return;
      }
      goAfterAuth(next, navigate);
    }
  }, [loading, me?.authenticated, me?.onboarding_required, navigate, next]);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const { res, data } = await loginRequest({ email, password, next });
      if (!res.ok || !data.ok) {
        setError(
          data.message || "メールアドレスまたはパスワードが正しくありません。"
        );
        return;
      }
      skipQueryNextRedirect.current = true;
      if (data.me) {
        setMeFromAuth(data.me as MeResponse);
      } else {
        await refresh();
      }
      analytics.loginCompleted();
      const redirect = (data.redirect as string) || next;
      if ((data.me as MeResponse | undefined)?.onboarding_required) {
        navigate("/onboarding", { replace: true });
        return;
      }
      goAfterAuth(redirect, navigate);
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
      skipQueryNextRedirect.current = true;
      if (data.me) setMeFromAuth(data.me as MeResponse);
      else await refresh();
      const redirect = (data.redirect as string) || "/app/";
      goAfterAuth(redirect, navigate);
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
