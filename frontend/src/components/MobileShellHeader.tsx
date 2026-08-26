import { Link } from "react-router-dom";
import { useSession } from "../lib/session";

type Props = {
  title: string;
  /** Bottom Nav トップレベルでは現在地が重複するため中央タイトルを隠す */
  hideTitle?: boolean;
  onOpenMenu: () => void;
};

const DM_ICON =
  "M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2z";
const NOTIFY_ICON =
  "M12 22c1.1 0 2-.9 2-2h-4c0 1.1.89 2 2 2zm6-6v-5c0-3.07-1.64-5.64-4.5-6.32V4c0-.83-.67-1.5-1.5-1.5s-1.5.67-1.5 1.5v.68C7.63 5.36 6 7.92 6 11v5l-2 2v1h16v-1l-2-2z";

export function MobileShellHeader({
  title,
  hideTitle = false,
  onOpenMenu,
}: Props) {
  const { me } = useSession();
  const user = me?.user;
  const dmUnread = me?.dm_unread_total || 0;
  const notifyUnread = me?.unread_notifications || 0;
  const showTitle = Boolean(title) && !hideTitle;

  return (
    <header
      className={`site-header mobile-only${showTitle ? "" : " site-header--no-title"}`}
    >
      {!showTitle ? (
        <h1 className="visually-hidden">{title || "わせわせ"}</h1>
      ) : null}
      <div className="shell-header-row">
        <div className="shell-header-start">
          <button
            type="button"
            className="shell-header-profile"
            onClick={onOpenMenu}
            aria-label={user ? "アカウントメニューを開く" : "メニューを開く"}
          >
            <span className="shell-header-avatar">
              {user ? user.initial : "?"}
            </span>
          </button>
        </div>
        {showTitle ? <h1 className="shell-header-title">{title}</h1> : null}
        <div className="shell-header-end">
          <Link className="shell-header-dm" to="/dm" aria-label="メッセージ">
            <svg viewBox="0 0 24 24" width={22} height={22} aria-hidden="true">
              <path d={DM_ICON} />
            </svg>
            {dmUnread > 0 ? (
              <span className="dm-nav-badge" aria-label={`未読 ${dmUnread}`}>
                {dmUnread > 99 ? "99+" : dmUnread}
              </span>
            ) : null}
          </Link>
          <Link
            className="shell-header-notify"
            to="/notifications"
            aria-label="通知"
          >
            <svg viewBox="0 0 24 24" width={22} height={22} aria-hidden="true">
              <path d={NOTIFY_ICON} />
            </svg>
            {notifyUnread > 0 ? (
              <span
                className="header-notify-badge"
                aria-label={`未読通知 ${notifyUnread}`}
              >
                {notifyUnread > 99 ? "99+" : notifyUnread}
              </span>
            ) : null}
          </Link>
        </div>
      </div>
    </header>
  );
}
