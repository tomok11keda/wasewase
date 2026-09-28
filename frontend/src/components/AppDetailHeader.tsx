import { useCallback, type ReactNode } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { matchDetailChrome, resolveDetailBack } from "../lib/chrome";

type Props = {
  right?: ReactNode;
};

export function AppDetailHeader({ right }: Props) {
  const location = useLocation();
  const navigate = useNavigate();
  const chrome = matchDetailChrome(location.pathname);
  const title = chrome?.title || "わせわせ";

  const onBack = useCallback(() => {
    const dest = resolveDetailBack(location.pathname, location.state);
    if (dest.mode === "history") {
      navigate(-1);
      return;
    }
    navigate(dest.to, dest.replace ? { replace: true } : undefined);
  }, [location.pathname, location.state, navigate]);

  return (
    <header className="site-header site-header--detail">
      <div className="shell-header-row">
        <div className="shell-header-start">
          <button
            type="button"
            className="shell-header-back"
            aria-label="戻る"
            onClick={onBack}
          >
            ←
          </button>
        </div>
        <h1 className="shell-header-title">{title}</h1>
        <div className="shell-header-end">{right}</div>
      </div>
    </header>
  );
}
