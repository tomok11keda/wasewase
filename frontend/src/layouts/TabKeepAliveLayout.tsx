import {
  createContext,
  useContext,
  useEffect,
  useRef,
  useState,
  type HTMLAttributes,
  type ReactNode,
} from "react";
import { Outlet, useLocation } from "react-router-dom";
import { CommunitiesPage } from "../pages/CommunitiesPage";
import { FleaPage } from "../pages/FleaPage";
import { HomePage } from "../pages/HomePage";
import { TimetablePage } from "../pages/TimetablePage";
import { MorePage } from "../pages/tabs";
import { matchMainTab, type MainTabId } from "../lib/tabs";

const TabVisibilityContext = createContext<MainTabId | null>(null);

/** Active main BottomNav tab, or null when on a nested / non-tab route. */
export function useActiveMainTab(): MainTabId | null {
  return useContext(TabVisibilityContext);
}

/**
 * Soft-refetch when returning to a kept-alive tab.
 * Skips the first activation (initial mount fetch owns that).
 */
export function useSoftTabRefetch(
  tabId: MainTabId,
  refetch: () => void | Promise<void>
): void {
  const active = useActiveMainTab();
  const wasActiveRef = useRef(active === tabId);

  useEffect(() => {
    const now = active === tabId;
    if (now && !wasActiveRef.current) {
      void refetch();
    }
    wasActiveRef.current = now;
  }, [active, tabId, refetch]);
}

function TabPane({
  tabId,
  active,
  children,
}: {
  tabId: MainTabId;
  active: boolean;
  children: ReactNode;
}) {
  const inertProps = !active
    ? ({ inert: true } as HTMLAttributes<HTMLDivElement>)
    : {};
  return (
    <div
      className={active ? "tab-keep-alive-pane is-active" : "tab-keep-alive-pane"}
      data-tab-pane={tabId}
      aria-hidden={!active}
      {...inertProps}
    >
      {children}
    </div>
  );
}

/**
 * Keep BottomNav primary tabs mounted after first visit (lazy keep-alive).
 * Nested routes (profile, DM, flea detail, …) still render via <Outlet />.
 */
export function TabKeepAliveLayout() {
  const { pathname } = useLocation();
  const active = matchMainTab(pathname);

  const [mounted, setMounted] = useState<Partial<Record<MainTabId, boolean>>>(
    () => (active ? { [active]: true } : {})
  );

  useEffect(() => {
    if (!active) return;
    setMounted((prev) => (prev[active] ? prev : { ...prev, [active]: true }));
  }, [active]);

  const showOutlet = active === null;

  return (
    <TabVisibilityContext.Provider value={active}>
      {mounted.home ? (
        <TabPane tabId="home" active={active === "home"}>
          <HomePage />
        </TabPane>
      ) : null}
      {mounted.communities ? (
        <TabPane tabId="communities" active={active === "communities"}>
          <CommunitiesPage />
        </TabPane>
      ) : null}
      {mounted.flea ? (
        <TabPane tabId="flea" active={active === "flea"}>
          <FleaPage />
        </TabPane>
      ) : null}
      {mounted.timetable ? (
        <TabPane tabId="timetable" active={active === "timetable"}>
          <TimetablePage />
        </TabPane>
      ) : null}
      {mounted.more ? (
        <TabPane tabId="more" active={active === "more"}>
          <MorePage />
        </TabPane>
      ) : null}

      <div
        className={
          showOutlet ? "tab-keep-alive-outlet" : "tab-keep-alive-outlet is-hidden"
        }
        hidden={!showOutlet}
        aria-hidden={!showOutlet}
      >
        <Outlet />
      </div>
    </TabVisibilityContext.Provider>
  );
}

/** Route element for main tabs — content comes from keep-alive panes. */
export function MainTabRoute() {
  return null;
}
