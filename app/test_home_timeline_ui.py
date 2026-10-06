"""Home timeline chrome: compact sort tabs, no faculty/search bars."""

from __future__ import annotations

import re
from pathlib import Path

from django.test import SimpleTestCase

ROOT = Path(__file__).resolve().parents[1]


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


class HomeTimelineChromeTests(SimpleTestCase):
    def test_home_hides_faculty_filter_and_local_search(self):
        home = _read("frontend/src/pages/HomePage.tsx")
        self.assertNotIn("FacultyFilterTabs", home)
        self.assertNotIn("LocalSearchBar", home)
        self.assertNotIn("タイムライン投稿を検索", home)
        self.assertNotIn("faculty-hint", home)
        self.assertNotIn("ranking-sort-tabs", home)

    def test_home_keeps_sort_compose_and_feed_plumbing(self):
        home = _read("frontend/src/pages/HomePage.tsx")
        self.assertIn("home-sort-tabs", home)
        self.assertIn("home-compose", home)
        self.assertIn("home-feed", home)
        self.assertIn("おすすめ", home)
        self.assertIn("最新", home)
        self.assertIn("いまどうしてる？", home)
        self.assertIn("compose-fab", home)
        self.assertIn('searchParams.get("sort")', home)
        self.assertIn("fetchTimeline", home)
        self.assertIn("faculty: faculty || undefined", home)
        self.assertIn("q: qParam || undefined", home)

    def test_other_hubs_keep_faculty_filter(self):
        flea = _read("frontend/src/pages/FleaPage.tsx")
        self.assertIn("FacultyFilterTabs", flea)

    def test_compose_fab_uses_brand_color_and_keeps_stacking(self):
        home_css = _read("frontend/src/styles/home.css")
        self.assertRegex(home_css, r"\.compose-fab\s*\{[^}]*z-index:\s*250")
        self.assertRegex(
            home_css,
            r"\.compose-fab\s*\{[^}]*background:\s*var\(--accent",
        )
        self.assertNotRegex(
            home_css,
            r"\.compose-fab\s*\{[^}]*#1d9bf0",
        )
        fab = home_css.split(".compose-fab")[1].split("}")[0]
        self.assertIn("position: fixed", fab)
        self.assertIn("var(--nav-h)", fab)
        self.assertIn("env(safe-area-inset-bottom, 0px)", fab)

    def test_home_fab_stays_visible_at_top_and_while_compose_cue_shows(self):
        home = _read("frontend/src/pages/HomePage.tsx")
        self.assertNotIn("composeCueInView", home)
        self.assertNotIn("revealComposeFab", home)
        self.assertNotIn("homeComposeRef", home)
        self.assertIn("showComposeFab", home)
        self.assertIn("!composeOpen", home)
        self.assertIn('activeTab === "home"', home)
        self.assertIn("createPortal", home)
        self.assertIn("document.body", home)
        self.assertIn("home-compose-fab shell-hide-on-desktop is-visible", home)
        self.assertIn("いまどうしてる？", home)
        home_css = _read("frontend/src/styles/home.css")
        self.assertIn(".home-compose-fab.is-visible", home_css)

    def test_feed_flatten_styles_are_home_scoped(self):
        main = _read("frontend/src/main.tsx")
        self.assertIn("timeline-feed.css", main)
        css = _read("frontend/src/styles/timeline-feed.css")
        self.assertIn(".timeline-home .home-feed", css)
        self.assertIn(".timeline-home .home-feed .tweet-card", css)
        unscoped = re.findall(
            r"^[^\s/@].*\{",
            css,
            flags=re.MULTILINE,
        )
        for rule in unscoped:
            self.assertTrue(
                rule.startswith(".timeline-home"),
                f"feed restyle must stay under .timeline-home: {rule}",
            )
        timeline_css = _read("frontend/src/styles/timeline.css")
        self.assertNotIn("home-feed", timeline_css)
        self.assertNotIn("home-sort-tabs", timeline_css)


