"""Detail push enter + header-back exit. Native edge-swipe POP is not animated."""

from __future__ import annotations

from pathlib import Path

from django.test import SimpleTestCase

ROOT = Path(__file__).resolve().parents[1]


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def _transition_src() -> str:
    return _read("frontend/src/lib/detailTransition.ts")


def _shell_css() -> str:
    return _read("frontend/src/styles/shell.css")


def _push_helper() -> str:
    return _transition_src().split("export function shouldPlayDetailPush")[1].split(
        "export function shouldResetDetailWindowScroll"
    )[0]


def _hook_body() -> str:
    return _transition_src().split("export function useDetailPushTransition")[1]


def _header_back_fn() -> str:
    return _transition_src().split("export function requestDetailHeaderBack")[1].split(
        "export function useDetailPushTransition"
    )[0]


def _execute_back_fn() -> str:
    return _transition_src().split("export function executeDetailBack")[1].split(
        "function queryVisibleDetailOutlet"
    )[0]


class DetailPushLogicTests(SimpleTestCase):
    def test_helper_requires_push_and_detail_chrome(self):
        src = _transition_src()
        helper = _push_helper()
        self.assertIn("export function shouldPlayDetailPush", src)
        self.assertIn('if (input.isSessionStart) return false', src)
        self.assertIn('if (input.navigationType !== "PUSH") return false', src)
        self.assertIn('matchChromeMode(input.pathname) === "detail"', src)
        self.assertIn("useNavigationType", src)
        self.assertIn("DETAIL_PUSH_CLASS = \"wase-detail-push\"", src)
        self.assertIn("DETAIL_PUSH_MS = 500", src)
        self.assertNotIn("navigationType === \"POP\"", helper)

    def test_pop_replace_and_boot_are_excluded(self):
        src = _transition_src()
        self.assertIn("isSessionStart", src)
        self.assertIn('navigationType !== "PUSH"', src)
        self.assertIn("isSessionStart: sessionStartRef.current", src)
        self.assertIn("shouldResetDetailWindowScroll", src)
        self.assertIn("return shouldPlayDetailPush(input)", src)

    def test_forward_resets_window_scroll_after_saving_list_position(self):
        src = _transition_src()
        self.assertIn("window.scrollTo(0, 0)", src)
        self.assertIn("saveScrollPosition(fromKey)", src)
        self.assertIn("mainTabScrollKey", src)
        no_play = src.split("if (!play)")[1].split("const fromKey")[0]
        self.assertNotIn("window.scrollTo(0, 0)", no_play)
        after_play = src.split("if (fromKey) saveScrollPosition(fromKey)")[1]
        self.assertIn("window.scrollTo(0, 0)", after_play)

    def test_pop_restores_list_scroll_and_does_not_reset_to_top(self):
        src = _transition_src()
        self.assertIn('if (navigationType === "POP")', src)
        self.assertIn("restoreScrollPosition(key, true)", src)
        pop_block = src.split('if (navigationType === "POP")')[1].split(
            "const fromKey"
        )[0]
        self.assertNotIn("window.scrollTo(0, 0)", pop_block)
        self.assertNotIn("DETAIL_PUSH_CLASS)", pop_block)
        self.assertNotIn("DETAIL_POP_CLASS)", pop_block)

    def test_app_shell_wires_transition_hook(self):
        src = _read("frontend/src/layouts/AppShellLayout.tsx")
        self.assertIn("useDetailPushTransition", src)
        self.assertIn("AppDetailHeader", src)
        self.assertIn("shouldHideBottomNav", src)

    def test_back_button_uses_shared_exit_then_existing_semantics(self):
        src = _read("frontend/src/components/AppDetailHeader.tsx")
        self.assertIn("requestDetailHeaderBack", src)
        self.assertIn("shell-header-back", src)
        self.assertNotIn("shouldPlayDetailPush", src)
        self.assertNotIn("wase-detail-push", src)
        self.assertNotIn("scrollTo(0, 0)", src)
        execute = _execute_back_fn()
        self.assertIn("resolveDetailBack", execute)
        self.assertIn("navigate(-1)", execute)
        self.assertIn("dest.replace ? { replace: true }", execute)


