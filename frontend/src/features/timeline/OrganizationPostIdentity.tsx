import { Link } from "react-router-dom";
import { VerifiedOrganizationBadge } from "../../components/VerifiedOrganizationBadge";
import type { OrganizationPostDisplay } from "./organizationActor";

export function OrganizationPostAvatar({
  display,
  className,
  onNavigate,
}: {
  display: OrganizationPostDisplay;
  className: string;
  onNavigate?: () => void;
}) {
  const media = display.avatarUrl ? (
    <img
      className="user-avatar--image tweet-avatar__img"
      src={display.avatarUrl}
      alt=""
    />
  ) : (
    display.initial
  );
  if (display.href) {
    return (
      <Link
        className={className}
        to={display.href}
        aria-hidden="true"
        onClick={onNavigate}
      >
        {media}
      </Link>
    );
  }
  return (
    <span className={className} aria-hidden="true">
      {media}
    </span>
  );
}

export function OrganizationPostName({
  display,
  onNavigate,
  nameClassName = "tweet-author",
  kindClassName = "tweet-org-kind",
}: {
  display: OrganizationPostDisplay;
  onNavigate?: () => void;
  nameClassName?: string;
  kindClassName?: string;
}) {
  const name = (
    <span className="account-verified-name">
      <span className="account-verified-name__text">{display.name}</span>
      <VerifiedOrganizationBadge verified={display.isVerified} compact />
    </span>
  );
  return (
    <>
      {display.href ? (
        <Link className={nameClassName} to={display.href} onClick={onNavigate}>
          {name}
        </Link>
      ) : (
        <span className={nameClassName}>{name}</span>
      )}
      {display.kindLabel ? (
        <span className={kindClassName}>{display.kindLabel}</span>
      ) : null}
    </>
  );
}
