import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { Link, NavLink, useLocation, useNavigate, useParams } from "react-router-dom";
import { useSession } from "../lib/session";
import { spaLoginPath } from "../features/auth/api";
import { fetchFollowList, type FollowListUser } from "../features/profile/api";
import {
  readFollowListCache,
  writeFollowListCache,
} from "../features/profile/followListCache";
import {
  FOLLOW_LIST_TABS,
  followListEmptyCopy,
  followListForbiddenCopy,
  followListKindFromPath,
  followListLoadErrorCopy,
  followListPath,
  followListTitle,
} from "../features/profile/followLists";
import { AccountDisplayName } from "../components/VerifiedAccountBadge";
import { PeopleListSkeleton } from "../components/skeleton";
import { listContentPhase, listQueryKey } from "../lib/listContentPhase";
import {
  isLatestRequest,
  isSameUserScope,
  nextRequestId,
} from "../lib/userScopedResult";

export function FollowListPage() {
  const { userId } = useParams();
  const location = useLocation();
  const pk = Number(userId);
  const kind = followListKindFromPath(location.pathname);
  const navigate = useNavigate();
  const { me, loading: sessionLoading } = useSession();
  const sessionUserId =
    me?.authenticated && me.user?.id != null ? me.user.id : null;
  const userIdRef = useRef(sessionUserId);
  userIdRef.current = sessionUserId;
  const fetchGen = useRef(0);
  const [users, setUsers] = useState<FollowListUser[]>([]);
  const [count, setCount] = useState(0);
  const [appliedKey, setAppliedKey] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [forbidden, setForbidden] = useState(false);

  const title = followListTitle(kind);
  const loginNext = `/app/users/${pk}/${kind}`;
  const listKey = listQueryKey([sessionUserId, pk, kind]);

  useLayoutEffect(() => {
    nextRequestId(fetchGen);
    const cached = readFollowListCache(listKey);
    if (cached) {
      setUsers(cached.users);
      setCount(cached.count);
      setAppliedKey(listKey);
      setError(cached.error);
      setForbidden(cached.forbidden);
      setLoading(false);
      return;
    }
    setUsers([]);
    setCount(0);
    setAppliedKey("");
    setLoading(true);
    setError(null);
    setForbidden(false);
  }, [pk, kind, sessionUserId, listKey]);

  const load = useCallback(async () => {
    if (!Number.isFinite(pk)) {
      setError("invalid_id");
      setLoading(false);
      return;
    }
    const gen = nextRequestId(fetchGen);
    const startedUserId = userIdRef.current;
    setLoading(true);
    setError(null);
    setForbidden(false);
    try {
      const data = await fetchFollowList(pk, kind);
      if (!isLatestRequest(fetchGen, gen)) return;
      if (!isSameUserScope(startedUserId, userIdRef.current)) return;
      setUsers(data.users);
      setCount(data.count);
      setAppliedKey(listKey);
      writeFollowListCache(listKey, {
        users: data.users,
        count: data.count,
        forbidden: false,
        error: null,
      });
    } catch (err: unknown) {
      if (!isLatestRequest(fetchGen, gen)) return;
      if (!isSameUserScope(startedUserId, userIdRef.current)) return;
      const message = err instanceof Error ? err.message : "load_failed";
      setUsers([]);
      setCount(0);
      setAppliedKey(listKey);
      if (message === "forbidden") {
        setForbidden(true);
        writeFollowListCache(listKey, {
          users: [],
          count: 0,
          forbidden: true,
          error: null,
        });
      } else if (message === "unauthorized") {
        navigate(spaLoginPath(loginNext), { replace: true });
        return;
      } else {
        setError(message);
        writeFollowListCache(listKey, {
          users: [],
          count: 0,
          forbidden: false,
          error: message,
        });
      }
    } finally {
      if (isLatestRequest(fetchGen, gen)) setLoading(false);
    }
  }, [pk, kind, listKey, navigate, loginNext]);

  useEffect(() => {
    if (sessionLoading) return;
    if (!me?.authenticated) {
      navigate(spaLoginPath(loginNext), { replace: true });
      return;
    }
    void load();
  }, [sessionLoading, me?.authenticated, pk, kind, navigate, loginNext, load]);

  const phase = listContentPhase({
    browsePreview: false,
    loading: sessionLoading || loading,
    error: forbidden ? "forbidden" : error,
    itemCount: users.length,
    matchesCurrentQuery: appliedKey === listKey,
  });

  return (
    <div className="profile-page" data-spa-page={title}>
      <div className="main-inner">
        {Number.isFinite(pk) ? (
          <nav className="profile-tabs follow-list-tabs" aria-label="フォロー一覧">
            {FOLLOW_LIST_TABS.map((tab) => (
              <NavLink
                key={tab.kind}
                className={({ isActive }) =>
                  `profile-tab${isActive ? " is-active" : ""}`
                }
                to={followListPath(pk, tab.kind)}
                replace
                end
              >
                {tab.label}
              </NavLink>
            ))}
          </nav>
        ) : null}

        {phase === "skeleton" ? <PeopleListSkeleton /> : null}

        {phase === "error" && forbidden ? (
          <div className="profile-empty profile-locked">
            <p className="profile-locked__title">このリストは表示できません</p>
            <p>{followListForbiddenCopy()}</p>
          </div>
        ) : null}

        {phase === "error" && !forbidden ? (
          <p className="profile-empty">
            {followListLoadErrorCopy(error)}
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => void load()}
            >
              再試行
            </button>
          </p>
        ) : null}

        {phase === "empty" ? (
          <p className="profile-empty">{followListEmptyCopy(kind)}</p>
        ) : null}

        {phase === "ready" ? (
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
                    <strong>
                      <AccountDisplayName
                        name={u.display_name}
                        verified={u.is_operator_verified}
                      />
                    </strong>
                    <span>@{u.username || u.id}</span>
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        ) : null}

        {phase === "ready" && count > users.length ? (
          <p className="profile-empty">先頭 {users.length} 人を表示しています</p>
        ) : null}
      </div>
    </div>
  );
}