class DetailPushCssTests(SimpleTestCase):
    def test_forward_keyframes_are_short_and_transform_only(self):
        css = _shell_css()
        enter = css.split("@keyframes wase-detail-push-in")[1].split(
            "@keyframes wase-detail-push-out"
        )[0]
        self.assertIn("@keyframes wase-detail-push-in", css)
        self.assertIn("translate3d(120px, 0, 0)", enter)
        self.assertIn("translate3d(0, 0, 0)", enter)
        self.assertIn("opacity: 0.98", enter)
        self.assertNotIn("100vw", enter)
        self.assertNotIn("translate3d(16px", enter)
        self.assertIn("500ms", css.split("html.wase-detail-push .tab-keep-alive-outlet")[1].split("}")[0])
        self.assertIn(
            "cubic-bezier(0.33, 0, 0.20, 1)",
            css.split("html.wase-detail-push .tab-keep-alive-outlet")[1].split("}")[0],
        )
        self.assertNotIn("margin-left", enter)
        self.assertNotIn("left:", enter)
        self.assertNotIn(
            "cubic-bezier(0.22, 1, 0.36, 1)",
            css.split("@keyframes wase-detail-push-in")[1].split(".spa-placeholder")[0],
        )

    def test_animation_targets_outlet_not_fixed_header_or_tabs(self):
        css = _shell_css()
        phase = css.split("@keyframes wase-detail-push-in")[1]
        self.assertIn("html.wase-detail-push .tab-keep-alive-outlet:not(.is-hidden)", phase)
        self.assertIn("html.wase-detail-pop .tab-keep-alive-outlet:not(.is-hidden)", phase)
        self.assertIn("animation: wase-detail-push-in 500ms", phase)
        self.assertIn("animation: wase-detail-push-out 500ms", phase)
        self.assertNotIn("html.wase-detail-push .site-header--detail", phase)
        self.assertNotIn("html.wase-detail-pop .site-header--detail", phase)
        self.assertNotIn("html.wase-detail-push .tab-keep-alive-pane", phase)
        self.assertNotIn("html.wase-detail-pop .tab-keep-alive-pane", phase)
        self.assertNotIn("html.wase-detail-push .bottom-nav", css)
        self.assertNotIn("html.wase-detail-pop .bottom-nav", css)

    def test_reduced_motion_disables_detail_push_and_pop(self):
        css = _shell_css()
        reduce_block = css.split("@keyframes wase-detail-push-in")[1]
        self.assertIn("prefers-reduced-motion: reduce", reduce_block)
        self.assertIn("animation: none", reduce_block)
        self.assertIn(
            "html.wase-detail-pop .tab-keep-alive-outlet:not(.is-hidden)",
            reduce_block.split("prefers-reduced-motion: reduce")[1],
        )


