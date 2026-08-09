import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useSession } from "../lib/session";
import { spaLoginPath } from "../features/auth/api";
import {
  fetchMessageRequests,
  type MessageRequestItem,
} from "../features/dm/api";

export function MessageRequestsPage() {
  const { me, loading: sessionLoading } = useSession();
  const navigate = useNavigate();
  const [items, setItems] = useState<MessageRequestItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(
    async (signal?: AbortSignal) => {
      if (!me?.authenticated) return;
      setLoading(true);
      setError(null);
      try {
        const data = await fetchMessageRequests(signal);
        if (signal?.aborted) return;
        setItems(data.requests || []);
      } catch (err) {
        if ((err as Error)?.name === "AbortError") return;
        setError(err instanceof Error ? err.message : "load_failed");
      } finally {
        if (!signal?.aborted) setLoading(false);
      }
    },
    [me?.authenticated]
  );

  useEffect(() => {
    if (sessionLoading) return;
    if (!me?.authenticated) {
      navigate(spaLoginPath("/app/dm/requests"), { replace: true });
      return;
    }
    const ac = new AbortController();
    void load(ac.signal);
    return () => ac.abort();
  }, [sessionLoading, me?.authenticated, load, navigate]);

  if (sessionLoading || !me?.authenticated) {
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
      <main className="main-inner" aria-label="メッセージリクエスト">
        <p className="dm-room-top">
          <Link className="dm-back-text" to="/dm">
            ← メッセージ一覧
          </Link>
        </p>
        <header className="dm-inbox-header">
          <h1>メッセージリクエスト</h1>
          <p>
            フォローしていないユーザーからのメッセージです。チャットを開始するか拒否できます。
          </p>
        </header>

        {loading ? (
          <p className="dm-inbox-empty">読み込み中…</p>
        ) : error ? (
          <p className="dm-inbox-empty">読み込みに失敗しました（{error}）</p>
        ) : items.length === 0 ? (
          <div className="dm-inbox-empty">
            <strong>リクエストはありません</strong>
            新しいメッセージリクエストが届くとここに表示されます。
          </div>
        ) : (
          <ul className="dm-inbox-list">
            {items.map((item) => {
              const user = item.from_user;
              const name = user?.display_name || "ユーザー";
              const handle = user?.username ? `@${user.username}` : "";
              const dept = [user?.department, user?.grade]
                .filter(Boolean)
                .join(" · ");
              return (
                <li key={item.id}>
                  <Link
                    className="dm-inbox-item is-invite"
                    to={item.spa_path || `/dm/${item.room_id}`}
                  >
                    <span className="dm-inbox-avatar" aria-hidden="true">
                      {user?.avatar_url ? (
                        <img src={user.avatar_url} alt="" />
                      ) : (
                        (user?.initial || name.slice(0, 1) || "?")
                      )}
                    </span>
                    <span className="dm-inbox-body">
                      <span className="dm-inbox-top">
                        <span className="dm-inbox-name">{name}</span>
                      </span>
                      {handle ? (
                        <span className="dm-inbox-handle">{handle}</span>
                      ) : null}
                      {dept ? (
                        <span className="dm-inbox-handle">{dept}</span>
                      ) : null}
                      <p className="dm-inbox-preview">
                        {item.preview || "メッセージを確認する"}
                      </p>
                    </span>
                    <span className="dm-inbox-status is-invite">リクエスト</span>
                  </Link>
                </li>
              );
            })}
          </ul>
        )}
      </main>
    </div>
  );
}
