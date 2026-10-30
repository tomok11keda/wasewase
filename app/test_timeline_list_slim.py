"""List/discover APIs omit comment bodies but keep counts and visibility."""

from __future__ import annotations

import json
from unittest.mock import patch

from django.db import connection
from django.test import Client, TestCase, override_settings
from django.test.utils import CaptureQueriesContext

from .board_services import TIMELINE_INITIAL_SIZE
from .comment_thread_services import TOMBSTONE_BODY
from .models import (
    Comment,
    Follow,
    Organization,
    OrganizationMember,
    TimelinePost,
    User,
    UserProfile,
)
from .organization_services import add_organization_member
from .profile_api_services import (
    DISCOVER_CANDIDATE_LIMIT,
    DISCOVER_TRENDING_LIMIT,
    _discover_timeline_candidates,
)
from .timeline_api_services import serialize_timeline_post
from .ugc_services import block_user


def _user(email: str, **kwargs) -> User:
    kwargs.setdefault("password", "test-pass-12345")
    user = User.objects.create_user(email=email, **kwargs)
    UserProfile.objects.get_or_create(
        user=user, defaults={"name": email.split("@")[0]}
    )
    return user


@override_settings(BROWSE_MODE_GATE_ENABLED=False)
class TimelineListSlimTests(TestCase):
    def setUp(self):
        self.author = _user("slim-author@waseda.jp", username="slimauthor")
        self.viewer = _user("slim-viewer@waseda.jp", username="slimviewer")
        self.blocked = _user("slim-blocked@waseda.jp", username="slimblocked")
        self.post = TimelinePost.objects.create(
            author=self.author, body="list slim target"
        )
        self.client = Client()

    def test_list_omits_comment_bodies_and_keeps_count(self):
        parent = Comment.objects.create(
            timeline_post=self.post, author=self.author, body="parent"
        )
        Comment.objects.create(
            timeline_post=self.post,
            author=self.viewer,
            body="reply",
            parent_comment=parent,
        )
        listed = self.client.get("/api/v1/timeline/?sort=latest")
        matched = next(
            row for row in listed.json()["posts"] if row["id"] == self.post.pk
        )
        self.assertEqual(matched["comments"], [])
        self.assertEqual(matched["comment_count"], 2)
        self.assertEqual(matched["body"], "list slim target")
        self.assertIn("like_count", matched)
        self.assertIn("quote_count", matched)
        self.assertTrue(matched.get("author"))

        detail = self.client.get(f"/api/v1/timeline/{self.post.pk}/")
        comments = detail.json()["post"]["comments"]
        self.assertEqual([row["body"] for row in comments], ["parent", "reply"])
        self.assertEqual(comments[1]["parent_comment_id"], parent.pk)
        self.assertEqual(comments[1]["reply_to"]["id"], parent.pk)
        self.assertEqual(detail.json()["post"]["comment_count"], 2)

        recommended = self.client.get("/api/v1/timeline/")
        rec = next(
            row for row in recommended.json()["posts"] if row["id"] == self.post.pk
        )
        self.assertEqual(rec["comments"], [])
        self.assertEqual(rec["comment_count"], 2)

        profile = self.client.get(f"/api/v1/profile/{self.author.pk}/posts/")
        self.assertEqual(profile.status_code, 200)
        profile_post = next(
            row for row in profile.json()["posts"] if row["id"] == self.post.pk
        )
        self.assertEqual(profile_post["comments"], [])
        self.assertEqual(profile_post["comment_count"], 2)

        search = self.client.get(
            "/api/v1/search/", {"q": "list slim target", "tab": "latest"}
        )
        self.assertEqual(search.status_code, 200)
        search_posts = search.json().get("posts") or []
        if not search_posts:
            search_posts = [
                row["post"]
                for row in search.json().get("results") or []
                if row.get("kind") == "post" and row.get("post")
            ]
        search_post = next(row for row in search_posts if row["id"] == self.post.pk)
        self.assertEqual(search_post["comments"], [])
        self.assertEqual(search_post["comment_count"], 2)

    def test_detail_keeps_tombstone_and_reply_thread(self):
        self.client.force_login(self.author)
        parent = self.client.post(
            f"/api/v1/timeline/{self.post.pk}/comments/",
            data=json.dumps({"body": "keep-parent"}),
            content_type="application/json",
        ).json()["comment"]
        child = self.client.post(
            f"/api/v1/timeline/{self.post.pk}/comments/",
            data=json.dumps(
                {
                    "body": "keep-child",
                    "parent_comment_id": parent["id"],
                }
            ),
            content_type="application/json",
        ).json()["comment"]
        self.client.delete(f"/api/v1/timeline/comments/{parent['id']}/")
        detail = self.client.get(f"/api/v1/timeline/{self.post.pk}/")
        comments = detail.json()["post"]["comments"]
        by_id = {row["id"]: row for row in comments}
        self.assertEqual(by_id[parent["id"]]["body"], TOMBSTONE_BODY)
        self.assertIsNone(by_id[parent["id"]]["author"])
        self.assertEqual(by_id[child["id"]]["parent_comment_id"], parent["id"])
        self.assertTrue(by_id[child["id"]]["reply_to"]["is_unavailable"])

    def test_pagination_and_total_count_unchanged(self):
        TimelinePost.objects.all().delete()
        posts = [
            TimelinePost.objects.create(author=self.author, body=f"page {i}")
            for i in range(TIMELINE_INITIAL_SIZE + 5)
        ]
        first = self.client.get("/api/v1/timeline/?sort=latest")
        data = first.json()
        self.assertEqual(len(data["posts"]), TIMELINE_INITIAL_SIZE)
        self.assertTrue(data["has_more"])
        self.assertEqual(data["total_count"], TIMELINE_INITIAL_SIZE + 5)
        self.assertEqual(data["next_offset"], TIMELINE_INITIAL_SIZE)
        more = self.client.get(
            f"/api/v1/timeline/?sort=latest&offset={data['next_offset']}"
        )
        self.assertEqual(len(more.json()["posts"]), 5)
        self.assertFalse(more.json()["has_more"])
        self.assertEqual(more.json()["total_count"], TIMELINE_INITIAL_SIZE + 5)
        self.assertEqual(
            {p.pk for p in posts},
            {p["id"] for p in data["posts"]} | {p["id"] for p in more.json()["posts"]},
        )

    def test_following_feed_and_private_and_block(self):
        followed = _user("slim-followed@waseda.jp", username="slimfollowed")
        private = _user("slim-private@waseda.jp", username="slimprivate")
        UserProfile.objects.filter(user=private).update(is_private=True)
        Follow.objects.create(follower=self.viewer, following=followed)
        visible = TimelinePost.objects.create(author=followed, body="followed post")
        hidden_private = TimelinePost.objects.create(
            author=private, body="private hidden"
        )
        blocked_author = TimelinePost.objects.create(
            author=self.blocked, body="blocked author"
        )
        block_user(self.viewer, self.blocked)
        self.client.force_login(self.viewer)
        following = self.client.get("/api/v1/timeline/?sort=latest&feed=following")
        ids = {row["id"] for row in following.json()["posts"]}
        self.assertIn(visible.pk, ids)
        self.assertNotIn(self.post.pk, ids)
        all_feed = self.client.get("/api/v1/timeline/?sort=latest")
        all_ids = {row["id"] for row in all_feed.json()["posts"]}
        self.assertNotIn(hidden_private.pk, all_ids)
        self.assertNotIn(blocked_author.pk, all_ids)

    def test_blocked_comment_author_excluded_from_list_count(self):
        Comment.objects.create(
            timeline_post=self.post, author=self.blocked, body="hidden"
        )
        Comment.objects.create(
            timeline_post=self.post, author=self.author, body="visible"
        )
        block_user(self.viewer, self.blocked)
        self.client.force_login(self.viewer)
        listed = self.client.get("/api/v1/timeline/?sort=latest")
        matched = next(
            row for row in listed.json()["posts"] if row["id"] == self.post.pk
        )
        self.assertEqual(matched["comments"], [])
        self.assertEqual(matched["comment_count"], 1)
        detail = self.client.get(f"/api/v1/timeline/{self.post.pk}/")
        self.assertEqual(detail.json()["post"]["comment_count"], 1)
        quoted = self.client.get(f"/api/v1/timeline/{self.post.pk}/quote/")
        self.assertEqual(quoted.status_code, 200)
        self.assertEqual(quoted.json()["quoted_post"]["comments"], [])
        self.assertEqual(quoted.json()["quoted_post"]["comment_count"], 1)

    def test_org_draft_and_unlisted_org_excluded(self):
        owner = _user("slim-org-owner@waseda.jp", username="slimorgowner")
        listed_org = Organization.objects.create(
            name="Slim Listed",
            slug="slim-listed",
            status=Organization.Status.ACTIVE,
            is_listed=True,
        )
        unlisted_org = Organization.objects.create(
            name="Slim Unlisted",
            slug="slim-unlisted",
            status=Organization.Status.ACTIVE,
            is_listed=False,
        )
        add_organization_member(
            listed_org, owner, role=OrganizationMember.Role.OWNER
        )
        add_organization_member(
            unlisted_org, owner, role=OrganizationMember.Role.OWNER
        )
        public_post = TimelinePost.objects.create(
            author=owner,
            organization=listed_org,
            body="org public",
            organization_visibility=TimelinePost.OrganizationVisibility.PUBLIC,
        )
        draft_post = TimelinePost.objects.create(
            author=owner,
            organization=listed_org,
            body="org draft",
            organization_visibility=TimelinePost.OrganizationVisibility.DRAFT,
        )
        unlisted_org_post = TimelinePost.objects.create(
            author=owner,
            organization=unlisted_org,
            body="unlisted org public vis",
            organization_visibility=TimelinePost.OrganizationVisibility.PUBLIC,
        )
        listed = self.client.get("/api/v1/timeline/?sort=latest")
        ids = {row["id"] for row in listed.json()["posts"]}
        self.assertIn(public_post.pk, ids)
        self.assertNotIn(draft_post.pk, ids)
        self.assertNotIn(unlisted_org_post.pk, ids)

    def test_list_query_count_does_not_grow_with_comments(self):
        for i in range(8):
            Comment.objects.create(
                timeline_post=self.post, author=self.author, body=f"c{i}"
            )
        with CaptureQueriesContext(connection) as few:
            self.client.get("/api/v1/timeline/?sort=latest")
        for i in range(40):
            Comment.objects.create(
                timeline_post=self.post, author=self.author, body=f"more{i}"
            )
        with CaptureQueriesContext(connection) as many:
            self.client.get("/api/v1/timeline/?sort=latest")
        self.assertEqual(len(few.captured_queries), len(many.captured_queries))
        comment_table_scans = [
            q["sql"]
            for q in many.captured_queries
            if 'FROM "app_comment"' in q["sql"] or "FROM app_comment" in q["sql"]
        ]
        self.assertEqual(comment_table_scans, [])

    def test_list_serialize_is_cheaper_than_prefetching_comment_bodies(self):
        from django.contrib.auth.models import AnonymousUser
        from django.test import RequestFactory

        from .board_services import (
            annotate_timeline_comment_count,
            build_timeline_posts_queryset,
        )

        extra = []
        for i in range(TIMELINE_INITIAL_SIZE):
            post = TimelinePost.objects.create(
                author=self.author, body=f"perf {i}"
            )
            extra.append(post)
            Comment.objects.bulk_create(
                [
                    Comment(
                        timeline_post=post,
                        author=self.author,
                        body=f"perf-c{i}-{j}",
                    )
                    for j in range(10)
                ]
            )
        factory = RequestFactory()
        request = factory.get("/api/v1/timeline/?sort=latest")
        request.user = AnonymousUser()

        with CaptureQueriesContext(connection) as old:
            old_qs = build_timeline_posts_queryset(
                request, prefetch_comments=True
            ).order_by("-created_at", "-pk")
            old_posts = list(old_qs[:TIMELINE_INITIAL_SIZE])
            old_payloads = [
                serialize_timeline_post(post, None, include_comments=True)
                for post in old_posts
            ]
        with CaptureQueriesContext(connection) as new:
            new_qs = annotate_timeline_comment_count(
                build_timeline_posts_queryset(request, prefetch_comments=False),
                None,
            ).order_by("-created_at", "-pk")
            new_posts = list(new_qs[:TIMELINE_INITIAL_SIZE])
            new_payloads = [
                serialize_timeline_post(post, None, include_comments=False)
                for post in new_posts
            ]

        self.assertEqual(len(old_payloads), TIMELINE_INITIAL_SIZE)
        self.assertEqual(len(new_payloads), TIMELINE_INITIAL_SIZE)
        self.assertTrue(all(row["comments"] for row in old_payloads))
        self.assertTrue(all(row["comments"] == [] for row in new_payloads))
        self.assertEqual(
            [row["comment_count"] for row in old_payloads],
            [row["comment_count"] for row in new_payloads],
        )
        self.assertLess(len(new.captured_queries), len(old.captured_queries))
        self.assertLess(len(new.captured_queries), 80)
        self.assertGreater(len(old.captured_queries), 200)


