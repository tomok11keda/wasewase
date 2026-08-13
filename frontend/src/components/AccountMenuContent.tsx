import { Link, useNavigate } from "react-router-dom";
import type { ReactNode } from "react";
import { useSession } from "../lib/session";
import { logoutRequest, spaLoginPath } from "../features/auth/api";
import { analyticsLogout } from "../lib/analytics/client";
import type { MeResponse } from "../lib/api";

function ClassicLink({
  href,
  children,
  onNavigate,
}: {
  href: string;
  children: ReactNode;
  onNavigate?: () => void;
}) {
  return (
    <a
      className="more-link"
      href={href}
      onClick={() => {
        onNavigate?.();
      }}
    >
      {children}
      <small className="more-link-note">（従来ページ）</small>
    </a>
  );
}

type Props = {
  /** Called after SPA navigation or logout so drawers can close. */
  onNavigate?: () => void;
  showSearchLink?: boolean;
};

/**
 * Account + utility links formerly under 「その他」.
 * Does not list primary bottom-nav destinations (検索 is a main tab).
 */
export function AccountMenuContent({
  onNavigate,
  showSearchLink = false,
}: Props) {
  const { me, setMeFromAuth, refresh } = useSession();
  const navigate = useNavigate();
  const user = me?.user;
  const notifyUnread = me?.unread_notifications || 0;
  const dmUnread = me?.dm_unread_total || 0;

  const spaProfile = user ? `/app/users/${user.id}/posts` : "/app/";

  const go = (to: string) => {
    onNavigate?.();
    navigate(to);
  };

  const onLogout = async () => {
    try {
      await logoutRequest();
    } catch {
      /* ignore */
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
    onNavigate?.();
    navigate("/login", { replace: true });
  };

  return (
    <div className="account-menu">
      {user ? (
        <button
          type="button"
          className="account-menu__identity"
          onClick={() => go(`/users/${user.id}/posts`)}
        >
          <span className="account-menu__avatar" aria-hidden="true">
            {user.initial}
          </span>
          <span className="account-menu__meta">
            <span className="account-menu__name">{user.display_name}</span>
            <span className="account-menu__handle">@{user.username}</span>
          </span>
        </button>
      ) : null}

      <p className="more-section-title">アカウント</p>
      <ul className="more-list">
        {me?.authenticated && user ? (
          <>
            <li>
              <Link
                className="more-link"
                to={`/users/${user.id}/posts`}
                onClick={() => onNavigate?.()}
              >
                プロフィール
              </Link>
            </li>
            <li>
              <Link
                className="more-link"
                to={`/users/${user.id}/flea`}
                onClick={() => onNavigate?.()}
              >
                公開プロフィール（フリマ）
              </Link>
            </li>
            <li>
              <ClassicLink
                href={`/mypage/edit/?next=${encodeURIComponent(spaProfile)}`}
                onNavigate={onNavigate}
              >
                プロフィール設定
              </ClassicLink>
            </li>
            <li>
              <Link
                className="more-link"
                to="/settings"
                onClick={() => onNavigate?.()}
              >
                アカウント設定
              </Link>
            </li>
            <li>
              <ClassicLink
                href="/mypage/settings/blocked/"
                onNavigate={onNavigate}
              >
                ブロック一覧
              </ClassicLink>
            </li>
            <li>
              <ClassicLink href="/mypage/settings/" onNavigate={onNavigate}>
                退会など
              </ClassicLink>
            </li>
            <li>
              <button
                type="button"
                className="more-link more-link-button"
                onClick={() => void onLogout()}
              >
                ログアウト
              </button>
            </li>
          </>
        ) : (
          <>
            <li>
              <Link
                className="more-link"
                to={spaLoginPath("/app/")}
                onClick={() => onNavigate?.()}
              >
                ログイン
              </Link>
            </li>
            <li>
              <Link
                className="more-link"
                to="/signup"
                onClick={() => onNavigate?.()}
              >
                新規登録
              </Link>
            </li>
          </>
        )}
      </ul>

      <p className="more-section-title">便利機能</p>
      <ul className="more-list">
        {user ? (
          <li>
            <Link
              className="more-link"
              to={`/users/${user.id}/bookmarks`}
              onClick={() => onNavigate?.()}
            >
              ブックマーク
            </Link>
          </li>
        ) : null}
        <li>
          <Link
            className="more-link"
            to="/notifications"
            onClick={() => onNavigate?.()}
          >
            通知
            {notifyUnread > 0 ? (
              <span className="account-menu__badge">{notifyUnread}</span>
            ) : null}
          </Link>
        </li>
        <li>
          <Link className="more-link" to="/dm" onClick={() => onNavigate?.()}>
            メッセージ
            {dmUnread > 0 ? (
              <span className="account-menu__badge">{dmUnread}</span>
            ) : null}
          </Link>
        </li>
        {showSearchLink ? (
          <li>
            <Link
              className="more-link"
              to="/search"
              onClick={() => onNavigate?.()}
            >
              検索
            </Link>
          </li>
        ) : null}
      </ul>
    </div>
  );
}
