import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { SfIcon } from "../../components/SfIcon";

type Props = {
  backTo: string;
  backLabel?: string;
  title: string;
  subtitle?: string;
  avatarUrl?: string;
  avatarInitial?: string;
  avatarShape?: "circle" | "rounded";
  detailsTo?: string;
  detailsLabel?: string;
  detailsState?: unknown;
  trailing?: ReactNode;
};

export function ChatRoomHeader({
  backTo,
  backLabel = "戻る",
  title,
  subtitle,
  avatarUrl,
  avatarInitial,
  avatarShape = "circle",
  detailsTo,
  detailsLabel = "チャット詳細",
  detailsState,
  trailing,
}: Props) {
  const initial = (avatarInitial || title || "?").slice(0, 1);
  const avatar = (
    <span
      className={`chat-room-header__avatar chat-room-header__avatar--${avatarShape}`}
      aria-hidden="true"
    >
      {avatarUrl ? (
        <img className="user-avatar--image" src={avatarUrl} alt="" />
      ) : (
        <span className="user-avatar--initial">{initial}</span>
      )}
    </span>
  );

  const identity = (
    <>
      {avatar}
      <span className="chat-room-header__text">
        <span className="chat-room-header__title">{title}</span>
        {subtitle ? (
          <span className="chat-room-header__subtitle">{subtitle}</span>
        ) : null}
      </span>
    </>
  );

  return (
    <header className="chat-room-header">
      <Link className="chat-room-header__back" to={backTo} aria-label={backLabel}>
        <span className="chat-room-header__back-icon" aria-hidden="true">
          ‹
        </span>
      </Link>
      {detailsTo ? (
        <Link
          className="chat-room-header__main"
          to={detailsTo}
          state={detailsState}
          aria-label={`${title}の詳細`}
        >
          {identity}
        </Link>
      ) : (
        <div className="chat-room-header__main">{identity}</div>
      )}
      <div className="chat-room-header__end">
        {trailing}
        {detailsTo ? (
          <Link
            className="chat-room-header__more"
            to={detailsTo}
            state={detailsState}
            aria-label={detailsLabel}
          >
            <SfIcon name="ellipsis" size={20} />
          </Link>
        ) : null}
      </div>
    </header>
  );
}
