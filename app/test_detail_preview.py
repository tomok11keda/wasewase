"""Native Feel Phase 2: list→detail first paint via location.state preview."""

from __future__ import annotations

from pathlib import Path

from django.test import SimpleTestCase

ROOT = Path(__file__).resolve().parents[1]


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


class TimelinePreviewNavTests(SimpleTestCase):
    def test_card_navigation_passes_initial_post(self):
        card = _read("frontend/src/features/timeline/TimelinePostCard.tsx")
        anchor = _read("frontend/src/features/timeline/postAnchor.ts")
        self.assertIn("timelinePostDetailState(post, opts)", card)
        self.assertIn("timelinePostDetailState(post)", card)
        self.assertIn("fromWaseWase: true", anchor)
        self.assertIn("initialPost: compactTimelinePost(post)", anchor)
        self.assertIn("focusComposer", anchor)
        self.assertIn("comments: []", anchor)

    def test_post_detail_first_paints_from_initial_post(self):
        src = _read("frontend/src/pages/TimelinePostDetailPage.tsx")
        self.assertIn("readInitialTimelinePost", src)
        self.assertIn("useState<TimelinePost | null>(() =>", src)
        self.assertIn("const [loading, setLoading] = useState(() => !post)", src)
        self.assertIn("fetchTimelinePost", src)
        self.assertIn("commentsPending={!hydrated}", src)
        self.assertIn("mutatedRef", src)
        self.assertIn("fetchGen", src)

    def test_post_detail_background_fetch_reconciles_and_handles_errors(self):
        src = _read("frontend/src/pages/TimelinePostDetailPage.tsx")
        self.assertIn("const next = await fetchTimelinePost(postId)", src)
        self.assertIn("setHydrated(true)", src)
        self.assertIn('setError("この投稿は表示できません")', src)
        self.assertIn("setPost(null)", src)
        self.assertIn('message !== "この投稿は表示できません"', src)
        self.assertIn("navState?.fromWaseWase", src)
        self.assertIn("navState?.focusComposer", src)

    def test_interactive_targets_still_ignored(self):
        src = _read("frontend/src/features/timeline/postAnchor.ts")
        self.assertIn("TIMELINE_POST_DETAIL_IGNORE_SELECTOR", src)
        for token in (
            ".timeline-flea-share",
            ".share-card",
            ".tweet-media",
            ".quoted-post-card",
            '[role="button"]',
        ):
            self.assertIn(token, src)
        card = _read("frontend/src/features/timeline/TimelinePostCard.tsx")
        self.assertIn("isTimelinePostDetailIgnoreTarget", card)
        self.assertIn("isQuotedPostInnerIgnoreTarget", card)


class QuotedRepostNavTests(SimpleTestCase):
    def test_quoted_original_card_navigates_to_original_id(self):
        card = _read("frontend/src/features/timeline/TimelinePostCard.tsx")
        quoted = card.split("{post.quoted_post ? (")[1].split("{post.shared_product")[0]
        self.assertIn("`/posts/${quoted.id}`", quoted)
        self.assertNotIn("`/posts/${post.id}`", quoted)
        self.assertIn("quotedPostDetailState()", quoted)
        self.assertIn("saveScrollPosition(\"/\")", quoted)
        self.assertIn("event.stopPropagation()", quoted)
        self.assertIn("isQuotedPostInnerIgnoreTarget(event.target)", quoted)
        self.assertIn("quoted.is_removed", quoted)
        self.assertIn("quoted-post-card--unavailable", quoted)

    def test_quoted_state_is_internal_push_without_fake_preview(self):
        anchor = _read("frontend/src/features/timeline/postAnchor.ts")
        helper = anchor.split("export function quotedPostDetailState")[1].split(
            "export function readInitialTimelinePost"
        )[0]
        self.assertIn("fromWaseWase: true", helper)
        self.assertNotIn("initialPost", helper)
        self.assertNotIn("compactTimelinePost", helper)
        full = anchor.split("export function timelinePostDetailState")[1].split(
            "export function quotedPostDetailState"
        )[0]
        self.assertIn("initialPost: compactTimelinePost(post)", full)

    def test_quoted_inner_ignore_excludes_the_card_itself(self):
        src = _read("frontend/src/features/timeline/postAnchor.ts")
        parent = src.split("TIMELINE_POST_DETAIL_IGNORE_SELECTOR")[1].split(
            "QUOTED_POST_INNER_IGNORE_SELECTOR"
        )[0]
        inner = src.split("QUOTED_POST_INNER_IGNORE_SELECTOR")[1].split(
            "export type TimelinePostDetailNavState"
        )[0]
        self.assertIn(".quoted-post-card", parent)
        self.assertNotIn(".quoted-post-card", inner)
        self.assertIn(".tweet-media", inner)
        self.assertIn("isQuotedPostInnerIgnoreTarget", src)

    def test_detail_page_and_transition_architecture_unchanged(self):
        detail = _read("frontend/src/pages/TimelinePostDetailPage.tsx")
        transition = _read("frontend/src/lib/detailTransition.ts")
        self.assertIn("readInitialTimelinePost", detail)
        self.assertIn("fetchTimelinePost", detail)
        self.assertIn("navState?.fromWaseWase", detail)
        self.assertIn("DETAIL_PUSH_MS = 400", transition)
        self.assertIn('navigationType !== "PUSH"', transition)
        self.assertIn("restoreScrollPosition(key, true)", transition)


