"""Official badge wiring and display-contract tests."""

from __future__ import annotations

from pathlib import Path

from django.test import SimpleTestCase

ROOT = Path(__file__).resolve().parents[1]


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


class OfficialBadgeContractTests(SimpleTestCase):
    def test_should_show_only_for_true(self):
        source = _read("frontend/src/features/community/OfficialBadge.tsx")
        self.assertIn("return official === true;", source)
        self.assertIn("export function officialBoardClass", source)
        self.assertIn("${baseClass} ${baseClass}--official", source)

        def should_show_official_badge(official):
            return official is True

        def official_board_class(base_class, official):
            if not should_show_official_badge(official):
                return base_class
            return f"{base_class} {base_class}--official"

        self.assertTrue(should_show_official_badge(True))
        for value in (False, None, 0, "", "true"):
            self.assertFalse(should_show_official_badge(value))
            self.assertEqual(
                official_board_class("thread-card__board", value),
                "thread-card__board",
            )
        self.assertEqual(
            official_board_class("thread-card__board", True),
            "thread-card__board thread-card__board--official",
        )

    def test_badge_component_is_noninteractive_and_text_based(self):
        source = _read("frontend/src/features/community/OfficialBadge.tsx")
        self.assertIn("export function shouldShowOfficialBadge", source)
        self.assertIn("return official === true;", source)
        self.assertIn('aria-label="公式コミュニティ"', source)
        self.assertIn("公式", source)
        self.assertNotIn("<button", source)
        self.assertNotIn("onClick", source)
        self.assertNotIn("大学公認", source)
        self.assertNotIn("大学運営", source)
        self.assertIn("if (!shouldShowOfficialBadge(official)) return null;", source)


class OfficialBadgeUsageTests(SimpleTestCase):
    SCREENS = (
        (
            "frontend/src/pages/CommunitiesPage.tsx",
            "thread-card__board",
        ),
        (
            "frontend/src/pages/CommunityThreadPage.tsx",
            "thread-card__board",
        ),
        (
            "frontend/src/pages/SearchPage.tsx",
            "search-thread-card__board",
        ),
        (
            "frontend/src/features/search/DiscoverCompactCards.tsx",
            "discover-compact-card__board",
        ),
    )

    def test_four_surfaces_render_badge_after_community_name(self):
        for rel, base_class in self.SCREENS:
            source = _read(rel)
            with self.subTest(rel=rel):
                self.assertIn("OfficialBadge", source)
                self.assertIn("officialBoardClass", source)
                self.assertIn(f'"{base_class}"', source)
                self.assertIn(
                    "<OfficialBadge official={thread.community.is_official} />",
                    source,
                )
                name_idx = source.index("thread.community.name")
                badge_idx = source.index(
                    "<OfficialBadge official={thread.community.is_official} />"
                )
                self.assertLess(name_idx, badge_idx)

    def test_search_to_detail_copies_is_official(self):
        source = _read("frontend/src/features/community/threadNav.ts")
        self.assertIn("is_official: thread.community.is_official", source)
        types = _read("frontend/src/features/community/api.ts")
        self.assertIn("is_official?: boolean | null;", types)
        search_types = _read("frontend/src/features/profile/api.ts")
        self.assertIn("is_official?: boolean | null;", search_types)

    def test_unofficial_chip_colors_stay_in_place(self):
        css = _read("frontend/src/styles/community.css")
        self.assertIn(".official-badge", css)
        self.assertIn("flex-shrink: 0", css)
        self.assertIn("pointer-events: none", css)
        self.assertNotIn(":has(", css)
        list_chip = css.split(".communities-page .thread-card__board {")[1].split("}")[0]
        self.assertIn("display: inline-block", list_chip)
        self.assertIn("background: #f4f6f7", list_chip)
        detail_idx = css.find("\n.thread-card__board {")
        self.assertGreater(detail_idx, 0)
        detail_chip = css[detail_idx:].split("}", 1)[0]
        self.assertIn("display: inline-block", detail_chip)
        self.assertIn("background: #f7edf0", detail_chip)
        self.assertIn("color: var(--accent)", detail_chip)
        self.assertNotIn("大学公認", css)

    def test_official_modifiers_do_not_use_has(self):
        css = _read("frontend/src/styles/community.css")
        profile = _read("frontend/src/styles/profile.css")
        self.assertNotIn(":has(", css)
        self.assertNotIn(":has(.official-badge)", profile)
        for modifier in (
            ".thread-card__board--official",
            ".search-thread-card__board--official",
            ".discover-compact-card__board--official",
        ):
            self.assertIn(modifier, css)
        unofficial_discover = profile.split(".discover-compact-card__board {")[1].split(
            "}"
        )[0]
        self.assertIn("white-space: nowrap", unofficial_discover)
        self.assertIn("overflow: hidden", unofficial_discover)
        official_discover = css.split(
            ".discover-compact-card__board--official {"
        )[1].split("}")[0]
        self.assertIn("display: inline-flex", official_discover)
        self.assertIn("min-width: 0", official_discover)
        self.assertIn("overflow: hidden", official_discover)
        name_rule = css.split(
            ".discover-compact-card__board--official .discover-compact-card__board-name"
        )[1].split("}")[0]
        self.assertIn("min-width: 0", name_rule)
        self.assertIn("text-overflow: ellipsis", name_rule)
        self.assertIn("flex-shrink: 0", css)

    def test_discover_wraps_name_only_when_official(self):
        source = _read("frontend/src/features/search/DiscoverCompactCards.tsx")
        self.assertIn("shouldShowOfficialBadge(thread.community.is_official)", source)
        self.assertIn(
            'className="discover-compact-card__board-name"',
            source,
        )
        self.assertIn("thread.community.name", source)
        self.assertIn("officialBoardClass", source)
        unofficial_pages = (
            "frontend/src/pages/CommunitiesPage.tsx",
            "frontend/src/pages/CommunityThreadPage.tsx",
            "frontend/src/pages/SearchPage.tsx",
        )
        for rel in unofficial_pages:
            page = _read(rel)
            with self.subTest(rel=rel):
                self.assertNotIn("--official", page)
                self.assertIn("officialBoardClass", page)
