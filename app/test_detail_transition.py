"""Native Feel Phase 3 / 3.1: forward-only detail push + window-scroll reset."""

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
        self.assertIn("DETAIL_PUSH_MS = 280", src)
        helper = src.split("export function shouldPlayDetailPush")[1].split(
            "export function shouldResetDetailWindowScroll"
        )[0]
        self.assertNotIn("navigationType === \"POP\"", helper)

    def test_pop_replace_and_boot_are_excluded(self):
        src = _read("frontend/src/lib/detailTransition.ts")
        self.assertIn("isSessionStart", src)
        self.assertIn('navigationType !== "PUSH"', src)
        self.assertIn("isSessionStart: sessionStartRef.current", src)
        self.assertIn("shouldResetDetailWindowScroll", src)
        self.assertIn("return shouldPlayDetailPush(input)", src)

    def test_forward_resets_window_scroll_after_saving_list_position(self):
        src = _read("frontend/src/lib/detailTransition.ts")
        self.assertIn("window.scrollTo(0, 0)", src)
        self.assertIn("saveScrollPosition(fromKey)", src)
        self.assertIn("mainTabScrollKey", src)
        no_play = src.split("if (!play)")[1].split("const fromKey")[0]
        self.assertNotIn("window.scrollTo(0, 0)", no_play)
        after_play = src.split("if (fromKey) saveScrollPosition(fromKey)")[1]
        self.assertIn("window.scrollTo(0, 0)", after_play)

    def test_pop_restores_list_scroll_and_does_not_reset_to_top(self):
        src = _read("frontend/src/lib/detailTransition.ts")
        self.assertIn('if (navigationType === "POP")', src)
        self.assertIn("restoreScrollPosition(key, true)", src)
        pop_block = src.split('if (navigationType === "POP")')[1].split(
            "const fromKey"
        )[0]
        self.assertNotIn("window.scrollTo(0, 0)", pop_block)
        self.assertNotIn("DETAIL_PUSH_CLASS)", pop_block)

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
        self.assertNotIn("scrollTo(0, 0)", src)


class DetailPushCssTests(SimpleTestCase):
    def test_forward_keyframes_are_short_and_transform_only(self):
        css = _read("frontend/src/styles/shell.css")
        self.assertIn("@keyframes wase-detail-push-in", css)
        self.assertIn("translate3d(40px, 0, 0)", css)
        self.assertIn("translate3d(0, 0, 0)", css)
        self.assertIn("opacity: 0.98", css)
        self.assertIn("280ms", css)
        self.assertIn("cubic-bezier(0.22, 1, 0.36, 1)", css)
        block = css.split("@keyframes wase-detail-push-in")[1].split("@media")[0]
        self.assertNotIn("margin-left", block)
        self.assertNotIn("left:", block)
        self.assertNotIn("translate3d(16px", css.split("@keyframes wase-detail-push-in")[1])

    def test_animation_targets_outlet_not_fixed_header_or_tabs(self):
        css = _read("frontend/src/styles/shell.css")
        phase = css.split("@keyframes wase-detail-push-in")[1]
        self.assertIn("html.wase-detail-push .tab-keep-alive-outlet:not(.is-hidden)", phase)
        self.assertIn("animation: wase-detail-push-in 280ms", phase)
        self.assertNotIn("html.wase-detail-push .site-header--detail", phase)
        self.assertNotIn("html.wase-detail-push .tab-keep-alive-pane", phase)
        self.assertNotIn("html.wase-detail-push .bottom-nav", css)

    def test_reduced_motion_disables_detail_push(self):
        css = _read("frontend/src/styles/shell.css")
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

    def test_header_offset_tokens_remain_source_of_truth(self):
        css = _read("static/css/capacitor_native.css")
        self.assertIn("padding-top: var(--wase-chrome-offset, var(--wase-header-h))", css)
        self.assertIn("--wase-chrome-offset: var(--wase-header-h)", css)
        header = _read("frontend/src/components/AppDetailHeader.tsx")
        self.assertIn("site-header--detail", header)

    def test_timeline_save_restore_not_cleared(self):
        card = _read("frontend/src/features/timeline/TimelinePostCard.tsx")
        home = _read("frontend/src/pages/HomePage.tsx")
        api = _read("frontend/src/features/profile/api.ts")
        self.assertIn('saveScrollPosition("/")', card)
        self.assertIn('restoreScrollPosition("/")', home)
        self.assertIn("export function saveScrollPosition", api)
        self.assertIn("restoreScrollPosition(pathKey: string, sync = false)", api)

    def test_timeline_community_flea_remain_detail_chrome(self):
        chrome = _read("frontend/src/lib/chrome.ts")
        self.assertIn('title: "投稿"', chrome)
        self.assertIn('title: "コミュニティ"', chrome)
        self.assertIn('title: "フリマ"', chrome)
        self.assertIn("isConversationPath", chrome)

    def test_keep_alive_and_native_edge_swipe_unchanged(self):
        keep = _read("frontend/src/layouts/TabKeepAliveLayout.tsx")
        native = _read("ios/App/App/AppDelegate.swift")
        self.assertIn("export function TabKeepAliveLayout", keep)
        self.assertIn("webView.allowsBackForwardNavigationGestures = true", native)

    def test_no_animation_library_added(self):
        pkg = _read("frontend/package.json")
        for name in ("framer-motion", "react-spring", "gsap"):
            self.assertNotIn(name, pkg)

    def test_transition_css_not_in_timeline_wip(self):
        timeline = _read("frontend/src/styles/timeline.css")
        self.assertNotIn("wase-detail-push-in", timeline)
        self.assertNotIn("wase-detail-push", timeline)
