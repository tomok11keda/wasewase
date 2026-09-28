"""Native Feel Phase 3: forward-only detail push transition."""

from __future__ import annotations

from pathlib import Path

from django.test import SimpleTestCase

ROOT = Path(__file__).resolve().parents[1]


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


class DetailPushLogicTests(SimpleTestCase):
    def test_helper_requires_push_and_detail_chrome(self):
        src = _read("frontend/src/lib/detailTransition.ts")
        self.assertIn("export function shouldPlayDetailPush", src)
        self.assertIn('if (input.isSessionStart) return false', src)
        self.assertIn('if (input.navigationType !== "PUSH") return false', src)
        self.assertIn('matchChromeMode(input.pathname) === "detail"', src)
        self.assertIn("useNavigationType", src)
        self.assertIn("DETAIL_PUSH_CLASS = \"wase-detail-push\"", src)
        self.assertIn("DETAIL_PUSH_MS = 180", src)
        self.assertNotIn("POP", src.split("shouldPlayDetailPush")[1].split("export function use")[0])

    def test_pop_replace_and_boot_are_excluded(self):
        src = _read("frontend/src/lib/detailTransition.ts")
        self.assertIn("isSessionStart", src)
        self.assertIn('navigationType !== "PUSH"', src)
        helper = src.split("export function shouldPlayDetailPush")[1].split(
            "export function useDetailPushTransition"
        )[0]
        self.assertNotIn("navigationType === \"POP\"", helper)
        self.assertNotIn("REPLACE", helper)
        self.assertIn("isSessionStart: sessionStartRef.current", src)

    def test_app_shell_wires_transition_hook(self):
        src = _read("frontend/src/layouts/AppShellLayout.tsx")
        self.assertIn("useDetailPushTransition", src)
        self.assertIn("AppDetailHeader", src)
        self.assertIn("shouldHideBottomNav", src)

    def test_back_button_stays_history_pop(self):
        src = _read("frontend/src/components/AppDetailHeader.tsx")
        self.assertIn("navigate(-1)", src)
        self.assertIn("resolveDetailBack", src)
        self.assertNotIn("shouldPlayDetailPush", src)
        self.assertNotIn("wase-detail-push", src)


class DetailPushCssTests(SimpleTestCase):
    def test_forward_keyframes_are_short_and_transform_only(self):
        css = _read("frontend/src/styles/shell.css")
        self.assertIn("@keyframes wase-detail-push-in", css)
        self.assertIn("translate3d(16px, 0, 0)", css)
        self.assertIn("translate3d(0, 0, 0)", css)
        self.assertIn("opacity: 0.98", css)
        self.assertIn("180ms", css)
        self.assertIn("cubic-bezier(0.22, 1, 0.36, 1)", css)
        block = css.split("@keyframes wase-detail-push-in")[1].split("@media")[0]
        self.assertNotIn("margin-left", block)
        self.assertNotIn("left:", block)

    def test_animation_targets_header_and_detail_outlet_not_tabs(self):
        css = _read("frontend/src/styles/shell.css")
        self.assertIn("html.wase-detail-push .site-header--detail", css)
        self.assertIn("html.wase-detail-push .tab-keep-alive-outlet:not(.is-hidden)", css)
        phase = css.split("@keyframes wase-detail-push-in")[1]
        self.assertIn("animation: wase-detail-push-in 180ms", phase)
        self.assertNotIn("html.wase-detail-push .tab-keep-alive-pane", phase)
        self.assertNotIn("html.wase-detail-push .bottom-nav", css)

    def test_reduced_motion_disables_detail_push(self):
        css = _read("frontend/src/styles/shell.css")
        self.assertIn("@media (prefers-reduced-motion: reduce)", css)
        reduce_block = css.split("@keyframes wase-detail-push-in")[1]
        self.assertIn("prefers-reduced-motion: reduce", reduce_block)
        self.assertIn("animation: none", reduce_block)


class DetailPushRegressionTests(SimpleTestCase):
    def test_phase2_preview_state_and_focus_survive(self):
        post = _read("frontend/src/pages/TimelinePostDetailPage.tsx")
        anchor = _read("frontend/src/features/timeline/postAnchor.ts")
        self.assertIn("readInitialTimelinePost", post)
        self.assertIn("initialPost", anchor)
        self.assertIn("fromWaseWase: true", anchor)
        self.assertIn("focusComposer", anchor)
        self.assertIn("navState?.fromWaseWase", post)
        self.assertIn("navState?.focusComposer", post)

    def test_timeline_community_flea_remain_detail_chrome(self):
        chrome = _read("frontend/src/lib/chrome.ts")
        self.assertIn('title: "投稿"', chrome)
        self.assertIn('title: "コミュニティ"', chrome)
        self.assertIn('title: "フリマ"', chrome)
        self.assertIn("isConversationPath", chrome)
        tabs = _read("frontend/src/lib/tabs.ts")
        self.assertIn("flea\\/chats", tabs)
        self.assertIn("courses\\/\\d+\\/talk", tabs)

    def test_keep_alive_and_native_edge_swipe_unchanged(self):
        keep = _read("frontend/src/layouts/TabKeepAliveLayout.tsx")
        native = _read("ios/App/App/AppDelegate.swift")
        home = _read("frontend/src/pages/HomePage.tsx")
        self.assertIn("export function TabKeepAliveLayout", keep)
        self.assertIn("webView.allowsBackForwardNavigationGestures = true", native)
        self.assertIn('restoreScrollPosition("/")', home)

    def test_no_animation_library_added(self):
        pkg = _read("frontend/package.json")
        for name in ("framer-motion", "react-spring", "gsap", "motion"):
            self.assertNotIn(name, pkg)

    def test_transition_css_not_in_timeline_wip(self):
        timeline = _read("frontend/src/styles/timeline.css")
        self.assertNotIn("wase-detail-push-in", timeline)
        self.assertNotIn("wase-detail-push", timeline)