class HomeMotionPilotTests(SimpleTestCase):
    def test_motion_tokens_are_shared_and_fast(self):
        tokens = _read("frontend/src/styles/tokens.css")
        motion = _read("frontend/src/lib/motion.ts")
        self.assertIn("--motion-fast: 120ms", tokens)
        self.assertIn("--motion-base: 180ms", tokens)
        self.assertIn("--motion-tab: 180ms", tokens)
        self.assertIn("--motion-sheet: 240ms", tokens)
        self.assertIn("cubic-bezier(0.2, 0.8, 0.2, 1)", tokens)
        self.assertIn("prefers-reduced-motion: reduce", tokens)
        self.assertIn("MOTION_FAST_MS = 120", motion)
        self.assertIn("MOTION_SHEET_MS = 240", motion)

    def test_home_sort_indicator_slides_instead_of_instant_underline(self):
        home = _read("frontend/src/pages/HomePage.tsx")
        css = _read("frontend/src/styles/home.css")
        self.assertIn("home-sort-indicator", home)
        self.assertIn("data-sort={sort}", home)
        self.assertIn("home-feed${feedEnter", home)
        self.assertIn(".home-sort-indicator", css)
        self.assertIn("translateX(100%)", css)
        self.assertNotIn(".home-sort-tab.is-active::after", css)

    def test_home_fab_uses_motion_tokens_and_always_visible_class(self):
        css = _read("frontend/src/styles/home.css")
        home = _read("frontend/src/pages/HomePage.tsx")
        self.assertIn("var(--motion-base)", css.split(".home-compose-fab")[1].split(".home-compose-fab.is-visible")[0])
        self.assertIn("is-visible", home)
        self.assertNotIn("revealComposeFab", home)
        self.assertNotIn("composeCueInView", home)

    def test_home_like_bookmark_pop_and_card_press_are_home_scoped(self):
        card = _read("frontend/src/features/timeline/TimelinePostCard.tsx")
        bookmark = _read("frontend/src/components/BookmarkButton.tsx")
        feed = _read("frontend/src/styles/timeline-feed.css")
        self.assertIn("likePopping", card)
        self.assertIn("is-popping", card)
        self.assertIn("is-popping", bookmark)
        self.assertIn("wase-home-pop", feed)
        self.assertIn(".timeline-home .home-feed .tweet-card:active", feed)
        self.assertIn("scale(0.99)", feed)

    def test_detail_push_duration_unchanged(self):
        src = _read("frontend/src/lib/detailTransition.ts")
        self.assertIn("DETAIL_PUSH_MS = 400", src)


class PrimaryActionFabContractTests(SimpleTestCase):
    def test_flea_main_list_has_always_on_exhibit_fab(self):
        flea = _read("frontend/src/pages/FleaPage.tsx")
        exhibit = _read("frontend/src/pages/ExhibitPage.tsx")
        self.assertIn("flea-compose-fab", flea)
        self.assertIn("createPortal", flea)
        self.assertIn("document.body", flea)
        self.assertIn('activeTab === "flea"', flea)
        self.assertIn('aria-label="商品を出品"', flea)
        self.assertIn("/flea/exhibit", flea)
        self.assertIn("is-visible", flea)
        self.assertNotIn("composeCueInView", flea)
        self.assertNotIn("scrollY", flea)
        self.assertNotIn("flea-compose-fab", exhibit)

    def test_search_and_timetable_do_not_mount_create_fabs(self):
        search = _read("frontend/src/pages/SearchPage.tsx")
        timetable = _read("frontend/src/pages/TimetablePage.tsx")
        self.assertNotIn("compose-fab", search)
        self.assertNotIn("flea-compose-fab", search)
        self.assertNotIn("compose-fab", timetable)
        self.assertNotIn("flea-compose-fab", timetable)

    def test_inactive_keep_alive_tabs_do_not_leak_fabs(self):
        home = _read("frontend/src/pages/HomePage.tsx")
        community = _read("frontend/src/pages/CommunitiesPage.tsx")
        flea = _read("frontend/src/pages/FleaPage.tsx")
        keep = _read("frontend/src/layouts/TabKeepAliveLayout.tsx")
        self.assertIn("export function TabKeepAliveLayout", keep)
        self.assertIn("useActiveMainTab", home)
        self.assertIn("useActiveMainTab", community)
        self.assertIn("useActiveMainTab", flea)
        self.assertIn('activeTab === "home"', home)
        self.assertIn('activeTab === "communities"', community)
        self.assertIn('activeTab === "flea"', flea)
        self.assertIn("document.body", home)
        self.assertIn("document.body", community)
        self.assertIn("document.body", flea)
        css = _read("frontend/src/styles/shell.css")
        stack = css.split(".tab-keep-alive-stack")[1].split("}")[0]
        self.assertIn("overflow: hidden", stack)

    def test_phase2_shell_height_and_nav_gutter_unchanged(self):
        tokens = _read("frontend/src/styles/tokens.css")
        self.assertIn(
            "min-height: calc(100dvh - var(--nav-h) - env(safe-area-inset-bottom, 0px))",
            tokens,
        )
        self.assertIn(
            "padding-bottom: calc(var(--nav-h) + env(safe-area-inset-bottom, 0px))",
            tokens,
        )
