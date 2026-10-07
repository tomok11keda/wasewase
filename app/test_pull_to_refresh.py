"""SPA Pull-to-Refresh: shared hook, gesture policy, page wiring, regressions."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from django.test import SimpleTestCase

ROOT = Path(__file__).resolve().parents[1]


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


PTR_PAGES = [
    "frontend/src/pages/HomePage.tsx",
    "frontend/src/pages/CommunitiesPage.tsx",
    "frontend/src/pages/FleaPage.tsx",
    "frontend/src/pages/NotificationsPage.tsx",
    "frontend/src/pages/DmInboxPage.tsx",
]

NO_PTR_PAGES = [
    "frontend/src/pages/SearchPage.tsx",
    "frontend/src/pages/TimetablePage.tsx",
    "frontend/src/pages/ProfilePage.tsx",
    "frontend/src/pages/TimelinePostDetailPage.tsx",
    "frontend/src/pages/CommunityThreadPage.tsx",
    "frontend/src/pages/DmRoomPage.tsx",
    "frontend/src/pages/GroupRoomPage.tsx",
    "frontend/src/pages/TradeChatPage.tsx",
    "frontend/src/pages/CourseTalkPage.tsx",
    "frontend/src/pages/ExhibitPage.tsx",
    "frontend/src/pages/GroupCreatePage.tsx",
    "frontend/src/pages/ProductDetailPage.tsx",
]


def _const(src: str, name: str) -> int:
    match = re.search(rf"export const {name} = (\d+)", src)
    assert match, name
    return int(match.group(1))


class PullToRefreshPolicyTests(SimpleTestCase):
    def test_classic_ux_constants(self):
        policy = _read("frontend/src/lib/pullToRefreshPolicy.ts")
        hook = _read("frontend/src/lib/usePullToRefresh.tsx")
        self.assertEqual(_const(policy, "PTR_THRESHOLD_PX"), 72)
        self.assertEqual(_const(policy, "PTR_MAX_PULL_PX"), 120)
        self.assertEqual(_const(policy, "PTR_ARM_PX"), 8)
        self.assertEqual(_const(policy, "PTR_EDGE_GUARD_PX"), 24)
        self.assertEqual(_const(policy, "PTR_TOP_MAX_SCROLL_Y"), 1)
        self.assertEqual(_const(policy, "PTR_MOBILE_MAX_WIDTH_PX"), 1023)
        self.assertEqual(_const(policy, "PTR_ERROR_MS"), 2000)
        self.assertIn("PTR_MOBILE_MEDIA", hook)
        self.assertIn("canStartPtrGesture", hook)
        self.assertIn("clampPtrPull", hook)
        self.assertIn("isPtrArmed", hook)
        self.assertIn("shouldActivatePtrPull", hook)
        self.assertIn("shouldCancelPtrBeforeActivate", hook)
        self.assertIn("shouldPtrPreventDefault", hook)

    def test_executable_policy_script_matches_source_constants(self):
        policy = _read("frontend/src/lib/pullToRefreshPolicy.ts")
        script = _read("frontend/scripts/verify_ptr_policy.mjs")
        for name in (
            "PTR_THRESHOLD_PX",
            "PTR_MAX_PULL_PX",
            "PTR_ARM_PX",
            "PTR_EDGE_GUARD_PX",
            "PTR_TOP_MAX_SCROLL_Y",
            "PTR_MOBILE_MAX_WIDTH_PX",
            "PTR_ERROR_MS",
        ):
            self.assertEqual(_const(policy, name), _const(script, name), name)

    def test_policy_script_passes(self):
        result = subprocess.run(
            ["node", "frontend/scripts/verify_ptr_policy.mjs"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn("PTR policy tests ok", result.stdout)


class PullToRefreshGestureHookTests(SimpleTestCase):
    def test_top_and_finger_and_edge_guards(self):
        policy = _read("frontend/src/lib/pullToRefreshPolicy.ts")
        hook = _read("frontend/src/lib/usePullToRefresh.tsx")
        self.assertIn("scrollY <= PTR_TOP_MAX_SCROLL_Y", policy)
        self.assertIn("touchCount !== 1", policy)
        self.assertIn("clientX <= PTR_EDGE_GUARD_PX", policy)
        self.assertIn("Math.abs(dx) > Math.abs(dy)", policy)
        self.assertIn("event.touches.length !== 1", hook)
        self.assertIn("currentScrollY()", hook)
        self.assertIn("touch.clientX", hook)

    def test_prevent_default_only_after_arm(self):
        policy = _read("frontend/src/lib/pullToRefreshPolicy.ts")
        hook = _read("frontend/src/lib/usePullToRefresh.tsx")
        self.assertIn("dy > PTR_ARM_PX", policy)
        self.assertIn("{ passive: false }", hook)
        self.assertIn("{ passive: true }", hook)
        self.assertIn("event.preventDefault()", hook)
        self.assertIn("shouldPtrPreventDefault(session.activated, dy)", hook)
        self.assertIn("shouldActivatePtrPull(dx, dy)", hook)

    def test_release_threshold_and_max_pull_and_single_refresh(self):
        policy = _read("frontend/src/lib/pullToRefreshPolicy.ts")
        hook = _read("frontend/src/lib/usePullToRefresh.tsx")
        self.assertIn("pullPx >= PTR_THRESHOLD_PX", policy)
        self.assertIn("dy > PTR_MAX_PULL_PX ? PTR_MAX_PULL_PX : dy", policy)
        self.assertIn("isPtrArmed(pullRef.current)", hook)
        self.assertIn('statusRef.current === "refreshing"', hook)
        self.assertIn("onRefreshRef.current()", hook)
        self.assertIn("PTR_ERROR_MS", hook)
        self.assertIn("更新中...", hook)
        self.assertIn("更新に失敗しました", hook)

    def test_desktop_disables_listeners(self):
        hook = _read("frontend/src/lib/usePullToRefresh.tsx")
        self.assertIn("window.matchMedia(PTR_MOBILE_MEDIA)", hook)
        self.assertIn("const active = enabled && isMobile", hook)
        self.assertIn('addEventListener("change", sync)', hook)
        css = _read("frontend/src/styles/pull-to-refresh.css")
        self.assertIn("@media (min-width: 1024px)", css)

    def test_cleanup_on_disable_and_unmount(self):
        hook = _read("frontend/src/lib/usePullToRefresh.tsx")
        self.assertIn("cancelled = true", hook)
        self.assertIn('removeEventListener("touchstart"', hook)
        self.assertIn('removeEventListener("touchmove"', hook)
        self.assertIn('removeEventListener("touchend"', hook)
        self.assertIn('removeEventListener("touchcancel"', hook)
        self.assertIn("clearTimeout", hook)

    def test_indicator_portals_outside_keep_alive(self):
        hook = _read("frontend/src/lib/usePullToRefresh.tsx")
        main = _read("frontend/src/main.tsx")
        css = _read("frontend/src/styles/pull-to-refresh.css")
        self.assertIn("createPortal", hook)
        self.assertIn("document.body", hook)
        self.assertIn("data-ptr", hook)
        self.assertIn("var(--wase-chrome-offset", css)
        self.assertIn("z-index: 180", css)
        self.assertIn("position: fixed", css)
        self.assertIn("pull-to-refresh.css", main)
        self.assertNotIn("tab-keep-alive", hook)


class PullToRefreshPageWiringTests(SimpleTestCase):
    def test_tier1_pages_share_the_hook(self):
        for rel in PTR_PAGES:
            src = _read(rel)
            self.assertIn('from "../lib/usePullToRefresh"', src, rel)
            self.assertIn("<PullToRefresh", src, rel)
            self.assertIn("onRefresh=", src, rel)
            self.assertNotIn("get_latest_posts", src, rel)
            self.assertNotIn("/board/latest/", src, rel)
            self.assertNotIn("window.location.reload()", src, rel)

    def test_out_of_scope_pages_do_not_import_ptr(self):
        for rel in NO_PTR_PAGES:
            src = _read(rel)
            self.assertNotIn("usePullToRefresh", src, rel)
            self.assertNotIn("PullToRefresh", src, rel)

    def test_timeline_soft_refresh_keeps_feed_and_posts(self):
        home = _read("frontend/src/pages/HomePage.tsx")
        self.assertIn(
            "enabled={onVisibleHome && !composeOpen && !browsePreview}", home
        )
        self.assertIn("await loadInitial(\"soft\")", home)
        self.assertIn("refresh_failed", home)
        self.assertIn("fetchTimeline({", home)
        self.assertIn("sort,", home)
        self.assertIn("faculty: faculty || undefined", home)
        self.assertIn("q: qParam || undefined", home)
        self.assertIn('if (mode === "soft") return false', home)
        self.assertIn('if (mode !== "soft") setLoading(false)', home)
        self.assertIn("setPosts(data.posts)", home)
        self.assertIn("hasDataRef.current = true", home)
        self.assertIn('activeTab === "home"', home)

    def test_community_keeps_hub_and_disables_while_composing(self):
        page = _read("frontend/src/pages/CommunitiesPage.tsx")
        self.assertIn(
            "enabled={onCommunityList && !composeOpen && !browsePreview}",
            page,
        )
        self.assertIn("loadCourses(\"soft\")", page)
        self.assertIn("load(\"soft\")", page)
        self.assertIn("refresh_failed", page)
        self.assertIn("fetchCommunityThreads({", page)
        self.assertIn("tag: tag || undefined", page)
        self.assertIn("q: qParam || undefined", page)
        self.assertIn("sort,", page)
        self.assertIn("fetchCourseDiscover()", page)
        self.assertIn('if (mode === "soft") return false', page)
        self.assertIn("is-composing", page)

    def test_flea_keeps_filters_and_listings(self):
        page = _read("frontend/src/pages/FleaPage.tsx")
        self.assertIn("enabled={showExhibitFab && !browsePreview}", page)
        self.assertIn('load("soft")', page)
        self.assertIn("refresh_failed", page)
        self.assertIn("feed: feed || undefined", page)
        self.assertIn("q: qParam || undefined", page)
        self.assertIn("faculty: faculty || undefined", page)
        self.assertIn("campus: campus || undefined", page)
        self.assertIn("order: order || undefined", page)
        self.assertIn("setProducts(data.products)", page)
        self.assertIn('if (mode !== "soft") setLoading(false)', page)
        self.assertIn('activeTab === "flea"', page)

    def test_notifications_ptr_does_not_mark_read(self):
        page = _read("frontend/src/pages/NotificationsPage.tsx")
        api = _read("frontend/src/features/notifications/api.ts")
        self.assertIn('fetchNotifications(mode === "initial")', page)
        self.assertIn('load("soft")', page)
        self.assertIn("refresh_failed", page)
        self.assertIn('if (mode === "initial") setLoading(true)', page)
        self.assertIn('if (mode === "soft") return false', page)
        self.assertIn("?mark_read=0", api)
        self.assertNotIn("fetchNotifications(true)", page)

    def test_dm_inbox_soft_refresh_not_individual_chats(self):
        inbox = _read("frontend/src/pages/DmInboxPage.tsx")
        app = _read("frontend/src/App.tsx")
        room = _read("frontend/src/pages/DmRoomPage.tsx")
        group = _read("frontend/src/pages/GroupRoomPage.tsx")
        trade = _read("frontend/src/pages/TradeChatPage.tsx")
        course = _read("frontend/src/pages/CourseTalkPage.tsx")
        self.assertIn('void load("initial", ac.signal)', inbox)
        self.assertIn('load("soft")', inbox)
        self.assertIn("refresh_failed", inbox)
        self.assertIn('if (mode === "initial")', inbox)
        self.assertIn("setLoading(true)", inbox)
        self.assertIn(
            "if (mode === \"initial\" && !signal?.aborted) setLoading(false)",
            inbox,
        )
        self.assertIn("setItems(data.conversations || [])", inbox)
        self.assertIn('path="dm" element={<DmInboxPage />}', app)
        self.assertIn('path="dm/:roomPk" element={<DmRoomPage />}', app)
        for src, label in (
            (room, "dm-room"),
            (group, "group"),
            (trade, "trade"),
            (course, "course"),
        ):
            self.assertNotIn("PullToRefresh", src, label)
            self.assertIn("useChatPoll", src, label)

    def test_keep_alive_only_active_tab_enables_ptr(self):
        home = _read("frontend/src/pages/HomePage.tsx")
        community = _read("frontend/src/pages/CommunitiesPage.tsx")
        flea = _read("frontend/src/pages/FleaPage.tsx")
        hook = _read("frontend/src/lib/usePullToRefresh.tsx")
        self.assertIn("useActiveMainTab", home)
        self.assertIn("onVisibleHome", home)
        self.assertIn("onCommunityList", community)
        self.assertIn("showExhibitFab", flea)
        self.assertIn("const active = enabled && isMobile", hook)
        self.assertIn('addEventListener("touchstart"', hook)


class PullToRefreshRegressionTests(SimpleTestCase):
    def test_phase1_keep_alive_overflow_hidden_remains(self):
        css = _read("frontend/src/styles/shell.css")
        stack = css.split(".tab-keep-alive-stack")[1].split("}")[0]
        self.assertIn("overflow: hidden", stack)
        inactive = css.split(
            ".tab-keep-alive-pane:not(.is-active):not(.is-leaving)"
        )[1].split("}")[0]
        self.assertIn("overflow: hidden", inactive)

    def test_phase2_mobile_shell_height_remains(self):
        tokens = _read("frontend/src/styles/tokens.css")
        shell = _read("frontend/src/styles/shell.css")
        self.assertIn(
            "min-height: calc(100dvh - var(--nav-h) - env(safe-area-inset-bottom, 0px))",
            tokens,
        )
        mobile = shell.split("@media (max-width: 1023px)")[1]
        self.assertIn(
            "min-height: calc(100dvh - var(--nav-h) - env(safe-area-inset-bottom, 0px))",
            mobile,
        )

    def test_fab_contracts_remain(self):
        home = _read("frontend/src/pages/HomePage.tsx")
        community = _read("frontend/src/pages/CommunitiesPage.tsx")
        flea = _read("frontend/src/pages/FleaPage.tsx")
        self.assertIn("createPortal", home)
        self.assertIn("document.body", home)
        self.assertIn("home-compose-fab shell-hide-on-desktop is-visible", home)
        self.assertIn("community-compose-fab", community)
        self.assertIn("flea-compose-fab", flea)
        self.assertNotIn("composeCueInView", home)

    def test_timetable_viewport_css_untouched_by_ptr(self):
        css = _read("frontend/src/styles/timetable.css")
        self.assertIn("--tt-header-fallback", css)
        self.assertIn("100dvh", css)
        self.assertNotIn("ptr-indicator", css)

    def test_detail_transition_untouched_by_ptr(self):
        src = _read("frontend/src/lib/detailTransition.ts")
        self.assertIn("getDetailPopVisualSnapshot", src)
        self.assertNotIn("PullToRefresh", src)
        self.assertNotIn("ptr-indicator", src)

    def test_native_bounce_and_swipe_back_untouched(self):
        native = _read("ios/App/App/AppDelegate.swift")
        self.assertIn("webView.scrollView.bounces = false", native)
        self.assertIn("alwaysBounceVertical = false", native)
        self.assertIn("alwaysBounceHorizontal = false", native)
        self.assertIn("contentInsetAdjustmentBehavior = .never", native)
        self.assertIn("allowsBackForwardNavigationGestures = true", native)
        self.assertNotIn("UIRefreshControl", native)

    def test_spa_does_not_call_classic_latest_html(self):
        frontend = ROOT / "frontend" / "src"
        for path in list(frontend.rglob("*.ts")) + list(frontend.rglob("*.tsx")):
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("get_latest_posts", text, str(path))
            self.assertNotIn("/board/latest/", text, str(path))