class CommunityPreviewNavTests(SimpleTestCase):
    def test_thread_navigation_passes_public_preview_only(self):
        nav = _read("frontend/src/features/community/threadNav.ts")
        list_page = _read("frontend/src/pages/CommunitiesPage.tsx")
        self.assertIn("communityThreadDetailState", list_page)
        self.assertIn("publicThreadPreview", nav)
        self.assertIn("can_delete: false", nav)
        self.assertIn("is_mine: false", nav)
        self.assertIn("can_report: false", nav)
        self.assertNotIn("email", nav)
        self.assertNotIn("username", nav)
        self.assertNotIn("user_id", nav)
        self.assertIn("anonymous_label", nav)
        self.assertIn("replies: []", nav)

    def test_thread_detail_first_paints_and_fetches(self):
        src = _read("frontend/src/pages/CommunityThreadPage.tsx")
        self.assertIn("readInitialThread", src)
        self.assertIn("fetchThreadDetail", src)
        self.assertIn("発言を読み込み中", src)
        self.assertIn("mutatedRef", src)
        self.assertIn("err instanceof TypeError", src)
        self.assertIn("const [loading, setLoading] = useState(() => !thread)", src)

    def test_search_and_discover_thread_links_use_preview(self):
        search = _read("frontend/src/pages/SearchPage.tsx")
        discover = _read("frontend/src/features/search/DiscoverCompactCards.tsx")
        self.assertIn("communityThreadDetailState(threadSummaryFromSearch(thread))", search)
        self.assertIn(
            "communityThreadDetailState(threadSummaryFromSearch(thread))",
            discover,
        )


class FleaPreviewNavTests(SimpleTestCase):
    def test_product_navigation_passes_preview(self):
        flea = _read("frontend/src/pages/FleaPage.tsx")
        nav = _read("frontend/src/features/flea/productNav.ts")
        self.assertIn("productDetailState(product)", flea)
        self.assertIn("can_purchase: false", nav)
        self.assertIn("can_delete: false", nav)
        self.assertIn("can_negotiate: false", nav)
        self.assertIn("can_share_to_timeline: false", nav)
        self.assertIn("show_trade_link: false", nav)
        self.assertIn("can_contact_seller: false", nav)
        self.assertIn("seller_chat_rooms: []", nav)

    def test_product_detail_first_paints_without_trusting_privileges(self):
        src = _read("frontend/src/pages/ProductDetailPage.tsx")
        self.assertIn("readInitialProduct", src)
        self.assertIn("fetchProductDetail", src)
        self.assertIn("const [loading, setLoading] = useState(() => !product)", src)
        self.assertIn("product.can_delete", src)
        self.assertIn("product.can_purchase", src)
        self.assertIn("product.can_contact_seller", src)
        self.assertIn("コメントを読み込み中", src)
        self.assertIn("err instanceof TypeError", src)

    def test_other_product_entry_points_pass_preview(self):
        profile = _read("frontend/src/pages/ProfilePage.tsx")
        search = _read("frontend/src/pages/SearchPage.tsx")
        share = _read("frontend/src/features/timeline/TimelineFleaShareCard.tsx")
        dm_share = _read("frontend/src/features/share/SharedContentCard.tsx")
        self.assertIn("productDetailState(p)", profile)
        self.assertIn("productDetailState(productCardFromSearch(product))", search)
        self.assertIn("productCardFromShared(product)", share)
        self.assertIn("productCardFromFleaShare", dm_share)


class Phase2RegressionTests(SimpleTestCase):
    def test_phase1_detail_header_and_bottom_nav_unchanged(self):
        shell = _read("frontend/src/layouts/AppShellLayout.tsx")
        header = _read("frontend/src/components/AppDetailHeader.tsx")
        self.assertIn("AppDetailHeader", shell)
        self.assertIn("shouldHideBottomNav", shell)
        self.assertIn('aria-label="戻る"', header)
        self.assertNotIn("post-detail-header", _read("frontend/src/pages/TimelinePostDetailPage.tsx"))

    def test_scroll_restore_and_keep_alive_unchanged(self):
        home = _read("frontend/src/pages/HomePage.tsx")
        card = _read("frontend/src/features/timeline/TimelinePostCard.tsx")
        keep = _read("frontend/src/layouts/TabKeepAliveLayout.tsx")
        self.assertIn('restoreScrollPosition("/")', home)
        self.assertIn("saveScrollPosition", card)
        self.assertIn("export function TabKeepAliveLayout", keep)
        self.assertNotIn("visibility: hidden", keep)

    def test_no_native_ios_changes_required(self):
        src = _read("ios/App/App/AppDelegate.swift")
        self.assertIn("webView.allowsBackForwardNavigationGestures = true", src)

    def test_no_global_cache_library(self):
        pkg = _read("frontend/package.json")
        for name in ("@tanstack/react-query", "swr", "zustand", "redux", "@apollo/client"):
            self.assertNotIn(name, pkg)

    def test_push_router_does_not_invent_preview_state(self):
        src = _read("frontend/src/components/NativePushOpenRouter.tsx")
        self.assertNotIn("initialPost", src)
        self.assertNotIn("initialThread", src)
        self.assertNotIn("initialProduct", src)
