import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useSession } from "../lib/session";
import { spaLoginPath } from "../features/auth/api";
import {
  fetchMessageRequests,
  type MessageRequestItem,
} from "../features/dm/api";
import { AccountDisplayName } from "../components/VerifiedAccountBadge";
import { PeopleListSkeleton } from "../components/skeleton";
import { listContentPhase, listQueryKey } from "../lib/listContentPhase";
import {
  isLatestRequest,
  isSameUserScope,
  nextRequestId,
} from "../lib/userScopedResult";

export function MessageRequestsPage() {
  const { me, loading: sessionLoading } = useSession();
  const navigate = useNavigate();
  const sessionUserId =
    me?.authenticated && me.user?.id != null ? me.user.id : null;
  const userIdRef = useRef(sessionUserId);
  userIdRef.current = sessionUserId;
  const fetchGen = useRef(0);
  const [items, setItems] = useState<MessageRequestItem[]>([]);
  const [appliedKey, setAppliedKey] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const listKey = listQueryKey([sessionUserId, "message-requests"]);

  useLayoutEffect(() => {
    nextRequestId(fetchGen);
    setItems([]);
    setAppliedKey("");
    setLoading(true);
    setError(null);
  }, [sessionUserId]);

  const load = useCallback(
    async (signal?: AbortSignal) => {
      if (!me?.authenticated) return;
      const gen = nextRequestId(fetchGen);
      const startedUserId = userIdRef.current;
      setLoading(true);
      setError(null);
      try {
        const data = await fetchMessageRequests(signal);
        if (signal?.aborted) return;
        if (!isLatestRequest(fetchGen, gen)) return;
        if (!isSameUserScope(startedUserId, userIdRef.current)) return;
        setItems(data.requests || []);
        setAppliedKey(listKey);
      } catch (err) {
        if ((err as Error)?.name === "AbortError") return;
        if (!isLatestRequest(fetchGen, gen)) return;
        if (!isSameUserScope(startedUserId, userIdRef.current)) return;
        setItems([]);
        setAppliedKey(listKey);
        setError(err instanceof Error ? err.message : "load_failed");
      } finally {
        if (!signal?.aborted && isLatestRequest(fetchGen, gen)) setLoading(false);
      }
    },
    [me?.authenticated, listKey]
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
  }, [sessionLoading, me?.authenticated, load, navigate, sessionUserId]);

  const phase = listContentPhase({
    browsePreview: false,
    loading: sessionLoading || loading,
    error,
    itemCount: items.length,
    matchesCurrentQuery: appliedKey === listKey,
  });

  return (
    <div className="dm-page" data-spa-page="メッセージ">
      <main className="main-inner" aria-label="メッセージリクエスト">
        <header className="dm-inbox-header">
          <p>
            フォローしていないユーザーからのメッセージです。チャットを開始するか拒否できます。
          </p>
        </header>

        {phase === "skeleton" ? (
          <PeopleListSkeleton />
        ) : phase === "error" ? (
          <p className="dm-inbox-empty">
            読み込みに失敗しました（{error}）
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => void load()}
            >
              再試行
            </button>
          </p>
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
                        <span className="dm-inbox-name">
                          <AccountDisplayName
                            name={name}
                            verified={user?.is_operator_verified}
                          />
                        </span>
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
