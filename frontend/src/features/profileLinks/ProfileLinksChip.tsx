import { useRef, useState } from "react";
import { SfIcon } from "../../components/SfIcon";
import { ProfileLinksModal } from "./ProfileLinksModal";
import {
  profileLinksChipLabel,
  safeExternalHref,
  type ProfileLinkItem,
  visibleProfileLinks,
} from "./profileLinks";

type Props = {
  links: ProfileLinkItem[];
};

export function ProfileLinksChip({ links }: Props) {
  const safe = visibleProfileLinks(links);
  const [open, setOpen] = useState(false);
  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const label = profileLinksChipLabel(safe);
  if (!label || !safe.length) return null;

  if (safe.length === 1) {
    const href = safeExternalHref(safe[0].url);
    if (!href) return null;
    return (
      <a
        className="profile-links-chip"
        href={href}
        target="_blank"
        rel="noopener noreferrer"
      >
        <SfIcon name="link" />
        <span className="profile-links-chip__label">{label}</span>
      </a>
    );
  }

  return (
    <>
      <button
        ref={triggerRef}
        type="button"
        className="profile-links-chip"
        aria-haspopup="dialog"
        aria-expanded={open}
        onClick={() => setOpen(true)}
      >
        <SfIcon name="link" />
        <span className="profile-links-chip__label">{label}</span>
      </button>
      <ProfileLinksModal
        open={open}
        links={safe}
        onClose={() => setOpen(false)}
        returnFocusTo={triggerRef.current}
      />
    </>
  );
}
