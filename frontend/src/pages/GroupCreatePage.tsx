import {
  useCallback,
  useEffect,
  useState,
  type FormEvent,
} from "react";
import { Link, useNavigate } from "react-router-dom";
import { useSession } from "../lib/session";
import {
  createGroup,
  fetchGroupFollowees,
  type Author,
} from "../features/dm/api";
import { spaLoginPath } from "../features/auth/api";
import { analytics } from "../lib/analytics/events";

export function GroupCreatePage() {
  const { me, loading: sessionLoading } = useSession();
  const navigate = useNavigate();
  const [candidates, setCandidates] = useState<Author[]>([]);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [name, setName] = useState("");
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (q: string) => {
    setLoading(true);
    try {
      const list = await fetchGroupFollowees(q);
      setCandidates(list);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "load_failed");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (sessionLoading) return;
    if (!me?.authenticated) {
      navigate(spaLoginPath("/app/dm/groups/new"), { replace: true });
      return;
    }
    const handle = window.setTimeout(() => {
      void load(query.trim());
    }, query.trim() ? 250 : 0);
    return () => window.clearTimeout(handle);
  }, [sessionLoading, me?.authenticated, load, query]);

  const toggle = (id: number) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!selected.size) {
      window.alert("招待するユーザーを1人以上選択してください。");
      return;
    }
    setBusy(true);
    try {
      const roomId = await createGroup(name.trim(), [...selected]);
      analytics.groupChatStarted();
      navigate(`/dm/groups/${roomId}`);
    } catch (err) {
      window.alert(err instanceof Error ? err.message : "作成に失敗しました");
    } finally {
      setBusy(false);
    }
  };

  if (sessionLoading) {
    return (
      <div className="dm-page" data-spa-page="メッセージ">
        <div className="main-inner">
          <p>読み込み中…</p>
        </div>
      </div>
    );
  }

  return (
    <div className="dm-page" data-spa-page="メッセージ">
      <main className="main-inner" aria-label="グループ作成">
        <div className="dm-group-header">
          <h1>グループを作成して招待</h1>
          <p>
            誰でも招待できます。招待された相手は参加するまでメンバーにはなりません。
          </p>
        </div>

        {error ? <p className="dm-empty">読み込みに失敗しました（{error}）</p> : null}

        <form className="dm-group-card" onSubmit={(e) => void onSubmit(e)}>
          <input
            className="dm-search-input"
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            maxLength={120}
            placeholder="グループ名（任意）"
            autoComplete="off"
          />
          <input
            className="dm-search-input"
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="ユーザーを検索（表示名 / @username）"
            autoComplete="off"
          />

          <ul className="dm-user-list">
            {loading ? (
              <li className="dm-user-item" style={{ color: "var(--dm-muted)" }}>
                検索中…
              </li>
            ) : candidates.length === 0 ? (
              <li className="dm-user-item" style={{ color: "var(--dm-muted)" }}>
                {query.trim()
                  ? "該当するユーザーがいません。"
                  : "フォロー中のユーザーがいません。検索して招待できます。"}
              </li>
            ) : (
              candidates.map((u) => (
                <li key={u.id ?? u.username} className="dm-user-item">
                  <label>
                    <input
                      type="checkbox"
                      checked={u.id != null && selected.has(u.id)}
                      onChange={() => u.id != null && toggle(u.id)}
                    />
                    <span className="dm-user-text">
                      <span className="dm-user-name">{u.display_name}</span>
                      <span className="dm-user-handle">@{u.username}</span>
                    </span>
                  </label>
                </li>
              ))
            )}
          </ul>

          <div className="dm-group-actions">
            <Link className="dm-btn dm-btn-ghost" to="/dm">
              キャンセル
            </Link>
            <button
              className="dm-btn dm-btn-primary"
              type="submit"
              disabled={busy || selected.size === 0}
            >
              作成して招待
            </button>
          </div>
        </form>
      </main>
    </div>
  );
}
