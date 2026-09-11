import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useSession } from "../lib/session";
import { spaLoginPath } from "../features/auth/api";
import {
  fetchFollowList,
  type FollowListKind,
  type FollowListUser,
} from "../features/profile/api";

type Props = {
  kind: FollowListKind;
};

export function FollowListPage({ kind }: Props) {
  const { userId } = useParams();
  const pk = Number(userId);
  const navigate = useNavigate();
  const { me, loading: sessionLoading } = useSession();
  const [users, setUsers] = useState<FollowListUser[]>([]);
  const [count, setCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [forbidden, setForbidden] = useState(false);

  const title = kind === "followers" ? "フォロワー" : "フォロー中";
  const profilePath = `/users/${pk}/posts`;
  const loginNext = `/app/users/${pk}/${kind}`;

  useEffect(() => {
    if (sessionLoading) return;
    if (!me?.authenticated) {
      navigate(spaLoginPath(loginNext), { replace: true });
      return;
    }
    if (!Number.isFinite(pk)) {
      setError("invalid_id");
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    setForbidden(false);
    void fetchFollowList(pk, kind)
      .then((data) => {
        if (cancelled) return;
        setUsers(data.users);
        setCount(data.count);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const message = err instanceof Error ? err.message : "load_failed";
        if (message === "forbidden") {
          setForbidden(true);
        } else if (message === "unauthorized") {
          navigate(spaLoginPath(loginNext), { replace: true });
          return;
        } else {
          setError(message);
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [sessionLoading, me?.authenticated, pk, kind, navigate, loginNext]);

  return (
    <div className="profile-page" data-spa-page={title}>
      <div className="main-inner">
        <Link className="profile-back" to={Number.isFinite(pk) ? profilePath : "/"}>
          ← プロフィールへ戻る
        </Link>
        <h1 className="page-title">{title}</h1>

        {sessionLoading || loading ? <p>読み込み中…</p> : null}

        {!loading && forbidden ? (
          <div className="profile-empty profile-locked">
            <p className="profile-locked__title">このリストは表示できません</p>
            <p>フォローするとフォロワーとフォロー中を見られます。</p>
          </div>
        ) : null}

        {!loading && error ? (
          <p className="profile-empty">
            {title}を表示できません（{error}）
          </p>
        ) : null}

        {!loading && !forbidden && !error && users.length === 0 ? (
          <p className="profile-empty">{title}はまだいません</p>
        ) : null}

        {!loading && !forbidden && !error && users.length > 0 ? (
          <ul className="follow-list">
            {users.map((u) => (
              <li key={u.id}>
                <Link className="search-user-card" to={`/users/${u.id}/posts`}>
                  {u.avatar_url ? (
                    <img
                      className="search-user-avatar"
                      src={u.avatar_url}
                      alt=""
                    />
                  ) : (
                    <span className="search-user-avatar is-initial">
                      {u.initial || "?"}
                    </span>
                  )}
                  <span className="search-user-text">
                    <strong>{u.display_name}</strong>
                    <span>@{u.username || u.id}</span>
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        ) : null}

        {!loading && !forbidden && !error && count > users.length ? (
          <p className="profile-empty">先頭 {users.length} 人を表示しています</p>
        ) : null}
      </div>
    </div>
  );
}
