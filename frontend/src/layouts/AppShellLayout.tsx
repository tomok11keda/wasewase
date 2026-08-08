import { Outlet, useLocation } from "react-router-dom";
import { BottomNav } from "../components/BottomNav";
import { BrowseModeBanner } from "../components/BrowseModeBanner";
import { MobileShellHeader } from "../components/MobileShellHeader";
import { SidebarNav } from "../components/SidebarNav";
import { SidebarWidgets } from "../components/SidebarWidgets";
import { useSession } from "../lib/session";
import { TAB_ROUTES } from "../lib/tabs";

function titleForPath(pathname: string): string {
  const normalized = pathname.replace(/\/$/, "") || "/";
  if (normalized.startsWith("/users/")) return "プロフィール";
  if (normalized.startsWith("/search")) return "検索";
  if (normalized.startsWith("/notifications")) return "通知";
  if (normalized.startsWith("/dm")) return "メッセージ";
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

  return (
    <>
      <div className="app-shell">
        <aside className="sidebar-left" aria-label="サイドナビ">
          <SidebarNav />
        </aside>

        <div className="main-column">
          <MobileShellHeader title={title} />
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

      <div className="shell-hide-on-desktop">
        <BottomNav />
      </div>
    </>
  );
}
