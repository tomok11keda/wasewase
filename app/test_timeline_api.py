"""Phase 3 timeline JSON API — reuses board/bookmark services."""

from __future__ import annotations

import json

from django.test import Client, TestCase, override_settings
from django.urls import reverse

from .models import TimelineLike, TimelinePost, User


@override_settings(BROWSE_MODE_GATE_ENABLED=False)
class TimelineApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="tl-api@waseda.jp",
            password="test-pass-12345",
        )
        self.other = User.objects.create_user(
            email="tl-other@waseda.jp",
            password="test-pass-12345",
        )
        self.post = TimelinePost.objects.create(
            author=self.other,
            body="hello timeline api",
            like_count=0,
        )
        self.client = Client()

    def test_list_anonymous(self):
        response = self.client.get("/api/v1/timeline/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("posts", data)
        self.assertTrue(any(p["id"] == self.post.pk for p in data["posts"]))
        self.assertIn("ads", data)

    def test_create_requires_login(self):
        response = self.client.post(
            "/api/v1/timeline/",
            {"body": "nope"},
        )
        self.assertIn(response.status_code, (302, 401, 403))

    def test_create_and_like(self):
        self.client.force_login(self.user)
        response = self.client.post(
            "/api/v1/timeline/",
            {"body": "composed via api"},
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertTrue(data["ok"])
        post_id = data["post"]["id"]

        like = self.client.post(f"/api/v1/timeline/{post_id}/like/")
        self.assertEqual(like.status_code, 200)
        self.assertTrue(like.json()["liked"])
        self.assertEqual(like.json()["like_count"], 1)
        self.assertTrue(
            TimelineLike.objects.filter(
                timeline_post_id=post_id, user=self.user
            ).exists()
        )

        unlike = self.client.post(f"/api/v1/timeline/{post_id}/like/")
        self.assertFalse(unlike.json()["liked"])

    def test_comment_and_delete_own_post(self):
        self.client.force_login(self.user)
        created = self.client.post(
            "/api/v1/timeline/",
            {"body": "to comment"},
        ).json()["post"]["id"]

        comment = self.client.post(
            f"/api/v1/timeline/{created}/comments/",
            data=json.dumps({"body": "nice"}),
            content_type="application/json",
        )
        self.assertEqual(comment.status_code, 201)
        self.assertEqual(comment.json()["comment"]["body"], "nice")

        deleted = self.client.delete(f"/api/v1/timeline/{created}/")
        self.assertEqual(deleted.status_code, 200)
        self.assertFalse(TimelinePost.objects.filter(pk=created).exists())

    def test_cannot_delete_others_post(self):
        self.client.force_login(self.user)
        response = self.client.delete(f"/api/v1/timeline/{self.post.pk}/")
        self.assertEqual(response.status_code, 403)

    def test_quote_endpoint(self):
        self.client.force_login(self.user)
        response = self.client.get(
            reverse("api_v1_timeline_quote", kwargs={"pk": self.post.pk})
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        self.assertEqual(response.json()["quoted_post"]["id"], self.post.pk)

    def test_following_empty_when_anonymous(self):
        response = self.client.get("/api/v1/timeline/?feed=following")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["posts"], [])
        self.assertTrue(data["feed_following_unauthenticated"])

    def test_list_includes_view_count_zero(self):
        response = self.client.get("/api/v1/timeline/")
        self.assertEqual(response.status_code, 200)
        matched = next(p for p in response.json()["posts"] if p["id"] == self.post.pk)
        self.assertEqual(matched["view_count"], 0)

    def test_impressions_batch_increments_once_per_id(self):
        other = TimelinePost.objects.create(
            author=self.other,
            body="second post",
            like_count=0,
            view_count=0,
        )
        response = self.client.post(
            "/api/v1/timeline/impressions/",
            data=json.dumps(
                {"post_ids": [self.post.pk, self.post.pk, other.pk, 999999]}
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["counts"][str(self.post.pk)], 1)
        self.assertEqual(data["counts"][str(other.pk)], 1)
        self.assertNotIn("999999", data["counts"])

        self.post.refresh_from_db()
        other.refresh_from_db()
        self.assertEqual(self.post.view_count, 1)
        self.assertEqual(other.view_count, 1)

        # Second request increments again (server has no session dedupe)
        again = self.client.post(
            "/api/v1/timeline/impressions/",
            data=json.dumps({"post_ids": [self.post.pk]}),
            content_type="application/json",
        )
        self.assertEqual(again.status_code, 200)
        self.post.refresh_from_db()
        self.assertEqual(self.post.view_count, 2)

    def test_impressions_skips_removed_posts(self):
        self.post.is_removed = True
        self.post.save(update_fields=["is_removed"])
        response = self.client.post(
            "/api/v1/timeline/impressions/",
            data=json.dumps({"post_ids": [self.post.pk]}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["counts"], {})
        self.post.refresh_from_db()
        self.assertEqual(self.post.view_count, 0)
