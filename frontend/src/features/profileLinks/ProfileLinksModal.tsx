import { useEffect, useId, useLayoutEffect, useRef } from "react";
import { createPortal } from "react-dom";
import { SfIcon } from "../../components/SfIcon";
import {
  profileLinkDisplayTitle,
  profileLinkHostname,
  safeExternalHref,
  type ProfileLinkItem,
  visibleProfileLinks,
} from "./profileLinks";

const FOCUSABLE_SELECTOR = [
  "a[href]",
  "button:not([disabled])",
  "textarea:not([disabled])",
  "input:not([disabled])",
  "select:not([disabled])",
  '[tabindex]:not([tabindex="-1"])',
].join(", ");

type Props = {
  open: boolean;
  links: ProfileLinkItem[];
  onClose: () => void;
  returnFocusTo?: HTMLElement | null;
};

function focusableIn(root: HTMLElement): HTMLElement[] {
  return Array.from(root.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR)).filter(
    (el) => !el.hasAttribute("disabled") && el.getAttribute("aria-hidden") !== "true"
  );
}

export function ProfileLinksModal({
  open,
  links,
  onClose,
  returnFocusTo,
}: Props) {
  const titleId = useId();
  const closeRef = useRef<HTMLButtonElement | null>(null);
  const dialogRef = useRef<HTMLDivElement | null>(null);
  const modalRef = useRef<HTMLDivElement | null>(null);
  const onCloseRef = useRef(onClose);
  const safe = visibleProfileLinks(links);
  onCloseRef.current = onClose;

  useLayoutEffect(() => {
    if (!open) return;
    const previouslyFocused =
      returnFocusTo ||
      (document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null);
    closeRef.current?.focus();

    const prevOverflow = document.body.style.overflow;
    const prevPaddingRight = document.body.style.paddingRight;
    document.body.style.overflow = "hidden";

    const marked: HTMLElement[] = [];
    const root = modalRef.current;
    for (const child of Array.from(document.body.children)) {
      if (!(child instanceof HTMLElement) || child === root) continue;
      if (child.hasAttribute("inert")) continue;
      child.setAttribute("inert", "");
      marked.push(child);
    }

    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onCloseRef.current();
        return;
      }
      if (event.key !== "Tab") return;
      const dialog = dialogRef.current;
      if (!dialog) return;
      const focusable = focusableIn(dialog);
      if (!focusable.length) {
        event.preventDefault();
        dialog.focus();
        return;
      }
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      const active = document.activeElement;
      if (event.shiftKey && (active === first || !dialog.contains(active))) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && (active === last || !dialog.contains(active))) {
        event.preventDefault();
        first.focus();
      }
    };

    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prevOverflow;
      document.body.style.paddingRight = prevPaddingRight;
      for (const el of marked) el.removeAttribute("inert");
      previouslyFocused?.focus();
    };
  }, [open, returnFocusTo]);

  useEffect(() => {
    if (!open) return;
    const dialog = dialogRef.current;
    if (dialog && !dialog.contains(document.activeElement)) {
      closeRef.current?.focus();
    }
  }, [open, safe.length]);

  if (!open) return null;

  return createPortal(
    <div ref={modalRef} className="profile-links-modal">
      <div className="profile-links-modal__backdrop" onClick={onClose} />
      <div
        ref={dialogRef}
        className="profile-links-modal__card"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
      >
        <header className="profile-links-modal__header">
          <h2 id={titleId}>リンク</h2>
          <button
            ref={closeRef}
            type="button"
            className="profile-links-modal__close"
            aria-label="閉じる"
            onClick={onClose}
          >
            ×
          </button>
        </header>
        <ul className="profile-links-modal__list">
          {safe.map((link) => {
            const href = safeExternalHref(link.url);
            if (!href) return null;
            return (
              <li key={`${link.id ?? "x"}-${link.url}`}>
                <a
                  className="profile-links-modal__item"
                  href={href}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  <SfIcon name="link" />
                  <span className="profile-links-modal__text">
                    <span className="profile-links-modal__title">
                      {profileLinkDisplayTitle(link)}
                    </span>
                    <span className="profile-links-modal__host">
                      {profileLinkHostname(link.url)}
                    </span>
                  </span>
                </a>
              </li>
            );
          })}
        </ul>
      </div>
    </div>,
    document.body
  );
}
