import { NavLink } from "react-router-dom";
import { TAB_ROUTES } from "../lib/tabs";
import { useSpaNavDiag, withSpaNavDiagSearch } from "../lib/spaNavDiag";

export function BottomNav() {
  const diag = useSpaNavDiag();

  return (
    <nav className="bottom-nav" aria-label="メイン">
      {TAB_ROUTES.map((tab) => (
        <NavLink
          key={tab.id}
          to={withSpaNavDiagSearch(tab.path, diag)}
          end={tab.path === "/"}
          className={({ isActive }) =>
            isActive ? "nav-item is-active" : "nav-item"
          }
        >
          {({ isActive }) => (
            <>
              <svg viewBox="0 0 24 24" width={24} height={24} aria-hidden="true">
                <path d={tab.icon} />
              </svg>
              <span>{tab.label}</span>
              {isActive ? <span className="visually-hidden">(現在のページ)</span> : null}
            </>
          )}
        </NavLink>
      ))}
    </nav>
  );
}
