import { useEffect, useState, type FormEvent } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import {
  ensureAuthCsrf,
  fetchPasswordResetStatus,
  passwordResetRequest,
  passwordResetResend,
  passwordResetSet,
  passwordResetVerify,
} from "../features/auth/api";
import { EmailDeliveryHint } from "../components/EmailDeliveryHint";

export function PasswordResetRequestPage() {
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    void ensureAuthCsrf();
  }, []);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const { res, data } = await passwordResetRequest(email);
      if (!res.ok || !data.ok) {
        setError(data.message || "入力内容を確認してください。");
        return;
      }
      navigate("/password-reset/verify", { replace: true });
    } catch {
      setError("送信に失敗しました。");
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="main-inner" data-spa-page="パスワード再設定">
      <div className="form-card">
        <h1>パスワード再設定</h1>
        {error ? <p className="field-error">{error}</p> : null}
        <form onSubmit={(e) => void onSubmit(e)}>
          <label htmlFor="pr-email">登録しているメールアドレス</label>
          <input
            id="pr-email"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="例：taro@akane.waseda.jp"
            autoComplete="email"
            required
          />
          <EmailDeliveryHint />
          <button type="submit" className="btn" disabled={busy}>
            確認コードを送る
          </button>
        </form>
        <p className="footer-link">
          <Link to="/login">ログインに戻る</Link>
        </p>
      </div>
    </main>
  );
}

export function PasswordResetVerifyPage() {
  const navigate = useNavigate();
  const [code, setCode] = useState("");
  const [masked, setMasked] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    void ensureAuthCsrf();
    void fetchPasswordResetStatus().then((data) => {
      if (!data.pending) {
        navigate("/password-reset", { replace: true });
        return;
      }
      if (data.verified) {
        navigate("/password-reset/set", { replace: true });
        return;
      }
      setMasked(data.masked_email || "");
    });
  }, [navigate]);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const { res, data } = await passwordResetVerify(code);
      if (!res.ok || !data.ok) {
        setError(data.message || "確認コードが正しくありません。");
        return;
      }
      navigate("/password-reset/set", { replace: true });
    } catch {
      setError("確認に失敗しました。");
    } finally {
      setBusy(false);
    }
  };

  const onResend = async () => {
    setBusy(true);
    try {
      const { res, data } = await passwordResetResend();
      if (!res.ok || !data.ok) {
        setError(data.message || "再送信に失敗しました。");
        return;
      }
      setInfo(data.message || "確認コードを再送信しました。");
    } catch {
      setError("再送信に失敗しました。");
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="main-inner" data-spa-page="パスワード再設定">
      <div className="form-card">
        <h1>確認コード入力</h1>
        {masked ? <p className="hint">{masked} に送ったコードを入力してください。</p> : null}
        <EmailDeliveryHint />
        {info ? (
          <ul className="messages">
            <li className="info">{info}</li>
          </ul>
        ) : null}
        {error ? <p className="field-error">{error}</p> : null}
        <form onSubmit={(e) => void onSubmit(e)}>
          <label htmlFor="prv-code">確認コード</label>
          <input
            id="prv-code"
            value={code}
            onChange={(e) => setCode(e.target.value)}
            maxLength={6}
            inputMode="numeric"
            autoComplete="one-time-code"
            required
          />
          <button type="submit" className="btn" disabled={busy || code.length !== 6}>
            確認する
          </button>
        </form>
        <p className="footer-link">
          <button type="button" className="linkish" disabled={busy} onClick={() => void onResend()}>
            コードを再送信
          </button>
        </p>
        <EmailDeliveryHint compact />
        <p className="footer-link">
          <Link to="/password-reset">メール入力に戻る</Link>
        </p>
      </div>
    </main>
  );
}

export function PasswordResetSetPage() {
  const navigate = useNavigate();
  const [password1, setPassword1] = useState("");
  const [password2, setPassword2] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [ready, setReady] = useState(false);
  const [allowed, setAllowed] = useState(false);

  useEffect(() => {
    void ensureAuthCsrf();
    void fetchPasswordResetStatus().then((data) => {
      setReady(true);
      if (!data.pending || !data.verified) {
        setAllowed(false);
        navigate(
          data.pending ? "/password-reset/verify" : "/password-reset",
          { replace: true }
        );
        return;
      }
      setAllowed(true);
    });
  }, [navigate]);

  if (!ready) {
    return (
      <main className="main-inner" data-spa-page="パスワード再設定">
        <div className="form-card">
          <p>読み込み中…</p>
        </div>
      </main>
    );
  }
  if (!allowed) return <Navigate to="/password-reset" replace />;

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const { res, data } = await passwordResetSet(password1, password2);
      if (!res.ok || !data.ok) {
        setError(data.message || "入力内容を確認してください。");
        return;
      }
      navigate("/login", { replace: true });
    } catch {
      setError("再設定に失敗しました。");
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="main-inner" data-spa-page="パスワード再設定">
      <div className="form-card">
        <h1>新しいパスワード</h1>
        {error ? <p className="field-error">{error}</p> : null}
        <form onSubmit={(e) => void onSubmit(e)}>
          <label htmlFor="prs-p1">新しいパスワード</label>
          <input
            id="prs-p1"
            type="password"
            value={password1}
            onChange={(e) => setPassword1(e.target.value)}
            autoComplete="new-password"
            placeholder="8文字以上"
            required
          />
          <label htmlFor="prs-p2">新しいパスワード（確認）</label>
          <input
            id="prs-p2"
            type="password"
            value={password2}
            onChange={(e) => setPassword2(e.target.value)}
            autoComplete="new-password"
            placeholder="もう一度入力"
            required
          />
          <button type="submit" className="btn" disabled={busy}>
            パスワードを再設定
          </button>
        </form>
        <p className="footer-link">
          <Link to="/login">ログイン画面に戻る</Link>
        </p>
      </div>
    </main>
  );
}
