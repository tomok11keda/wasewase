import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useSession } from "../lib/session";
import {
  fetchNotifications,
  type NotificationItem,
} from "../features/notifications/api";
import { spaLoginPath } from "../features/auth/api";

function formatBadgeCount(n: number): string {
  if (n > 99) return "99+";
  return String(n);
}

function NotificationRow({ item }: { item: NotificationItem }) {
  const body = (
    <>
      <p className="notification-message">{item.message}</p>
      <time className="notification-time">{item.created_at}</time>
    </>
  );

  if (item.spa_path) {
    const [path, hash] = item.spa_path.split("#");
    return (
      <Link to={path || "/"} state={hash ? { hash } : undefined}>
        {body}
      </Link>
    );
  }
  // Prefer in-SPA navigation when link is already under /app/
  if (item.link?.startsWith("/app/") || item.link === "/app" || item.link?.startsWith("/app?")) {
    const raw = item.link === "/app" ? "/" : item.link.replace(/^\/app/, "") || "/";
    const [pathAndQuery, hash] = raw.split("#");
    const [path, query] = pathAndQuery.split("?");
    const to = query ? `${path || "/"}?${query}` : path || "/";
    return (
      <Link to={to} state={hash ? { hash } : undefined}>
        {body}
      </Link>
    );
  }
  if (item.link) {
    // Classic paths: Django redirects GET → /app/… when WASE_REACT_SPA is on
    return <a href={item.link}>{body}</a>;
  }
  return <div className="notification-static">{body}</div>;
}

export function NotificationsPage() {
  const { me, loading: sessionLoading, refresh } = useSession();
  const navigate = useNavigate();
  const [items, setItems] = useState<NotificationItem[]>([]);
  const [pendingFollowRequests, setPendingFollowRequests] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (sessionLoading) return;
    if (!me?.authenticated) {
      navigate(spaLoginPath("/app/notifications"), { replace: true });
      return;
    }
    const ac = new AbortController();
    setLoading(true);
    void fetchNotifications(true)
      .then((data) => {
        if (ac.signal.aborted) return;
        setItems(data.notifications || []);
        setPendingFollowRequests(Number(data.pending_follow_request_count || 0));
        setError(null);
        void refresh();
      })
      .catch((err) => {
        if (ac.signal.aborted) return;
        setError(err instanceof Error ? err.message : "load_failed");
      })
      .finally(() => {
        if (!ac.signal.aborted) setLoading(false);
      });
    return () => ac.abort();
  }, [sessionLoading, me?.authenticated, navigate, refresh]);

  if (sessionLoading || loading) {
    return (
      <div className="notifications-page" data-spa-page="通知">
        <main className="main-inner">
          <p>読み込み中…</p>
        </main>
      </div>
    );
  }

  const showEmpty = !error && items.length === 0;

  return (
    <div className="notifications-page" data-spa-page="通知">
      <main className="main-inner">
        <h1 className="page-title">通知</h1>

        <Link
          className="follow-request-entry"
          to="/settings/follow-requests"
          aria-label={
            pendingFollowRequests > 0
              ? `フォローリクエスト、未処理${pendingFollowRequests}件`
              : "フォローリクエスト"
          }
        >
          <span className="follow-request-entry__label">フォローリクエスト</span>
          {pendingFollowRequests > 0 ? (
            <span className="follow-request-entry__badge" aria-hidden="true">
              {formatBadgeCount(pendingFollowRequests)}
            </span>
          ) : null}
          <span className="follow-request-entry__chevron" aria-hidden="true">
            ›
          </span>
        </Link>

        {error ? (
          <p className="empty-message">読み込みに失敗しました（{error}）</p>
        ) : showEmpty ? (
          <p className="empty-message">通知はまだありません。</p>
        ) : (
          <ul className="notification-list">
            {items.map((n) => (
              <li
                key={n.id}
                className={`notification-item${n.is_read ? "" : " is-unread"}`}
              >
                <NotificationRow item={n} />
              </li>
            ))}
          </ul>
        )}
      </main>
    </div>
  );
}