class DetailHeaderBackExitTests(SimpleTestCase):
    def test_header_back_starts_exit_animation_not_pop_navigation_type(self):
        back = _header_back_fn()
        hook = _hook_body()
        self.assertIn("setHtmlPopClass(true)", back)
        self.assertIn("DETAIL_EXIT_ANIMATION", back)
        self.assertNotIn("navigationType", back)
        self.assertNotIn("setHtmlPopClass(true)", hook)
        self.assertIn("setHtmlPopClass(false)", hook)
        self.assertEqual(
            _read("frontend/src/layouts/AppShellLayout.tsx").count(
                "requestDetailHeaderBack"
            ),
            0,
        )
        self.assertIn(
            "requestDetailHeaderBack",
            _read("frontend/src/components/AppDetailHeader.tsx"),
        )

    def test_exit_waits_for_animationend_then_runs_existing_back_once(self):
        src = _transition_src()
        back = _header_back_fn()
        self.assertIn("animationend", src)
        self.assertIn("waitForNamedAnimation", back)
        self.assertIn("executeDetailBack", back)
        self.assertIn("DETAIL_PUSH_MS + 40", src)
        self.assertEqual(back.count("executeDetailBack"), 2)
        self.assertNotIn("navigate(-1)", back)

    def test_double_tap_ignored_while_exit_in_flight(self):
        back = _header_back_fn()
        src = _transition_src()
        self.assertIn("if (detailBackInFlight) return", back)
        self.assertIn("detailBackInFlight = true", back)
        self.assertIn("if (navigated) return", back)
        self.assertIn("releaseDetailBackLock", src)

    def test_native_or_browser_pop_does_not_play_react_exit(self):
        helper = _push_helper()
        hook = _hook_body()
        native = _read("ios/App/App/AppDelegate.swift")
        self.assertNotIn("DETAIL_POP_CLASS", helper)
        self.assertNotIn("requestDetailHeaderBack", hook)
        self.assertIn("setHtmlPopClass(false)", hook)
        self.assertNotIn("setHtmlPopClass(true)", hook)
        self.assertIn("webView.allowsBackForwardNavigationGestures = true", native)

    def test_replace_boot_and_conversation_stay_unanimate(self):
        src = _transition_src()
        helper = _push_helper()
        self.assertIn('navigationType !== "PUSH"', helper)
        self.assertIn("isSessionStart", helper)
        self.assertIn('matchChromeMode(input.pathname) === "detail"', helper)
        back = _header_back_fn()
        self.assertIn('matchChromeMode(pathname) !== "detail"', back)
        self.assertNotIn("conversation", helper)

    def test_reduced_motion_back_navigates_immediately(self):
        back = _header_back_fn()
        self.assertIn("if (prefersReducedMotion())", back)
        go_block = back.split("if (prefersReducedMotion())")[1].split(
            "const root = document.documentElement"
        )[0]
        self.assertIn("go()", go_block)
        self.assertNotIn("waitForNamedAnimation", go_block)
        self.assertNotIn("DETAIL_POP_CLASS", go_block)

    def test_exit_distance_clears_viewport_without_changing_forward(self):
        css = _shell_css()
        out = css.split("@keyframes wase-detail-push-out")[1].split(
            "html.wase-detail-push,"
        )[0]
        self.assertIn("translate3d(100vw, 0, 0)", out)
        self.assertIn("translate3d(0, 0, 0)", out)
        self.assertNotIn("translate3d(120px", out)
        self.assertIn("opacity: 0.98", out)
        rule = [
            line
            for line in css.splitlines()
            if "wase-detail-push-out" in line and "animation:" in line
        ]
        self.assertTrue(rule)
        self.assertIn("500ms", rule[0])
        self.assertIn("cubic-bezier(0.33, 0, 0.20, 1)", rule[0])
        enter = css.split("@keyframes wase-detail-push-in")[1].split(
            "@keyframes wase-detail-push-out"
        )[0]
        self.assertIn("translate3d(120px, 0, 0)", enter)
        self.assertNotIn("100vw", enter)

    def test_animationend_requires_outlet_target_and_exit_name(self):
        src = _transition_src()
        wait = src.split("function waitForNamedAnimation")[1].split(
            "function releaseDetailBackLock"
        )[0]
        self.assertIn("event.target !== el", wait)
        self.assertIn("event.animationName !== animationName", wait)
        self.assertIn("DETAIL_EXIT_ANIMATION", _header_back_fn())
        self.assertIn("DETAIL_PUSH_MS + 40", wait)

    def test_keep_alive_underlay_only_during_header_back_exit(self):
        keep = _read("frontend/src/layouts/TabKeepAliveLayout.tsx")
        css = _shell_css()
        self.assertIn("is-back-underlay", keep)
        self.assertIn("subscribeDetailPopVisual", keep)
        self.assertIn("useActiveMainTab", keep)
        self.assertIn("is-collapsed", keep)
        self.assertIn(".tab-keep-alive-stack.is-collapsed", css)
        self.assertIn("display: none", css.split(".tab-keep-alive-stack.is-collapsed")[1].split("}")[0])
        self.assertIn(".tab-keep-alive-stack.is-back-underlay", css)
        self.assertIn("pointer-events: none", css.split(".tab-keep-alive-stack.is-back-underlay")[1].split("}")[0])
        self.assertIn("readScrollPosition", keep)


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
        self.assertIn("export function readScrollPosition", api)
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
        self.assertNotIn("wase-detail-pop", timeline)
        self.assertNotIn("wase-detail-push-out", timeline)
