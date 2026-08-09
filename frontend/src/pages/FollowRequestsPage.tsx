import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useSession } from "../lib/session";
import { spaLoginPath } from "../features/auth/api";
import {
  acceptFollowRequest,
  fetchFollowRequests,
  rejectFollowRequest,
  type FollowRequestItem,
} from "../features/profile/api";

export function FollowRequestsPage() {
  const { me, loading: sessionLoading, refresh } = useSession();
  const navigate = useNavigate();
  const [items, setItems] = useState<FollowRequestItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [flash, setFlash] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const list = await fetchFollowRequests();
      setItems(list);
    } catch (err) {
      setError(err instanceof Error ? err.message : "load_failed");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (sessionLoading) return;
    if (!me?.authenticated) {
      navigate(spaLoginPath("/app/settings/follow-requests"), { replace: true });
      return;
    }
    void load();
  }, [sessionLoading, me?.authenticated, navigate, load]);

  const onAccept = async (id: number) => {
    setBusyId(id);
    setFlash(null);
    try {
      await acceptFollowRequest(id);
      setItems((prev) => prev.filter((r) => r.id !== id));
      setFlash("フォローリクエストを承認しました。");
      void refresh();
    } catch (err) {
      window.alert(err instanceof Error ? err.message : "承認に失敗しました");
    } finally {
      setBusyId(null);
    }
  };

  const onReject = async (id: number) => {
    setBusyId(id);
    setFlash(null);
    try {
      await rejectFollowRequest(id);
      setItems((prev) => prev.filter((r) => r.id !== id));
      setFlash("フォローリクエストを拒否しました。");
      void refresh();
    } catch (err) {
      window.alert(err instanceof Error ? err.message : "拒否に失敗しました");
    } finally {
      setBusyId(null);
    }
  };

  if (sessionLoading || loading) {
    return (
      <div className="settings-page" data-spa-page="フォローリクエスト">
        <div className="main-inner">
          <p>読み込み中…</p>
        </div>
      </div>
    );
  }

  return (
    <div className="settings-page" data-spa-page="フォローリクエスト">
      <div className="main-inner">
        <Link className="profile-back" to="/notifications">
          ← 通知へ戻る
        </Link>
        <h1 className="page-title">フォローリクエスト</h1>

        {flash ? <p className="settings-flash settings-flash--ok">{flash}</p> : null}
        {error ? <p className="settings-flash settings-flash--error">{error}</p> : null}

        {!error && items.length === 0 ? (
          <p className="profile-empty">フォローリクエストはありません</p>
        ) : null}

        <ul className="follow-request-list">
          {items.map((item) => {
            const u = item.from_user;
            return (
              <li key={item.id} className="follow-request-item">
                <Link
                  className="follow-request-user"
                  to={`/users/${u.id}/posts`}
                >
                  {u.avatar_url ? (
                    <img
                      className="follow-request-avatar user-avatar--image"
                      src={u.avatar_url}
                      alt=""
                    />
                  ) : (
                    <span className="follow-request-avatar user-avatar--icon">
                      {u.initial || "?"}
                    </span>
                  )}
                  <span className="follow-request-names">
                    <strong>{u.display_name}</strong>
                    <small>@{u.username || u.id}</small>
                  </span>
                </Link>
                <div className="follow-request-actions">
                  <button
                    type="button"
                    className="btn btn-primary"
                    disabled={busyId === item.id}
                    onClick={() => void onAccept(item.id)}
                  >
                    承認
                  </button>
                  <button
                    type="button"
                    className="btn btn-secondary"
                    disabled={busyId === item.id}
                    onClick={() => void onReject(item.id)}
                  >
                    拒否
                  </button>
                </div>
              </li>
            );
          })}
        </ul>
      </div>
    </div>
  );
}
