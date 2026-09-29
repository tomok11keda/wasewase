import { useCallback, type ReactNode } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { matchDetailChrome } from "../lib/chrome";
import { requestDetailHeaderBack } from "../lib/detailTransition";

type Props = {
  right?: ReactNode;
};

export function AppDetailHeader({ right }: Props) {
  const location = useLocation();
  const navigate = useNavigate();
  const chrome = matchDetailChrome(location.pathname);
  const title = chrome?.title || "わせわせ";

  const onBack = useCallback(() => {
    requestDetailHeaderBack(navigate, location.pathname, location.state);
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
