import { useEffect, useId, useState } from "react";
import { createPortal } from "react-dom";
import { Link } from "react-router-dom";
import { saveScrollPosition } from "../profile/api";
import {
  fetchTimelineLikers,
  type TimelineAuthor,
} from "./api";

type Liker = NonNullable<TimelineAuthor>;

type Props = {
  postId: number;
  open: boolean;
  onClose: () => void;
};

export function LikerListModal({ postId, open, onClose }: Props) {
  const titleId = useId();
  const [users, setUsers] = useState<Liker[]>([]);
  const [count, setCount] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
    };
  }, [open, onClose]);

  useEffect(() => {
    if (!open) return;
    const ac = new AbortController();
    setLoading(true);
    setError(null);
    setUsers([]);
    setCount(0);
    void fetchTimelineLikers(postId, ac.signal)
      .then((data) => {
        if (ac.signal.aborted) return;
        setUsers(data.users);
        setCount(data.count);
        setError(null);
      })
      .catch((err: unknown) => {
        if (ac.signal.aborted) return;
        setUsers([]);
        setCount(0);
        setError(err instanceof Error ? err.message : "load_failed");
      })
      .finally(() => {
        if (!ac.signal.aborted) setLoading(false);
      });
    return () => ac.abort();
  }, [open, postId]);

  if (!open) return null;

  return createPortal(
    <div className="compose-modal spa-compose-modal" aria-hidden="false">
      <div className="compose-modal__backdrop" onClick={onClose} />
      <div
        className="compose-modal__panel"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
      >
        <header className="compose-modal__header">
          <h2 id={titleId}>いいねした人</h2>
          <button
            type="button"
            className="compose-modal__close"
            aria-label="閉じる"
            onClick={onClose}
          >
            ×
          </button>
        </header>
        {loading ? <p className="empty-message">読み込み中…</p> : null}
        {!loading && error ? (
          <p className="empty-message">表示できません（{error}）</p>
        ) : null}
        {!loading && !error && users.length === 0 ? (
          <p className="empty-message">まだいいねした人はいません</p>
        ) : null}
        {!loading && !error && users.length > 0 ? (
          <ul className="follow-list">
            {users.map((u) => (
              <li key={u.id}>
                <Link
                  className="search-user-card"
                  to={`/users/${u.id}/posts`}
                  onClick={() => {
                    saveScrollPosition("/");
                    onClose();
                  }}
                >
                  {u.avatar_url ? (
                    <img className="search-user-avatar" src={u.avatar_url} alt="" />
                  ) : (
                    <span className="search-user-avatar is-initial">
                      {u.initial || "?"}
                    </span>
                  )}
                  <span className="search-user-text">
                    <strong>{u.display_name || u.username || "ユーザー"}</strong>
                    <span>@{u.username || u.id}</span>
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        ) : null}
        {!loading && !error && count > users.length ? (
          <p className="empty-message">先頭 {users.length} 人を表示しています</p>
        ) : null}
      </div>
    </div>,
    document.body
  );
}
