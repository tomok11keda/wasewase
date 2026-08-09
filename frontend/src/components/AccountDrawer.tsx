import { useEffect, useRef } from "react";
import { useLocation } from "react-router-dom";
import { AccountMenuContent } from "./AccountMenuContent";

type Props = {
  open: boolean;
  onClose: () => void;
};

/**
 * Mobile account drawer — slides in from the left (X-style profile menu).
 * Desktop keeps the sticky SidebarNav; this panel is for the mobile header avatar.
 */
export function AccountDrawer({ open, onClose }: Props) {
  const location = useLocation();
  const locationKey = `${location.pathname}${location.search}`;
  const prevLocationKey = useRef(locationKey);

  useEffect(() => {
    if (prevLocationKey.current !== locationKey) {
      prevLocationKey.current = locationKey;
      if (open) onClose();
    }
  }, [locationKey, open, onClose]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    document.body.classList.add("account-drawer-open");
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.classList.remove("account-drawer-open");
    };
  }, [open, onClose]);

  return (
    <div
      className={`account-drawer${open ? " is-open" : ""}`}
      aria-hidden={!open}
    >
      <button
        type="button"
        className="account-drawer__backdrop"
        aria-label="メニューを閉じる"
        tabIndex={open ? 0 : -1}
        onClick={onClose}
      />
      <div
        className="account-drawer__panel"
        role="dialog"
        aria-modal="true"
        aria-label="アカウントメニュー"
      >
        <div className="account-drawer__header">
          <p className="account-drawer__title">メニュー</p>
          <button
            type="button"
            className="account-drawer__close"
            aria-label="閉じる"
            onClick={onClose}
          >
            ×
          </button>
        </div>
        <AccountMenuContent onNavigate={onClose} />
      </div>
    </div>
  );
}
