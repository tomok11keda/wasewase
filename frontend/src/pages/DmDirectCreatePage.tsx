import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { AccountDisplayName } from "../components/VerifiedAccountBadge";
import { PeopleListSkeleton } from "../components/skeleton";
import { spaLoginPath } from "../features/auth/api";
import { fetchGroupFollowees, startDm, type Author } from "../features/dm/api";
import { useSession } from "../lib/session";

export function DmDirectCreatePage() {
  const { me, loading: sessionLoading } = useSession();
  const navigate = useNavigate();
  const [candidates, setCandidates] = useState<Author[]>([]);
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState<number | null>(null);
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
      navigate(spaLoginPath("/app/dm/new/direct"), { replace: true });
      return;
    }
    const handle = window.setTimeout(() => {
      void load(query.trim());
    }, query.trim() ? 250 : 0);
    return () => window.clearTimeout(handle);
  }, [sessionLoading, me?.authenticated, load, query, navigate]);

  const start = async (userId: number) => {
    if (busyId != null) return;
    setBusyId(userId);
    try {
      const roomId = await startDm(userId);
      navigate(`/dm/${roomId}`);
    } catch (err) {
      window.alert(err instanceof Error ? err.message : "チャットを開始できませんでした");
    } finally {
      setBusyId(null);
    }
  };

  if (sessionLoading) {
    return (
      <div className="dm-page" data-spa-page="個人チャット">
        <main className="main-inner" aria-label="個人チャット">
          <PeopleListSkeleton />
        </main>
      </div>
    );
  }

  return (
    <div className="dm-page" data-spa-page="個人チャット">
      <main className="main-inner" aria-label="個人チャット">
        <div className="dm-group-header">
          <p>相手を選ぶと個人チャットが開きます。</p>
        </div>
        {error ? <p className="dm-empty">読み込みに失敗しました（{error}）</p> : null}
        <div className="dm-group-card">
          <input
            className="dm-search-input"
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="ユーザーを検索（表示名 / @username）"
            autoComplete="off"
          />
          {loading && !query.trim() && candidates.length === 0 ? (
            <PeopleListSkeleton rows={4} />
          ) : (
            <ul className="dm-user-list">
              {loading ? (
                <li className="dm-user-item" style={{ color: "var(--dm-muted)" }}>
                  検索中…
                </li>
              ) : candidates.length === 0 ? (
                <li className="dm-user-item" style={{ color: "var(--dm-muted)" }}>
                  {query.trim()
                    ? "該当するユーザーがいません。"
                    : "フォロー中のユーザーがいません。検索して開始できます。"}
                </li>
              ) : (
                candidates.map((user) => (
                  <li key={user.id ?? user.username} className="dm-user-item">
                    <button
                      type="button"
                      className="dm-compose-user"
                      disabled={user.id == null || busyId != null}
                      onClick={() => user.id != null && void start(user.id)}
                    >
                      <span className="dm-user-text">
                        <span className="dm-user-name">
                          <AccountDisplayName
                            name={user.display_name}
                            verified={user.is_operator_verified}
                          />
                        </span>
                        <span className="dm-user-handle">@{user.username}</span>
                      </span>
                      <span className="dm-compose-user__action">
                        {busyId === user.id ? "開始中…" : "チャット"}
                      </span>
                    </button>
                  </li>
                ))
              )}
            </ul>
          )}
          <div className="dm-group-actions">
            <Link className="dm-btn dm-btn-ghost" to="/dm/new">
              戻る
            </Link>
          </div>
        </div>
      </main>
    </div>
  );
}
