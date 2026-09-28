import { useCallback, useEffect, useState } from "react";
import { Outlet, useLocation } from "react-router-dom";
import { AccountDrawer } from "../components/AccountDrawer";
import { AppDetailHeader } from "../components/AppDetailHeader";
import { BottomNav } from "../components/BottomNav";
import { BrowseModeBanner } from "../components/BrowseModeBanner";
import { MobileShellHeader } from "../components/MobileShellHeader";
import { SidebarNav } from "../components/SidebarNav";
import { SidebarWidgets } from "../components/SidebarWidgets";
import { applyChromeModeClass, matchChromeMode } from "../lib/chrome";
import { useSession } from "../lib/session";
import { matchMainTab, shouldHideBottomNav, TAB_ROUTES } from "../lib/tabs";

function titleForMainPath(pathname: string): string {
  const normalized = pathname.replace(/\/$/, "") || "/";
  const hit = TAB_ROUTES.find((tab) => {
    if (tab.path === "/") return normalized === "/" || normalized === "";
    return normalized === tab.path;
  });
  return hit?.title || "わせわせ";
}

export function AppShellLayout() {
  const { loading } = useSession();
  const location = useLocation();
  const chromeMode = matchChromeMode(location.pathname);
  const title = titleForMainPath(location.pathname);
  const hideShellTitle = matchMainTab(location.pathname) != null;
  const hideBottomNav = shouldHideBottomNav(location.pathname);
  const [menuOpen, setMenuOpen] = useState(false);
  const openMenu = useCallback(() => setMenuOpen(true), []);
  const closeMenu = useCallback(() => setMenuOpen(false), []);

  useEffect(() => {
    applyChromeModeClass(chromeMode, document.documentElement);
    applyChromeModeClass(chromeMode, document.body);
  }, [chromeMode]);

  useEffect(() => {
    document.body.classList.toggle("shell-hide-bottom-nav", hideBottomNav);
    document.documentElement.classList.toggle(
      "shell-hide-bottom-nav",
      hideBottomNav
    );
    return () => {
      document.body.classList.remove("shell-hide-bottom-nav");
      document.documentElement.classList.remove("shell-hide-bottom-nav");
    };
  }, [hideBottomNav]);

  return (
    <>
      <div className="app-shell" data-chrome-mode={chromeMode}>
        <aside className="sidebar-left" aria-label="サイドナビ">
          <SidebarNav />
        </aside>

        <div className="main-column">
          {chromeMode === "main" ? (
            <MobileShellHeader
              title={title}
              hideTitle={hideShellTitle}
              onOpenMenu={openMenu}
            />
          ) : null}
          {chromeMode === "detail" ? <AppDetailHeader /> : null}
          <BrowseModeBanner />
          {loading ? (
            <div className="main-inner">
              <div className="spa-placeholder">
                <p>読み込み中…</p>
              </div>
            </div>
          ) : (
            <Outlet />
          )}
        </div>

        <aside className="sidebar-right" aria-label="サイド情報">
          <SidebarWidgets />
        </aside>
      </div>

      {!hideBottomNav ? (
        <div className="shell-hide-on-desktop">
          <BottomNav />
        </div>
      ) : null}

      <AccountDrawer open={menuOpen} onClose={closeMenu} />
    </>
  );
}
