"""Native Feel Phase 1: one shell chrome, no dual headers, shared offset tokens."""

from __future__ import annotations

from pathlib import Path

from django.test import SimpleTestCase

ROOT = Path(__file__).resolve().parents[1]


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


class ChromeModeSourceTests(SimpleTestCase):
    def test_chrome_helper_defines_three_modes(self):
        src = _read("frontend/src/lib/chrome.ts")
        self.assertIn('export type ChromeMode = "main" | "detail" | "conversation"', src)
        self.assertIn("export function matchChromeMode", src)
        self.assertIn("export function matchDetailChrome", src)
        self.assertIn("export function resolveDetailBack", src)
        self.assertIn('kind: "from-wasewase-or-fallback"', src)
        self.assertIn('title: "投稿"', src)
        self.assertIn('title: "コミュニティ"', src)
        self.assertIn('title: "フリマ"', src)
        self.assertIn("isConversationPath", src)
        self.assertIn("matchMainTab", src)

    def test_app_shell_switches_chrome_from_route(self):
        src = _read("frontend/src/layouts/AppShellLayout.tsx")
        self.assertIn("matchChromeMode", src)
        self.assertIn("AppDetailHeader", src)
        self.assertIn('chromeMode === "main"', src)
        self.assertIn('chromeMode === "detail"', src)
        self.assertIn("MobileShellHeader", src)
        self.assertIn("shouldHideBottomNav", src)
        self.assertIn("data-chrome-mode={chromeMode}", src)
        self.assertIn("hideShellTitle", src)

    def test_main_tabs_keep_mobile_shell_header(self):
        tabs = _read("frontend/src/lib/tabs.ts")
        self.assertIn('path: "/"', tabs)
        self.assertIn('path: "/communities"', tabs)
        self.assertIn('path: "/search"', tabs)
        self.assertIn('path: "/flea"', tabs)
        self.assertIn('path: "/timetable"', tabs)
        shell = _read("frontend/src/layouts/AppShellLayout.tsx")
        self.assertIn("MobileShellHeader", shell)
        self.assertIn("onOpenMenu", shell)

    def test_conversation_paths_are_not_detail_chrome(self):
        chrome = _read("frontend/src/lib/chrome.ts")
        tabs = _read("frontend/src/lib/tabs.ts")
        self.assertIn("if (isConversationPath(pathname)) return \"conversation\"", chrome)
        self.assertIn("flea\\/chats", tabs)
        self.assertIn("courses\\/\\d+\\/talk", tabs)
        self.assertIn("dm\\/groups", tabs)
        self.assertIn("shouldHideBottomNav", tabs)
        self.assertIn("return isConversationPath(pathname)", tabs)


class DualHeaderRemovalTests(SimpleTestCase):
    def test_post_detail_does_not_render_page_header(self):
        src = _read("frontend/src/pages/TimelinePostDetailPage.tsx")
        self.assertNotIn("post-detail-header", src)
        self.assertNotIn("post-detail-back", src)
        self.assertIn("fromWaseWase", src)
        self.assertIn("navigate(-1)", src)
        self.assertIn('navigate("/", { replace: true })', src)
        self.assertIn('data-spa-page="投稿"', src)

    def test_community_thread_keeps_header_while_loading(self):
        src = _read("frontend/src/pages/CommunityThreadPage.tsx")
        self.assertNotIn("community-back", src)
        self.assertIn("読み込み中…", src)
        loading = src.split("if (loading)")[1].split("if (error")[0]
        self.assertIn('data-spa-page="コミュニティ"', loading)
        self.assertIn("community-thread-page", loading)

    def test_product_detail_keeps_header_while_loading(self):
        src = _read("frontend/src/pages/ProductDetailPage.tsx")
        self.assertNotIn("← フリマへ戻る", src)
        self.assertIn("読み込み中…", src)
        loading = src.split("if (loading)")[1].split("if (error")[0]
        self.assertIn("product-detail-page", loading)
        self.assertIn("seller", src)
        self.assertIn("deleteProduct", src)
        self.assertIn("shareProductToTimeline", src)
        self.assertIn("startProductChat", src)

    def test_profile_settings_notifications_drop_duplicate_back_rows(self):
        profile = _read("frontend/src/pages/ProfilePage.tsx")
        settings = _read("frontend/src/pages/SettingsPage.tsx")
        notify = _read("frontend/src/pages/NotificationsPage.tsx")
        follow = _read("frontend/src/pages/FollowListPage.tsx")
        req = _read("frontend/src/pages/FollowRequestsPage.tsx")
        course = _read("frontend/src/pages/CourseDetailPage.tsx")
        self.assertNotIn("profile-back", profile)
        self.assertNotIn("profile-back", settings)
        self.assertNotIn('className="page-title">通知', notify)
        self.assertNotIn("profile-back", follow)
        self.assertNotIn("profile-back", req)
        self.assertNotIn("course-detail__back", course)

    def test_conversation_pages_keep_in_page_back(self):
        dm = _read("frontend/src/pages/DmRoomPage.tsx")
        group = _read("frontend/src/pages/GroupRoomPage.tsx")
        talk = _read("frontend/src/pages/CourseTalkPage.tsx")
        trade = _read("frontend/src/pages/TradeChatPage.tsx")
        self.assertIn("dm-back-text", dm)
        self.assertIn("dm-back-text", group)
        self.assertIn("dm-back-text", talk)
        self.assertIn("back-link", trade)


