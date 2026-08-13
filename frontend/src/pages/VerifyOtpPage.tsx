import { useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  ensureAuthCsrf,
  fetchVerifyStatus,
  verifyOtpRequest,
  verifyOtpResend,
} from "../features/auth/api";
import { EmailDeliveryHint } from "../components/EmailDeliveryHint";
import { useSession } from "../lib/session";
import { analytics } from "../lib/analytics/events";
import type { MeResponse } from "../lib/api";

export function VerifyOtpPage() {
  const { setMeFromAuth, refresh } = useSession();
  const navigate = useNavigate();
  const [code, setCode] = useState("");
  const [masked, setMasked] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    void ensureAuthCsrf();
    void fetchVerifyStatus().then((data) => {
      if (!data.pending) {
        navigate("/signup", { replace: true });
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
      const { res, data } = await verifyOtpRequest(code);
      if (!res.ok || !data.ok) {
        setError(data.message || "認証コードが正しくありません。");
        if (data.redirect === "/app/signup") navigate("/signup");
        return;
      }
      if (data.me) setMeFromAuth(data.me as MeResponse);
      else await refresh();
      analytics.signupCompleted();
      navigate("/?login_success=1", { replace: true });
    } catch {
      setError("認証に失敗しました。");
    } finally {
      setBusy(false);
    }
  };

  const onResend = async () => {
    setBusy(true);
    setError(null);
    try {
      const { res, data } = await verifyOtpResend();
      if (!res.ok || !data.ok) {
        setError(data.message || "再送信に失敗しました。");
        return;
      }
      setInfo(data.message || "認証コードを再送信しました。");
    } catch {
      setError("再送信に失敗しました。");
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="main-inner" data-spa-page="メール認証">
      <div className="form-card">
        <h1>メール認証</h1>
        {masked ? (
          <p className="hint">{masked} に送った6桁のコードを入力してください。</p>
        ) : null}
        <EmailDeliveryHint />
        {info ? (
          <ul className="messages">
            <li className="info">{info}</li>
          </ul>
        ) : null}
        {error ? <p className="field-error">{error}</p> : null}
        <form onSubmit={(e) => void onSubmit(e)}>
          <label htmlFor="otp-code">認証コード</label>
          <input
            id="otp-code"
            value={code}
            onChange={(e) => setCode(e.target.value)}
            maxLength={6}
            inputMode="numeric"
            autoComplete="one-time-code"
            placeholder="123456"
            required
          />
          <button type="submit" className="btn" disabled={busy || code.length !== 6}>
            認証する
          </button>
        </form>
        <p className="footer-link">
          <button
            type="button"
            className="linkish"
            disabled={busy}
            onClick={() => void onResend()}
          >
            コードを再送信
          </button>
        </p>
        <EmailDeliveryHint compact />
        <p className="footer-link">
          <Link to="/signup">新規登録に戻る</Link>
        </p>
      </div>
    </main>
  );
}
