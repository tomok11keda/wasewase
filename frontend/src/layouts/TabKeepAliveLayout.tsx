import {
  createContext,
  useContext,
  useEffect,
  useRef,
  useState,
  type CSSProperties,
  type HTMLAttributes,
  type ReactNode,
} from "react";
import { Outlet, useLocation } from "react-router-dom";
import { CommunitiesPage } from "../pages/CommunitiesPage";
import { FleaPage } from "../pages/FleaPage";
import { HomePage } from "../pages/HomePage";
import { TimetablePage } from "../pages/TimetablePage";
import { matchMainTab, type MainTabId } from "../lib/tabs";
import { useSpaNavDiag } from "../lib/spaNavDiag";
import { flashDiagMark } from "../lib/flashDiag";

/** Tab crossfade duration — keep in sync with shell.css */
export const TAB_CROSSFADE_MS = 220;

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
  leaving,
  children,
}: {
  tabId: MainTabId;
  active: boolean;
  leaving: boolean;
  children: ReactNode;
}) {
  const inertProps = !active
    ? ({ inert: true } as HTMLAttributes<HTMLDivElement>)
    : {};

  const className = [
    "tab-keep-alive-pane",
    active ? "is-active" : "",
    leaving ? "is-leaving" : "",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <div
      className={className}
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
 * Diag `no_transition`: keep-alive は維持し crossfade のみ無効。
 */
export function TabKeepAliveLayout() {
  const { pathname } = useLocation();
  const diag = useSpaNavDiag();
  const active = matchMainTab(pathname);
  const stackRef = useRef<HTMLDivElement | null>(null);
  const prevActiveRef = useRef<MainTabId | null>(active);
  const instant = diag.disableTransition;

  const [mounted, setMounted] = useState<Partial<Record<MainTabId, boolean>>>(
    () => (active ? { [active]: true } : {})
  );
  const [leaving, setLeaving] = useState<MainTabId | null>(null);
  const [stackMinHeight, setStackMinHeight] = useState<number | undefined>();

  useEffect(() => {
    if (!active) return;
    setMounted((prev) => {
      if (prev[active]) return prev;
      flashDiagMark("keepalive_pane_mount", { tabId: active });
      return { ...prev, [active]: true };
    });
  }, [active]);

  useEffect(() => {
    const prev = prevActiveRef.current;
    if (!active) {
      prevActiveRef.current = null;
      setLeaving(null);
      setStackMinHeight(undefined);
      return;
    }
    if (instant) {
      if (prev && prev !== active) {
        flashDiagMark("tab_transition_instant", {
          from: prev,
          to: active,
        });
      }
      prevActiveRef.current = active;
      setLeaving(null);
      setStackMinHeight(undefined);
      return;
    }
    if (prev && prev !== active && mounted[prev]) {
      flashDiagMark("tab_transition_start", {
        from: prev,
        to: active,
        ms: TAB_CROSSFADE_MS,
      });
      const root = stackRef.current;
      if (root) {
        const prevEl = root.querySelector(
          `[data-tab-pane="${prev}"]`
        ) as HTMLElement | null;
        const nextEl = root.querySelector(
          `[data-tab-pane="${active}"]`
        ) as HTMLElement | null;
        const h = Math.max(
          prevEl?.offsetHeight ?? 0,
          nextEl?.offsetHeight ?? 0,
          root.offsetHeight
        );
        if (h > 0) setStackMinHeight(h);
      }
      setLeaving(prev);
      const timer = window.setTimeout(() => {
        setLeaving(null);
        setStackMinHeight(undefined);
        flashDiagMark("tab_transition_end", {
          from: prev,
          to: active,
        });
      }, TAB_CROSSFADE_MS);
      prevActiveRef.current = active;
      return () => window.clearTimeout(timer);
    }
    prevActiveRef.current = active;
  }, [active, mounted, instant]);

  const showOutlet = active === null;

  return (
    <TabVisibilityContext.Provider value={active}>
      <div
        ref={stackRef}
        className={[
          showOutlet
            ? "tab-keep-alive-stack is-collapsed"
            : "tab-keep-alive-stack",
          instant ? "is-instant" : "",
        ]
          .filter(Boolean)
          .join(" ")}
        style={
          stackMinHeight
            ? ({ minHeight: stackMinHeight } as CSSProperties)
            : undefined
        }
        data-active-tab={active || ""}
      >
        {mounted.home ? (
          <TabPane
            tabId="home"
            active={active === "home"}
            leaving={leaving === "home"}
          >
            <HomePage />
          </TabPane>
        ) : null}
        {mounted.communities ? (
          <TabPane
            tabId="communities"
            active={active === "communities"}
            leaving={leaving === "communities"}
          >
            <CommunitiesPage />
          </TabPane>
        ) : null}
        {mounted.flea ? (
          <TabPane
            tabId="flea"
            active={active === "flea"}
            leaving={leaving === "flea"}
          >
            <FleaPage />
          </TabPane>
        ) : null}
        {mounted.timetable ? (
          <TabPane
            tabId="timetable"
            active={active === "timetable"}
            leaving={leaving === "timetable"}
          >
            <TimetablePage />
          </TabPane>
        ) : null}
      </div>

      <div
        className={
          showOutlet
            ? "tab-keep-alive-outlet"
            : "tab-keep-alive-outlet is-hidden"
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
