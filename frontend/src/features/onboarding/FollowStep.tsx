import { useEffect, useState } from "react";
import { toggleFollow } from "../profile/api";
import {
  completeFollowStep,
  fetchOnboardingSuggestions,
  type OnboardingSuggestion,
} from "./api";

type Props = {
  onDone: () => void;
};

export function FollowStep({ onDone }: Props) {
  const [users, setUsers] = useState<OnboardingSuggestion[]>([]);
  const [goal, setGoal] = useState(3);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [skipping, setSkipping] = useState(false);

  const load = async () => {
    const data = await fetchOnboardingSuggestions();
    setUsers(data.users);
    setGoal(data.follow_goal || 3);
  };

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    void load()
      .catch(() => {
        if (!cancelled) setError("おすすめユーザーを表示できません。");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const followingCount = users.filter((u) => u.is_following).length;
  const progress = Math.min(followingCount, goal);

  const onToggle = async (user: OnboardingSuggestion) => {
    setBusyId(user.id);
    try {
      const result = await toggleFollow(user.id);
      setUsers((prev) =>
        prev.map((row) =>
          row.id === user.id
            ? {
                ...row,
                is_following: result.is_following,
                follow_state: result.follow_state,
              }
            : row
        )
      );
    } catch {
      setError("フォローを更新できませんでした。");
    } finally {
      setBusyId(null);
    }
  };

  const goNext = async () => {
    setSkipping(true);
    setError(null);
    try {
      await completeFollowStep();
      onDone();
    } catch {
      setError("次の画面に進めませんでした。");
    } finally {
      setSkipping(false);
    }
  };

  return (
    <>
      <h1>早稲田生とつながろう</h1>
      <p className="hint">知っている人や気になる人をフォローしてみよう</p>
      <p className="onboarding-progress" aria-live="polite">
        {progress}/{goal}
      </p>

      {loading ? <p>読み込み中…</p> : null}
      {error ? <p className="field-error">{error}</p> : null}

      {!loading && users.length === 0 ? (
        <p className="hint">いま表示できるおすすめユーザーはいません。</p>
      ) : null}

      <ul className="onboarding-follow-list">
        {users.map((u) => (
          <li key={u.id} className="onboarding-follow-row">
            {u.avatar_url ? (
              <img className="search-user-avatar" src={u.avatar_url} alt="" />
            ) : (
              <span className="search-user-avatar is-initial">
                {u.initial || "?"}
              </span>
            )}
            <span className="search-user-text">
              <strong>{u.display_name}</strong>
              <span>@{u.username || u.id}</span>
              {u.department ? <span>{u.department}</span> : null}
            </span>
            <button
              type="button"
              className={`btn onboarding-follow-btn${
                u.is_following ? " is-following" : ""
              }`}
              disabled={busyId === u.id || skipping}
              onClick={() => void onToggle(u)}
            >
              {u.is_following ? "フォロー中" : "フォロー"}
            </button>
          </li>
        ))}
      </ul>

      <button
        type="button"
        className="btn"
        disabled={skipping}
        onClick={() => void goNext()}
      >
        次へ
      </button>
      <p className="footer-link">
        <button
          type="button"
          className="linkish"
          disabled={skipping}
          onClick={() => void goNext()}
        >
          今はスキップ
        </button>
      </p>
    </>
  );
}
