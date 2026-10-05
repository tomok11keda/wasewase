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
        self.assertIn("aria-pressed", page)
        self.assertIn("role=\"group\"", page)
        self.assertIn("＋ 新規スレッド", page)
        self.assertIn("btn-new-thread--desktop", page)
        self.assertIn("おすすめ", page)
        self.assertIn("最新", page)
        self.assertIn("授業", page)
        self.assertIn("Communityでは匿名で投稿できます", page)
        self.assertIn("匿名で投稿されます", page)
        self.assertIn('hub === "community"', page)
        self.assertIn("fetchCommunityThreads", page)
        self.assertIn("tag: tag || undefined", page)
        self.assertIn("q: qParam || undefined", page)
        self.assertIn('searchParams.get("sort")', page)
        self.assertIn("analytics.communityViewed", page)
        self.assertIn("analytics.communityPostCreated", page)
        self.assertIn("thread-card__replies", page)
        self.assertIn("CommunityReportMenu", page)

    def test_community_mobile_compose_uses_timeline_style_fab(self):
        page = _read("frontend/src/pages/CommunitiesPage.tsx")
        home = _read("frontend/src/pages/HomePage.tsx")
        self.assertIn("community-compose-fab", page)
        self.assertIn('aria-label="匿名で投稿"', page)
        self.assertIn("createPortal", page)
        self.assertIn("shell-hide-on-desktop", page)
        self.assertIn("hub === \"community\" && !composeOpen", page)
        self.assertIn('activeTab === "communities"', page)
        self.assertNotIn('spaLoginPath("/app/?compose=1")', page)
        self.assertNotIn("openCompose: true", page)
        self.assertIn("compose-fab", home)
        self.assertIn('aria-label="投稿する"', home)
        self.assertNotIn("community-compose-fab", home)
        self.assertNotIn('aria-label="匿名で投稿"', home)

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
        self.assertIn(".btn-new-thread--desktop", css)
        self.assertIn(".community-compose__anon", css)
        chrome = css.split(".community-thread-page")[0]
        self.assertNotIn("backdrop-filter", chrome)
        self.assertNotIn("position: sticky", chrome)

    def test_sort_filter_is_compact_pills_not_underline_tabs(self):
        css = _read("frontend/src/styles/community.css")
        page = _read("frontend/src/pages/CommunitiesPage.tsx")
        chrome = css.split(".community-thread-page")[0]
        self.assertIn(".community-hub-tab.is-active::after", chrome)
        self.assertNotIn(".community-sort-tab.is-active::after", chrome)
        self.assertNotIn(
            ".community-hub-tabs,\n.community-sort-tabs",
            chrome,
        )
        self.assertIn("width: fit-content", chrome)
        self.assertIn("rgba(137, 30, 43, 0.08)", chrome)
        self.assertIn('aria-pressed={sort === "recommended"}', page)
        self.assertIn("hub === \"community\" ? (", page)


class CommunityComposeSpacingTests(SimpleTestCase):
    def test_fab_visible_keeps_thread_list_clearance(self):
        css = _read("frontend/src/styles/community.css")
        page = _read("frontend/src/pages/CommunitiesPage.tsx")
        rule = css.split(".communities-page .thread-list")[1].split("}")[0]
        self.assertIn("padding-bottom: calc(52px + 24px)", rule)
        self.assertIn("hub === \"community\" && !composeOpen", page)
        self.assertIn("community-compose-fab", page)

    def test_composer_open_drops_fab_clearance(self):
        css = _read("frontend/src/styles/community.css")
        page = _read("frontend/src/pages/CommunitiesPage.tsx")
        self.assertIn('communities-page${composeOpen ? " is-composing" : ""}', page)
        composing = css.split(".communities-page.is-composing .thread-list")[1].split(
            "}"
        )[0]
        self.assertIn("padding-bottom: 16px", composing)
        self.assertNotIn("52px", composing)