@override_settings(BROWSE_MODE_GATE_ENABLED=False)
class SearchDiscoverSlimTests(TestCase):
    def setUp(self):
        self.user = _user("disc-user@waseda.jp", username="discuser")
        self.client = Client()
        for i in range(6):
            TimelinePost.objects.create(author=self.user, body=f"discover post {i}")

    def test_discover_keeps_candidate_window_and_serializes_winners_only(self):
        self.assertEqual(DISCOVER_CANDIDATE_LIMIT, 80)
        with patch(
            "app.profile_api_services._discover_timeline_candidates",
            wraps=_discover_timeline_candidates,
        ) as candidates:
            with patch(
                "app.profile_api_services.serialize_timeline_post",
                wraps=serialize_timeline_post,
            ) as mocked:
                response = self.client.get("/api/v1/search/")
        candidates.assert_called()
        for call in candidates.call_args_list:
            limit = call.kwargs.get("limit", DISCOVER_CANDIDATE_LIMIT)
            self.assertEqual(limit, DISCOVER_CANDIDATE_LIMIT)
        self.assertEqual(response.status_code, 200)
        discover = response.json()["discover"]
        post_rows = [row for row in discover["trending"] if row.get("kind") == "post"]
        self.assertTrue(post_rows)
        self.assertLessEqual(len(post_rows), DISCOVER_TRENDING_LIMIT)
        self.assertLessEqual(mocked.call_count, DISCOVER_TRENDING_LIMIT)
        self.assertGreaterEqual(mocked.call_count, 1)
        for row in post_rows:
            self.assertEqual(row["post"]["comments"], [])
            self.assertIn("comment_count", row["post"])
            self.assertTrue(row["post"]["body"])
