import { Link, NavLink, useNavigate } from "react-router-dom";
import { useSession } from "../lib/session";
import { logoutRequest, performSpaLogout, spaLoginPath } from "../features/auth/api";
import { analyticsLogout } from "../lib/analytics/client";
import { TAB_ROUTES } from "../lib/tabs";
import type { MeResponse } from "../lib/api";

const NOTIFY_ICON =
  "M12 22c1.1 0 2-.9 2-2h-4c0 1.1.89 2 2 2zm6-6v-5c0-3.07-1.64-5.64-4.5-6.32V4c0-.83-.67-1.5-1.5-1.5s-1.5.67-1.5 1.5v.68C7.63 5.36 6 7.92 6 11v5l-2 2v1h16v-1l-2-2z";
const DM_ICON =
  "M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2z";
const BOOKMARK_ICON =
  "M17 3H7c-1.1 0-2 .9-2 2v16l7-3 7 3V5c0-1.1-.9-2-2-2z";
const SETTINGS_ICON =
  "M19.14 12.94c.04-.31.06-.63.06-.94 0-.31-.02-.63-.06-.94l2.03-1.58c.18-.14.23-.41.12-.61l-1.92-3.32c-.12-.22-.37-.29-.59-.22l-2.39.96c-.5-.38-1.03-.7-1.62-.94l-.36-2.54c-.04-.24-.24-.41-.48-.41h-3.84c-.24 0-.43.17-.47.41l-.36 2.54c-.59.24-1.13.57-1.62.94l-2.39-.96c-.22-.08-.47 0-.59.22L2.74 8.87c-.12.21-.08.47.12.61l2.03 1.58c-.04.31-.06.63-.06.94s.02.63.06.94l-2.03 1.58c-.18.14-.23.41-.12.61l1.92 3.32c.12.22.37.29.59.22l2.39-.96c.5.38 1.03.7 1.62.94l.36 2.54c.05.24.24.41.48.41h3.84c.24 0 .44-.17.47-.41l.36-2.54c.59-.24 1.13-.56 1.62-.94l2.39.96c.22.08.47 0 .59-.22l1.92-3.32c.12-.22.07-.47-.12-.61l-2.01-1.58zM12 15.6c-1.98 0-3.6-1.62-3.6-3.6s1.62-3.6 3.6-3.6 3.6 1.62 3.6 3.6-1.62 3.6-3.6 3.6z";
const COMPOSE_ICON = "M3 17.25V21h3.75L17.81 9.94l-3.75-3.75L3 17.25zM20.71 7.04c.39-.39.39-1.02 0-1.41l-2.34-2.34a.9959.9959 0 0 0-1.41 0l-1.83 1.83 3.75 3.75 1.83-1.83z";

