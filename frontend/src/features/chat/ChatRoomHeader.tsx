import type { MouseEvent, ReactNode } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { SfIcon } from "../../components/SfIcon";
import { SkeletonBone, SkeletonCircle } from "../../components/skeleton";
import { requestStackHeaderBack } from "../../lib/detailTransition";

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
  /** Header chrome only — no details link until the room API confirms access. */
  pending?: boolean;
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
  pending = false,
}: Props) {
  const location = useLocation();
  const navigate = useNavigate();
  const initial = (avatarInitial || title || "?").slice(0, 1);
  const showDetails = Boolean(detailsTo) && !pending;
  const avatar = pending && !avatarUrl && !avatarInitial ? (
    <SkeletonCircle
      size={36}
      className={`chat-room-header__avatar chat-room-header__avatar--${avatarShape}`}
    />
  ) : (
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
        {title ? (
          <span className="chat-room-header__title">{title}</span>
        ) : pending ? (
          <SkeletonBone className="sk-chat-title" />
        ) : (
          <span className="chat-room-header__title">{title}</span>
        )}
        {subtitle ? (
          <span className="chat-room-header__subtitle">{subtitle}</span>
        ) : pending ? (
          <SkeletonBone className="sk-chat-subtitle" />
        ) : null}
      </span>
    </>
  );

  const onStackBack = (event: MouseEvent<HTMLAnchorElement>) => {
    if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    requestStackHeaderBack(navigate, backTo, location.state);
  };

  return (
    <header className="chat-room-header">
      <Link
        className="chat-room-header__back"
        to={backTo}
        aria-label={backLabel}
        onClick={onStackBack}
      >
        <span className="chat-room-header__back-icon" aria-hidden="true">
          ‹
        </span>
      </Link>
      {showDetails && detailsTo ? (
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
        {showDetails ? (
          <Link
            className="chat-room-header__more"
            to={detailsTo || backTo}
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
