import { useCallback, useEffect, useState } from "react";
import { Outlet, useLocation } from "react-router-dom";
import { AccountDrawer } from "../components/AccountDrawer";
import { BottomNav } from "../components/BottomNav";
import { BrowseModeBanner } from "../components/BrowseModeBanner";
import { MobileShellHeader } from "../components/MobileShellHeader";
import { SidebarNav } from "../components/SidebarNav";
import { SidebarWidgets } from "../components/SidebarWidgets";
import { useSession } from "../lib/session";
import { shouldHideBottomNav, TAB_ROUTES } from "../lib/tabs";

function titleForPath(pathname: string): string {
  const normalized = pathname.replace(/\/$/, "") || "/";
  if (normalized.startsWith("/users/")) return "プロフィール";
  if (normalized.startsWith("/search")) return "検索";
  if (normalized.startsWith("/notifications")) return "通知";
  if (normalized.startsWith("/dm")) return "メッセージ";
  if (normalized === "/more") return "メニュー";
  if (normalized.startsWith("/settings")) return "設定";
  const hit = TAB_ROUTES.find((tab) => {
    if (tab.path === "/") return normalized === "/" || normalized === "";
    return normalized === tab.path || normalized.startsWith(`${tab.path}/`);
  });
  return hit?.title || "わせわせ";
}

export function AppShellLayout() {
  const { loading } = useSession();
  const location = useLocation();
  const title = titleForPath(location.pathname);
  const hideBottomNav = shouldHideBottomNav(location.pathname);
  const [menuOpen, setMenuOpen] = useState(false);
  const openMenu = useCallback(() => setMenuOpen(true), []);
  const closeMenu = useCallback(() => setMenuOpen(false), []);

  useEffect(() => {
    document.body.classList.toggle("shell-hide-bottom-nav", hideBottomNav);
    return () => {
      document.body.classList.remove("shell-hide-bottom-nav");
    };
  }, [hideBottomNav]);

  return (
    <>
      <div className="app-shell">
        <aside className="sidebar-left" aria-label="サイドナビ">
          <SidebarNav />
        </aside>

        <div className="main-column">
          <MobileShellHeader title={title} onOpenMenu={openMenu} />
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