export function SidebarNav() {
  const { me, setMeFromAuth, refresh } = useSession();
  const navigate = useNavigate();
  const unread = me?.unread_notifications || 0;
  const dmUnread = me?.dm_unread_total || 0;
  const user = me?.user;

  const onLogout = async () => {
    try {
      await performSpaLogout();
    } catch {
      try {
        await logoutRequest();
      } catch {
        /* ignore */
      }
    }
    analyticsLogout();
    setMeFromAuth({
      authenticated: false,
      is_browse_mode: false,
      react_spa_enabled: true,
      user: null,
      unread_notifications: 0,
      dm_unread_total: 0,
    } as MeResponse);
    await refresh();
    navigate("/login", { replace: true });
  };

  return (
    <nav className="sidebar-left-inner" aria-label="メインナビゲーション">
      <NavLink to="/" className="sidebar-brand" aria-label="わせわせ ホーム" end>
        <span className="sidebar-brand__mark" aria-hidden="true">
          わ
        </span>
        <span className="sidebar-brand__text">わせわせ</span>
      </NavLink>

      <ul className="sidebar-nav">
        {TAB_ROUTES.map((tab) => (
          <li key={tab.id}>
            <NavLink
              to={tab.path}
              end={tab.path === "/"}
              className={({ isActive }) =>
                isActive ? "sidebar-nav__item is-active" : "sidebar-nav__item"
              }
            >
              <svg viewBox="0 0 24 24" width={24} height={24} aria-hidden="true">
                <path d={tab.icon} />
              </svg>
              <span className="sidebar-nav__label">{tab.label}</span>
            </NavLink>
          </li>
        ))}
        <li>
          <NavLink
            to="/notifications"
            className={({ isActive }) =>
              isActive ? "sidebar-nav__item is-active" : "sidebar-nav__item"
            }
          >
            <svg viewBox="0 0 24 24" width={24} height={24} aria-hidden="true">
              <path d={NOTIFY_ICON} />
            </svg>
            <span className="sidebar-nav__label">通知</span>
            {unread > 0 ? (
              <span className="sidebar-nav__badge" aria-label={`未読通知 ${unread}件`}>
                {unread}
              </span>
            ) : null}
          </NavLink>
        </li>
        <li>
          <NavLink
            to="/dm"
            className={({ isActive }) =>
              isActive ? "sidebar-nav__item is-active" : "sidebar-nav__item"
            }
          >
            <svg viewBox="0 0 24 24" width={24} height={24} aria-hidden="true">
              <path d={DM_ICON} />
            </svg>
            <span className="sidebar-nav__label">メッセージ</span>
            {dmUnread > 0 ? (
              <span className="sidebar-nav__badge" aria-label={`未読 ${dmUnread}`}>
                {dmUnread}
              </span>
            ) : null}
          </NavLink>
        </li>
        {user ? (
          <li>
            <NavLink
              className={({ isActive }) =>
                isActive ? "sidebar-nav__item is-active" : "sidebar-nav__item"
              }
              to={`/users/${user.id}/bookmarks`}
            >
              <svg viewBox="0 0 24 24" width={24} height={24} aria-hidden="true">
                <path d={BOOKMARK_ICON} />
              </svg>
              <span className="sidebar-nav__label">ブックマーク</span>
            </NavLink>
          </li>
        ) : null}
        <li>
          <NavLink
            to="/settings"
            className={({ isActive }) =>
              isActive ? "sidebar-nav__item is-active" : "sidebar-nav__item"
            }
          >
            <svg viewBox="0 0 24 24" width={24} height={24} aria-hidden="true">
              <path d={SETTINGS_ICON} />
            </svg>
            <span className="sidebar-nav__label">アカウント設定</span>
          </NavLink>
        </li>
      </ul>

      {me?.authenticated ? (
        <button
          type="button"
          className="sidebar-nav__compose"
          onClick={() => navigate("/", { state: { openCompose: true } })}
        >
          <svg viewBox="0 0 24 24" width={24} height={24} aria-hidden="true">
            <path d={COMPOSE_ICON} />
          </svg>
          <span className="sidebar-nav__compose-label">投稿する</span>
        </button>
      ) : (
        <Link className="sidebar-nav__compose" to={spaLoginPath("/app/?compose=1")}>
          <svg viewBox="0 0 24 24" width={24} height={24} aria-hidden="true">
            <path d={COMPOSE_ICON} />
          </svg>
          <span className="sidebar-nav__compose-label">投稿する</span>
        </Link>
      )}

      <div className={`sidebar-user${user ? "" : " sidebar-user--guest"}`}>
        {user ? (
          <>
            <Link className="sidebar-user__link" to={`/users/${user.id}/posts`}>
              <span className="sidebar-user__avatar" aria-hidden="true">
                {user.initial}
              </span>
              <span className="sidebar-user__meta">
                <span className="sidebar-user__name">{user.display_name}</span>
                <span className="sidebar-user__handle">@{user.username}</span>
              </span>
            </Link>
            <button
              type="button"
              className="sidebar-nav__item"
              onClick={() => void onLogout()}
              style={{
                width: "100%",
                border: "none",
                background: "transparent",
                cursor: "pointer",
                textAlign: "left",
              }}
            >
              <span className="sidebar-nav__label">ログアウト</span>
            </button>
          </>
        ) : (
          <>
            <Link className="sidebar-nav__item" to={spaLoginPath("/app/")}>
              <span className="sidebar-nav__label">ログイン</span>
            </Link>
            <Link className="sidebar-nav__item" to="/signup">
              <span className="sidebar-nav__label">新規登録</span>
            </Link>
          </>
        )}
      </div>
    </nav>
  );
}
