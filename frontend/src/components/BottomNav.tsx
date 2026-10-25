import { NavLink } from "react-router-dom";
import { useAccount } from "../lib/accountContext";
import { visibleTabRoutes } from "../lib/tabs";
import { useSpaNavDiag, withSpaNavDiagSearch } from "../lib/spaNavDiag";

export function BottomNav() {
  const diag = useSpaNavDiag();
  const { actor } = useAccount();
  const tabs = visibleTabRoutes(actor.type === "organization");

  return (
    <nav className="bottom-nav" aria-label="メイン">
      {tabs.map((tab) => (
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
