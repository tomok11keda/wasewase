import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useSession } from "../lib/session";
import { spaLoginPath } from "../features/auth/api";
import {
  acceptFollowRequest,
  fetchFollowRequests,
  rejectFollowRequest,
  type FollowRequestItem,
} from "../features/profile/api";
import { AccountDisplayName } from "../components/VerifiedAccountBadge";
import { PeopleListSkeleton } from "../components/skeleton";
import { listContentPhase, listQueryKey } from "../lib/listContentPhase";
import {
  isLatestRequest,
  isSameUserScope,
  nextRequestId,
} from "../lib/userScopedResult";

export function FollowRequestsPage() {
  const { me, loading: sessionLoading, refresh } = useSession();
  const navigate = useNavigate();
  const sessionUserId =
    me?.authenticated && me.user?.id != null ? me.user.id : null;
  const userIdRef = useRef(sessionUserId);
  userIdRef.current = sessionUserId;
  const fetchGen = useRef(0);
  const [items, setItems] = useState<FollowRequestItem[]>([]);
  const [appliedKey, setAppliedKey] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [flash, setFlash] = useState<string | null>(null);
  const listKey = listQueryKey([sessionUserId, "follow-requests"]);

  useLayoutEffect(() => {
    nextRequestId(fetchGen);
    setItems([]);
    setAppliedKey("");
    setLoading(true);
    setError(null);
    setFlash(null);
    setBusyId(null);
  }, [sessionUserId]);

  const load = useCallback(async () => {
    const gen = nextRequestId(fetchGen);
    const startedUserId = userIdRef.current;
    setLoading(true);
    setError(null);
    try {
      const list = await fetchFollowRequests();
      if (!isLatestRequest(fetchGen, gen)) return;
      if (!isSameUserScope(startedUserId, userIdRef.current)) return;
      setItems(list);
      setAppliedKey(listKey);
    } catch (err) {
      if (!isLatestRequest(fetchGen, gen)) return;
      if (!isSameUserScope(startedUserId, userIdRef.current)) return;
      setItems([]);
      setAppliedKey(listKey);
      setError(err instanceof Error ? err.message : "load_failed");
    } finally {
      if (isLatestRequest(fetchGen, gen)) setLoading(false);
    }
  }, [listKey]);

  useEffect(() => {
    if (sessionLoading) return;
    if (!me?.authenticated) {
      navigate(spaLoginPath("/app/settings/follow-requests"), { replace: true });
      return;
    }
    void load();
  }, [sessionLoading, me?.authenticated, navigate, load, sessionUserId]);

  const onAccept = async (id: number) => {
    if (busyId != null) return;
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
    if (busyId != null) return;
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

  const phase = listContentPhase({
    browsePreview: false,
    loading: sessionLoading || loading,
    error,
    itemCount: items.length,
    matchesCurrentQuery: appliedKey === listKey,
  });

  return (
    <div className="settings-page" data-spa-page="フォローリクエスト">
      <div className="main-inner">
        {flash ? <p className="settings-flash settings-flash--ok">{flash}</p> : null}
        {phase === "error" ? (
          <p className="settings-flash settings-flash--error">
            {error}
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => void load()}
            >
              再試行
            </button>
          </p>
        ) : null}

        {phase === "skeleton" ? <PeopleListSkeleton /> : null}
        {phase === "empty" ? (
          <p className="profile-empty">フォローリクエストはありません</p>
        ) : null}

        {phase === "ready" ? (
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
                      <strong>
                        <AccountDisplayName
                          name={u.display_name}
                          verified={u.is_operator_verified}
                        />
                      </strong>
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
        ) : null}
      </div>
    </div>
  );
}
