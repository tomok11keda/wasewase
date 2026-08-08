import { useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  ensureAuthCsrf,
  fetchSignupMeta,
  signupRequest,
} from "../features/auth/api";
import { useSession } from "../lib/session";

export function SignupPage() {
  const { me, loading } = useSession();
  const navigate = useNavigate();
  const [faculties, setFaculties] = useState<{ value: string; label: string }[]>(
    []
  );
  const [email, setEmail] = useState("");
  const [nickname, setNickname] = useState("");
  const [faculty, setFaculty] = useState("");
  const [password1, setPassword1] = useState("");
  const [password2, setPassword2] = useState("");
  const [acceptTerms, setAcceptTerms] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string[]>>({});
  const [info, setInfo] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    void ensureAuthCsrf();
    void fetchSignupMeta()
      .then((m) => setFaculties(m.faculties || []))
      .catch(() => setFaculties([]));
  }, []);

  useEffect(() => {
    if (!loading && me?.authenticated) {
      navigate("/", { replace: true });
    }
  }, [loading, me?.authenticated, navigate]);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setFieldErrors({});
    try {
      const { res, data } = await signupRequest({
        email,
        nickname,
        faculty,
        password1,
        password2,
        accept_terms: acceptTerms,
      });
      if (!res.ok || !data.ok) {
        setError(data.message || "入力内容を確認してください。");
        if (data.errors) setFieldErrors(data.errors as Record<string, string[]>);
        return;
      }
      if (data.message) setInfo(String(data.message));
      navigate("/verify", { replace: true });
    } catch {
      setError("登録に失敗しました。");
    } finally {
      setBusy(false);
    }
  };

  const err = (key: string) =>
    fieldErrors[key]?.[0] ? (
      <p className="field-error">{fieldErrors[key][0]}</p>
    ) : null;

  return (
    <main className="main-inner" data-spa-page="新規登録">
      <div className="form-card">
        <h1>新規登録</h1>
        {info ? (
          <ul className="messages">
            <li className="info">{info}</li>
          </ul>
        ) : null}
        {error ? <p className="field-error">{error}</p> : null}
        <form onSubmit={(e) => void onSubmit(e)}>
          <label htmlFor="su-email">メールアドレス（早稲田大学）</label>
          <input
            id="su-email"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="example@waseda.jp"
            autoComplete="email"
            required
          />
          {err("email")}
          <p className="hint">
            @waseda.jp または @〇〇.waseda.jp のアドレスのみ登録できます。
          </p>

          <label htmlFor="su-nick">ニックネーム（表示名）</label>
          <input
            id="su-nick"
            value={nickname}
            onChange={(e) => setNickname(e.target.value)}
            placeholder="例：わせ太郎"
            autoComplete="nickname"
            required
          />
          {err("nickname")}

          <label htmlFor="su-faculty">学部（わせわせ認証バッジ）</label>
          <select
            id="su-faculty"
            value={faculty}
            onChange={(e) => setFaculty(e.target.value)}
            required
          >
            <option value="">学部を選択してください</option>
            {faculties.map((f) => (
              <option key={f.value} value={f.value}>
                {f.label}
              </option>
            ))}
          </select>
          {err("faculty")}

          <label htmlFor="su-p1">パスワード</label>
          <input
            id="su-p1"
            type="password"
            value={password1}
            onChange={(e) => setPassword1(e.target.value)}
            autoComplete="new-password"
            required
          />
          {err("password1")}

          <label htmlFor="su-p2">パスワード（確認）</label>
          <input
            id="su-p2"
            type="password"
            value={password2}
            onChange={(e) => setPassword2(e.target.value)}
            autoComplete="new-password"
            required
          />
          {err("password2")}

          <label className="terms-agree">
            <input
              type="checkbox"
              checked={acceptTerms}
              onChange={(e) => setAcceptTerms(e.target.checked)}
            />
            <span>
              <a href="/terms/" target="_blank" rel="noreferrer">
                利用規約
              </a>
              と
              <a href="/privacy/" target="_blank" rel="noreferrer">
                プライバシーポリシー
              </a>
              に同意する
            </span>
          </label>
          {err("accept_terms")}

          <button type="submit" className="btn" disabled={busy || !acceptTerms}>
            認証コードを送る
          </button>
        </form>
        <p className="footer-link">
          すでにアカウントがある方は <Link to="/login">ログイン</Link>
        </p>
      </div>
    </main>
  );
}