class OffsetAndSafeAreaTests(SimpleTestCase):
    def test_header_height_is_sat_plus_content_not_double_counted_on_content(self):
        css = _read("static/css/capacitor_native.css")
        self.assertIn("--wase-header-content-h", css)
        self.assertIn("--wase-chrome-offset: var(--wase-header-h)", css)
        self.assertIn("html.chrome-conversation", css)
        self.assertIn("padding-top: var(--wase-chrome-offset, var(--wase-header-h))", css)
        self.assertNotIn(".main-column:has(> .site-header)", css)
        header_h = css.split("--wase-header-h:")[1].split(";")[0]
        self.assertIn("--wase-sat", header_h)
        self.assertIn("--wase-header-content-h", header_h)
        content_pad = [
            line
            for line in css.splitlines()
            if "padding-top: var(--wase-chrome-offset" in line
        ]
        self.assertTrue(content_pad)
        self.assertFalse(any("safe-area-inset-top" in line for line in content_pad))

    def test_timetable_uses_shared_header_token(self):
        css = _read("frontend/src/styles/timetable.css")
        self.assertIn("var(--wase-chrome-offset, var(--wase-header-h))", css)
        self.assertNotIn("var(--wase-header-h, 64px)", css)

    def test_chat_frame_uses_chrome_offset(self):
        css = _read("frontend/src/styles/dm.css")
        self.assertIn("var(--wase-chrome-offset, var(--wase-header-h, 0px))", css)
        self.assertIn("html.chrome-detail .dm-inbox-header", css)
        self.assertIn("html.chrome-detail .dm-group-header", css)

    def test_pwa_head_sets_header_h_on_first_native_frame(self):
        head = _read("templates/includes/pwa_head.html")
        self.assertIn("css/capacitor_native.css", head)
        self.assertIn('js/capacitor_native.js', head)
        self.assertIn("--wase-sat", head)
        self.assertIn("--wase-header-h", head)
        self.assertIn("min + 10 + 44 + 10", head)


class NativeAndScrollPreserveTests(SimpleTestCase):
    def test_ios_edge_swipe_flag_unchanged(self):
        src = _read("ios/App/App/AppDelegate.swift")
        self.assertIn("webView.allowsBackForwardNavigationGestures = true", src)

    def test_timeline_scroll_restore_still_present(self):
        home = _read("frontend/src/pages/HomePage.tsx")
        api = _read("frontend/src/features/profile/api.ts")
        self.assertIn('restoreScrollPosition("/")', home)
        self.assertIn("export function saveScrollPosition", api)
        self.assertIn("export function restoreScrollPosition", api)

    def test_detail_header_has_accessible_back_target(self):
        src = _read("frontend/src/components/AppDetailHeader.tsx")
        self.assertIn('aria-label="戻る"', src)
        self.assertIn("shell-header-back", src)
        css = _read("frontend/src/styles/shell.css")
        self.assertIn(".shell-header-back", css)
        self.assertIn("min-width: 44px", css)
        self.assertIn("min-height: 44px", css)
        self.assertIn("site-header--detail", css)

    def test_account_drawer_stays_above_header(self):
        css = _read("frontend/src/styles/shell.css")
        self.assertIn("z-index: 2400", css)
        self.assertIn("z-index: 1000", css.split(".site-header")[1][:80])
