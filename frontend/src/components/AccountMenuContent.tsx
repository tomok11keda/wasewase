import { Link, useNavigate } from "react-router-dom";
import type { ReactNode } from "react";
import { useAccount } from "../lib/accountContext";
import { useSession } from "../lib/session";
import { logoutRequest, performSpaLogout, spaLoginPath } from "../features/auth/api";
import { invalidateOwnProfileCacheAfterEdit } from "../features/profile/ownProfileCache";
import { organizationInitial } from "../features/orgs/orgProfile";
import { analyticsLogout } from "../lib/analytics/client";
import type { MeResponse } from "../lib/api";
import { WASEDA_OFFICIAL_SERVICE } from "../lib/wasedaOfficialLinks";
import { AccountAvatar } from "./AccountAvatar";
import { AccountSwitcher } from "./AccountSwitcher";
import { AccountDisplayName } from "./VerifiedAccountBadge";
import { VerifiedOrganizationBadge } from "./VerifiedOrganizationBadge";

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

/** Official Waseda portal — new tab / system browser, never the SPA or in-app WebView. */
function OfficialExternalLink({
  href,
  children,
  note,
  onNavigate,
}: {
  href: string;
  children: ReactNode;
  note: string;
  onNavigate?: () => void;
}) {
  return (
    <a
      className="more-link"
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      onClick={() => {
        onNavigate?.();
      }}
    >
      <span className="more-link-copy">
        {children}
        <small className="more-link-note">{note}</small>
      </span>
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
  const { actor, selectPersonal } = useAccount();
  const navigate = useNavigate();
  const user = me?.user;
  const notifyUnread = me?.unread_notifications || 0;
  const dmUnread = me?.dm_unread_total || 0;
  const orgActor = actor.type === "organization" ? actor.organization : null;

  const spaProfile = user ? `/app/users/${user.id}/posts` : "/app/";
  const identityPath = orgActor
    ? `/orgs/${orgActor.slug}`
    : user
      ? `/users/${user.id}/posts`
      : "/";
  const profilePath = identityPath;

  const go = (to: string) => {
    onNavigate?.();
    navigate(to);
  };

  const onLogout = async () => {
    selectPersonal();
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
    onNavigate?.();
    navigate("/login", { replace: true });
  };

  return (
    <div className="account-menu">
      {user ? (
        <button
          type="button"
          className="account-menu__identity"
          onClick={() => go(identityPath)}
        >
          <AccountAvatar
            url={orgActor ? orgActor.avatar_url : user.avatar_url}
            initial={
              orgActor ? organizationInitial(orgActor.name) : user.initial
            }
            className="account-menu__avatar"
          />
          <span className="account-menu__meta">
            <span className="account-menu__name">
              {orgActor ? (
                <>
                  {orgActor.name}
                  <VerifiedOrganizationBadge verified={orgActor.is_verified} />
                </>
              ) : (
                <AccountDisplayName
                  name={user.display_name}
                  verified={user.is_operator_verified}
                />
              )}
            </span>
            <span className="account-menu__handle">
              {orgActor ? "学生団体" : `@${user.username}`}
            </span>
          </span>
        </button>
      ) : null}

      {user ? <AccountSwitcher onNavigate={onNavigate} /> : null}

      <p className="more-section-title">アカウント</p>
      <ul className="more-list">
        {me?.authenticated && user ? (
          <>
            <li>
              <Link
                className="more-link"
                to={profilePath}
                onClick={() => onNavigate?.()}
              >
                プロフィール
              </Link>
            </li>
            {orgActor ? (
              <li>
                <Link
                  className="more-link"
                  to={`/orgs/${orgActor.slug}/edit`}
                  onClick={() => onNavigate?.()}
                >
                  団体プロフィールを編集
                </Link>
              </li>
            ) : null}
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
                onNavigate={() => {
                  if (user?.id) invalidateOwnProfileCacheAfterEdit(user.id);
                  onNavigate?.();
                }}
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

      <p className="more-section-title">大学サービス</p>
      <ul className="more-list">
        <li>
          <OfficialExternalLink
            href={WASEDA_OFFICIAL_SERVICE.href}
            note={WASEDA_OFFICIAL_SERVICE.note}
            onNavigate={onNavigate}
          >
            {WASEDA_OFFICIAL_SERVICE.label}
          </OfficialExternalLink>
        </li>
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
