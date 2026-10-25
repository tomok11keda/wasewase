import { useEffect } from "react";
import { TIMELINE_FEED_SKELETON_COUNT } from "../features/timeline/timelineFeedPhase";
import { PostCardSkeleton, SkeletonCircle } from "./skeleton";
import { applyChromeModeClass, matchChromeMode } from "../lib/chrome";
import {
  bootHeaderTitle,
  bootShowsBottomNav,
  bootSkeletonKind,
} from "../lib/bootSkeleton";
import { matchMainTab, normalizeSpaPath, TAB_ROUTES } from "../lib/tabs";

const DM_ICON =
  "M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2z";
const NOTIFY_ICON =
  "M12 22c1.1 0 2-.9 2-2h-4c0 1.1.89 2 2 2zm6-6v-5c0-3.07-1.64-5.64-4.5-6.32V4c0-.83-.67-1.5-1.5-1.5s-1.5.67-1.5 1.5v.68C7.63 5.36 6 7.92 6 11v5l-2 2v1h16v-1l-2-2z";

export function BootSkeletonFeed({
  kind = "timeline",
}: {
  kind?: "timeline" | "neutral";
}) {
  return (
    <div className="boot-skeleton-feed">
      <PostCardSkeleton
        count={kind === "timeline" ? TIMELINE_FEED_SKELETON_COUNT : 3}
      />
    </div>
  );
}

function BootHeader({ pathname }: { pathname: string }) {
  const chrome = matchChromeMode(pathname);
  const title = bootHeaderTitle(pathname);
  const showTitle = Boolean(title);
  const isDetail = chrome === "detail" || chrome === "conversation";

  return (
    <header
      className={`site-header mobile-only${showTitle ? "" : " site-header--no-title"}${isDetail ? " site-header--detail" : ""}`}
    >
      <div className="shell-header-row">
        <div className="shell-header-start">
          {isDetail ? (
            <span className="shell-header-back" aria-hidden="true">
              ←
            </span>
          ) : (
            <span className="shell-header-profile" aria-hidden="true">
              <SkeletonCircle size={34} className="shell-header-avatar" />
            </span>
          )}
        </div>
        {showTitle ? (
          <h1 className="shell-header-title">{title}</h1>
        ) : (
          <h1 className="visually-hidden">わせわせ</h1>
        )}
        {isDetail ? (
          <div className="shell-header-end" />
        ) : (
          <div className="shell-header-end" aria-hidden="true">
            <span className="shell-header-dm">
              <svg viewBox="0 0 24 24" width={22} height={22}>
                <path d={DM_ICON} />
              </svg>
            </span>
            <span className="shell-header-notify">
              <svg viewBox="0 0 24 24" width={22} height={22}>
                <path d={NOTIFY_ICON} />
              </svg>
            </span>
          </div>
        )}
      </div>
    </header>
  );
}

function BootBottomNav({ pathname }: { pathname: string }) {
  const active = matchMainTab(pathname);
  return (
    <nav className="bottom-nav" aria-hidden="true">
      {TAB_ROUTES.map((tab) => (
        <span
          key={tab.id}
          className={`nav-item${active === tab.id ? " is-active" : ""}`}
        >
          <svg viewBox="0 0 24 24" width={24} height={24}>
            <path d={tab.icon} />
          </svg>
          <span>{tab.label}</span>
        </span>
      ))}
    </nav>
  );
}

function BootSidebar({ pathname }: { pathname: string }) {
  const active = matchMainTab(pathname);
  return (
    <div className="sidebar-left-inner" aria-hidden="true">
      <span className="sidebar-brand">
        <span className="sidebar-brand__mark">わ</span>
        <span className="sidebar-brand__text">わせわせ</span>
      </span>
      <ul className="sidebar-nav">
        {TAB_ROUTES.map((tab) => (
          <li key={tab.id}>
            <span
              className={`sidebar-nav__item${active === tab.id ? " is-active" : ""}`}
            >
              <svg viewBox="0 0 24 24" width={24} height={24}>
                <path d={tab.icon} />
              </svg>
              <span className="sidebar-nav__label">{tab.label}</span>
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** Full-shell placeholder while `/me` is in flight. Not interactive. No PII. */
export function BootSkeleton({ pathname }: { pathname: string }) {
  const path = normalizeSpaPath(pathname);
  const kind = bootSkeletonKind(path);
  const showBottomNav = bootShowsBottomNav(path);
  const isHome = matchMainTab(path) === "home";
  const chrome = matchChromeMode(path);

  useEffect(() => {
    applyChromeModeClass(chrome, document.documentElement);
    applyChromeModeClass(chrome, document.body);
    document.body.classList.toggle("shell-hide-bottom-nav", !showBottomNav);
    document.documentElement.classList.toggle(
      "shell-hide-bottom-nav",
      !showBottomNav
    );
    return () => {
      document.body.classList.remove("shell-hide-bottom-nav");
      document.documentElement.classList.remove("shell-hide-bottom-nav");
    };
  }, [chrome, showBottomNav]);

  return (
    <div
      className="boot-skeleton"
      data-boot-kind={kind}
      aria-busy="true"
      aria-label="読み込み中"
    >
      <div className="app-shell" data-chrome-mode={chrome}>
        <aside className="sidebar-left">
          <BootSidebar pathname={path} />
        </aside>
        <div className="main-column">
          <BootHeader pathname={path} />
          <div
            className={`main-inner${isHome ? " timeline-home" : ""}`}
          >
            <BootSkeletonFeed kind={kind} />
          </div>
        </div>
        <aside className="sidebar-right" aria-hidden="true" />
      </div>
      {showBottomNav ? (
        <div className="shell-hide-on-desktop">
          <BootBottomNav pathname={path} />
        </div>
      ) : null}
    </div>
  );
}
