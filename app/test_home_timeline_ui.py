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
        communities = _read("frontend/src/pages/CommunitiesPage.tsx")
        flea = _read("frontend/src/pages/FleaPage.tsx")
        self.assertIn("FacultyFilterTabs", communities)
        self.assertIn("ranking-sort-tabs", communities)
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

    def test_home_fab_hides_while_compose_cue_is_visible(self):
        home = _read("frontend/src/pages/HomePage.tsx")
        self.assertIn("homeComposeRef", home)
        self.assertIn("IntersectionObserver", home)
        self.assertIn("composeCueInView", home)
        self.assertIn("revealComposeFab", home)
        self.assertIn("home-compose-fab", home)
        home_css = _read("frontend/src/styles/home.css")
        self.assertIn(".home-compose-fab", home_css)
        self.assertIn(".home-compose-fab.is-visible", home_css)
        self.assertRegex(
            home_css,
            r"\.home-compose-fab\s*\{[^}]*opacity:\s*0",
        )

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
