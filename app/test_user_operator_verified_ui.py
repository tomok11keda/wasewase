"""Operator verification badge wiring and display-contract tests."""

from __future__ import annotations

from pathlib import Path

from django.test import SimpleTestCase

ROOT = Path(__file__).resolve().parents[1]


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


class VerifiedAccountBadgeContractTests(SimpleTestCase):
    def test_should_show_only_for_true(self):
        source = _read("frontend/src/components/VerifiedAccountBadge.tsx")
        self.assertIn("return verified === true;", source)
        self.assertIn('className="account-verified-badge"', source)
        self.assertIn('aria-label="WaseWase運営認証アカウント"', source)
        css = _read("frontend/src/styles/account-verified.css")
        self.assertIn("pointer-events: none", css)
        self.assertIn("flex-shrink: 0", css)
        self.assertIn("account-verified-name__text", source)
        self.assertIn(
            ".tweet-author .account-verified-name__text",
            css,
        )
        self.assertIn("text-overflow: ellipsis", css)
        self.assertNotIn("<button", source)
        self.assertNotIn("onClick", source)
        self.assertNotIn("OfficialBadge", source)
        self.assertNotIn("official-badge", source)

        def should_show(verified):
            return verified is True

        self.assertTrue(should_show(True))
        for value in (False, None, 0, "", "true"):
            self.assertFalse(should_show(value))

    def test_css_is_separated_from_community_official(self):
        css = _read("frontend/src/styles/account-verified.css")
        community = _read("frontend/src/styles/community.css")
        self.assertIn(".account-verified-badge", css)
        self.assertNotIn(".official-badge", css)
        self.assertNotIn(".account-verified-badge", community)
        self.assertNotIn(":has(", css)
        main = _read("frontend/src/main.tsx")
        self.assertIn("./styles/account-verified.css", main)


class VerifiedAccountBadgeUsageTests(SimpleTestCase):
    SCREENS = (
        "frontend/src/pages/ProfilePage.tsx",
        "frontend/src/features/timeline/TimelinePostCard.tsx",
        "frontend/src/pages/SearchPage.tsx",
        "frontend/src/features/search/DiscoverCompactCards.tsx",
        "frontend/src/pages/FollowListPage.tsx",
        "frontend/src/pages/FollowRequestsPage.tsx",
        "frontend/src/components/SidebarNav.tsx",
        "frontend/src/components/AccountMenuContent.tsx",
        "frontend/src/pages/DmInboxPage.tsx",
        "frontend/src/pages/DmRoomPage.tsx",
        "frontend/src/pages/GroupRoomPage.tsx",
        "frontend/src/pages/GroupCreatePage.tsx",
        "frontend/src/pages/TradeChatPage.tsx",
        "frontend/src/pages/FleaPage.tsx",
        "frontend/src/pages/ProductDetailPage.tsx",
        "frontend/src/features/timeline/LikerListModal.tsx",
        "frontend/src/components/ShareActionSheet.tsx",
        "frontend/src/features/share/SharedContentCard.tsx",
        "frontend/src/features/onboarding/FollowStep.tsx",
        "frontend/src/pages/TimetablePage.tsx",
        "frontend/src/features/chat/ChatThreadMessage.tsx",
        "frontend/src/pages/MessageRequestsPage.tsx",
        "frontend/src/pages/HomePage.tsx",
    )

    def test_priority_screens_use_account_display_name(self):
        for rel in self.SCREENS:
            source = _read(rel)
            with self.subTest(rel=rel):
                self.assertIn("AccountDisplayName", source)
                self.assertIn("is_operator_verified", source)

    def test_dm_and_group_use_sender_flag(self):
        chat = _read("frontend/src/features/chat/ChatThreadMessage.tsx")
        self.assertIn("m.sender_is_operator_verified", chat)
        self.assertIn("m.reply_to.sender_is_operator_verified", chat)
        trade = _read("frontend/src/pages/TradeChatPage.tsx")
        self.assertIn("m.sender_is_operator_verified", trade)
        self.assertIn("AccountDisplayName", trade)
        self.assertIn("liveRoom.partner", trade)
        self.assertIn("ChatRoomHeader", trade)
        inbox = _read("frontend/src/pages/DmInboxPage.tsx")
        self.assertIn("item.partner?.is_operator_verified", inbox)
        self.assertIn("item.latest_sender_is_operator_verified", inbox)
        self.assertIn("dm-inbox-preview-text", inbox)
        self.assertIn("item.kind === \"dm\" && !item.is_blocked", inbox)

    def test_community_anonymous_surfaces_do_not_use_account_badge(self):
        for rel in (
            "frontend/src/pages/CommunitiesPage.tsx",
            "frontend/src/pages/CommunityThreadPage.tsx",
            "frontend/src/features/community/OfficialBadge.tsx",
        ):
            source = _read(rel)
            with self.subTest(rel=rel):
                self.assertNotIn("VerifiedAccountBadge", source)
                self.assertNotIn("AccountDisplayName", source)
                self.assertNotIn("is_operator_verified", source)
                self.assertNotIn("account-verified-badge", source)

    def test_search_keeps_community_official_separate(self):
        search = _read("frontend/src/pages/SearchPage.tsx")
        self.assertIn("OfficialBadge", search)
        self.assertIn("AccountDisplayName", search)
        self.assertIn("thread.community.is_official", search)
        self.assertIn("user.is_operator_verified", search)
        discover = _read("frontend/src/features/search/DiscoverCompactCards.tsx")
        self.assertIn("OfficialBadge", discover)
        self.assertIn("post.author?.is_operator_verified", discover)
