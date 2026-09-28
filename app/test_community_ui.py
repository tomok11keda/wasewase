"""Community index chrome: compact tabs, no faculty/search bars."""

from __future__ import annotations

from pathlib import Path

from django.test import SimpleTestCase

ROOT = Path(__file__).resolve().parents[1]


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


class CommunityIndexChromeTests(SimpleTestCase):
    def test_community_hides_faculty_filter_and_local_search(self):
        page = _read("frontend/src/pages/CommunitiesPage.tsx")
        self.assertNotIn("FacultyFilterTabs", page)
        self.assertNotIn("LocalSearchBar", page)
        self.assertNotIn("コミュニティのスレッドを検索", page)
        self.assertNotIn("ranking-sort-tabs", page)

    def test_community_keeps_hub_sort_compose_and_feed_plumbing(self):
        page = _read("frontend/src/pages/CommunitiesPage.tsx")
        self.assertIn("community-hub-tabs", page)
        self.assertIn("community-sort-tabs", page)
        self.assertIn("新規スレッド", page)
        self.assertIn("おすすめ", page)
        self.assertIn("最新", page)
        self.assertIn("授業", page)
        self.assertIn("Communityでは匿名で投稿できます", page)
        self.assertIn("fetchCommunityThreads", page)
        self.assertIn("tag: tag || undefined", page)
        self.assertIn("q: qParam || undefined", page)
        self.assertIn('searchParams.get("sort")', page)
        self.assertIn("analytics.communityViewed", page)
        self.assertIn("analytics.communityPostCreated", page)
        self.assertIn("thread-card__replies", page)
        self.assertIn("CommunityReportMenu", page)

    def test_flea_and_thread_detail_keep_existing_surfaces(self):
        flea = _read("frontend/src/pages/FleaPage.tsx")
        detail = _read("frontend/src/pages/CommunityThreadPage.tsx")
        self.assertIn("FacultyFilterTabs", flea)
        self.assertIn("COMMUNITY_ANON_HINT", detail)
        self.assertNotIn("community-hub-tabs", detail)

    def test_community_styles_are_index_scoped(self):
        css = _read("frontend/src/styles/community.css")
        self.assertIn(".community-hub-tabs", css)
        self.assertIn(".community-sort-tabs", css)
        self.assertIn(".communities-page .thread-card", css)
        self.assertIn(".thread-card__replies.is-zero", css)
        chrome = css.split(".community-thread-page")[0]
        self.assertNotIn("backdrop-filter", chrome)
        self.assertNotIn("position: sticky", chrome)
