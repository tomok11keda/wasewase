"""Phase 3 timeline JSON API — reuses board/bookmark services."""

from __future__ import annotations

import json

from django.test import Client, TestCase, override_settings
from django.urls import reverse

from .models import Product, TimelineLike, TimelinePost, User, UserBlock, UserProfile


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
        comment_payload = comment.json()["comment"]
        self.assertEqual(comment_payload["body"], "nice")
        self.assertIn("author", comment_payload)
        self.assertEqual(comment_payload["author"]["id"], self.user.pk)
        self.assertIn("avatar_url", comment_payload["author"])
        self.assertIn("initial", comment_payload["author"])
        self.assertTrue(comment_payload["author"]["initial"])

        listed = self.client.get("/api/v1/timeline/")
        matched = next(
            p for p in listed.json()["posts"] if p["id"] == created
        )
        listed_comment = matched["comments"][0]
        self.assertIn("avatar_url", listed_comment["author"])
        self.assertIn("initial", listed_comment["author"])

        deleted = self.client.delete(f"/api/v1/timeline/{created}/")
        self.assertEqual(deleted.status_code, 200)
        self.assertFalse(TimelinePost.objects.filter(pk=created).exists())

    def test_cannot_delete_others_post(self):
        self.client.force_login(self.user)
        response = self.client.delete(f"/api/v1/timeline/{self.post.pk}/")
        self.assertEqual(response.status_code, 403)

    def test_get_single_post_matches_feed_serializer(self):
        listed = self.client.get("/api/v1/timeline/")
        listed_post = next(
            p for p in listed.json()["posts"] if p["id"] == self.post.pk
        )
        detail = self.client.get(f"/api/v1/timeline/{self.post.pk}/")
        self.assertEqual(detail.status_code, 200)
        data = detail.json()
        self.assertTrue(data["ok"])
        post = data["post"]
        self.assertEqual(post["id"], self.post.pk)
        self.assertEqual(post["body"], "hello timeline api")
        self.assertEqual(post["comments"], listed_post["comments"])
        self.assertIn("user_has_liked", post)
        self.assertIn("user_has_bookmarked", post)
        self.assertFalse(post["user_has_liked"])

    def test_get_single_post_includes_like_state(self):
        self.client.force_login(self.user)
        self.client.post(f"/api/v1/timeline/{self.post.pk}/like/")
        detail = self.client.get(f"/api/v1/timeline/{self.post.pk}/")
        self.assertTrue(detail.json()["post"]["user_has_liked"])
        self.assertEqual(detail.json()["post"]["like_count"], 1)

    def test_get_single_post_missing_is_not_found(self):
        response = self.client.get("/api/v1/timeline/999999/")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"], "not_found")

    def test_get_removed_post_is_not_found(self):
        self.post.is_removed = True
        self.post.save(update_fields=["is_removed"])
        response = self.client.get(f"/api/v1/timeline/{self.post.pk}/")
        self.assertEqual(response.status_code, 404)

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


@override_settings(BROWSE_MODE_GATE_ENABLED=False)
class TimelineLikerApiTests(TestCase):
    def setUp(self):
        self.author = User.objects.create_user(
            email="liker-author@waseda.jp",
            password="test-pass-12345",
            username="liker_author",
        )
        self.viewer = User.objects.create_user(
            email="liker-viewer@waseda.jp",
            password="test-pass-12345",
            username="liker_viewer",
        )
        self.alice = User.objects.create_user(
            email="liker-alice@waseda.jp",
            password="test-pass-12345",
            username="liker_alice",
        )
        self.bob = User.objects.create_user(
            email="liker-bob@waseda.jp",
            password="test-pass-12345",
            username="liker_bob",
        )
        UserProfile.objects.create(user=self.author, name="投稿者")
        UserProfile.objects.create(user=self.viewer, name="閲覧者")
        UserProfile.objects.create(user=self.alice, name="アリス表示")
        UserProfile.objects.create(user=self.bob, name="")
        self.post = TimelinePost.objects.create(
            author=self.author,
            body="liker list target",
            like_count=0,
        )
        self.client = Client()

    def _likers_url(self, pk=None):
        return f"/api/v1/timeline/{pk or self.post.pk}/likers/"

    def test_anonymous_cannot_list_likers(self):
        response = self.client.get(self._likers_url())
        self.assertIn(response.status_code, (302, 401, 403))

    def test_empty_likers(self):
        self.client.force_login(self.viewer)
        response = self.client.get(self._likers_url())
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["users"], [])
        self.assertEqual(data["count"], 0)
        self.assertFalse(data["has_more"])

    def test_lists_likers_with_display_name_and_username_fallback(self):
        TimelineLike.objects.create(timeline_post=self.post, user=self.alice)
        TimelineLike.objects.create(timeline_post=self.post, user=self.bob)
        self.post.like_count = 2
        self.post.save(update_fields=["like_count"])
        self.client.force_login(self.viewer)
        response = self.client.get(self._likers_url())
        self.assertEqual(response.status_code, 200)
        data = response.json()
        by_id = {u["id"]: u for u in data["users"]}
        self.assertEqual(set(by_id), {self.alice.pk, self.bob.pk})
        self.assertEqual(by_id[self.alice.pk]["display_name"], "アリス表示")
        self.assertEqual(by_id[self.alice.pk]["username"], "liker_alice")
        self.assertEqual(by_id[self.bob.pk]["display_name"], "liker_bob")
        self.assertEqual(by_id[self.bob.pk]["username"], "liker_bob")
        blob = json.dumps(data)
        self.assertNotIn("waseda.jp", blob)
        self.assertNotIn("email", data["users"][0])
        self.assertNotIn("is_private", data["users"][0])
        for user in data["users"]:
            self.assertEqual(
                set(user),
                {"id", "username", "display_name", "avatar_url", "initial"},
            )

    def test_non_liker_is_absent(self):
        TimelineLike.objects.create(timeline_post=self.post, user=self.alice)
        self.client.force_login(self.viewer)
        ids = [u["id"] for u in self.client.get(self._likers_url()).json()["users"]]
        self.assertIn(self.alice.pk, ids)
        self.assertNotIn(self.viewer.pk, ids)
        self.assertNotIn(self.author.pk, ids)

    def test_unlike_removes_liker(self):
        self.client.force_login(self.alice)
        self.client.post(f"/api/v1/timeline/{self.post.pk}/like/")
        self.client.force_login(self.viewer)
        ids = [u["id"] for u in self.client.get(self._likers_url()).json()["users"]]
        self.assertEqual(ids, [self.alice.pk])
        self.client.force_login(self.alice)
        self.client.post(f"/api/v1/timeline/{self.post.pk}/like/")
        self.client.force_login(self.viewer)
        data = self.client.get(self._likers_url()).json()
        self.assertEqual(data["users"], [])
        self.assertEqual(data["count"], 0)

    def test_duplicate_like_does_not_duplicate_rows(self):
        TimelineLike.objects.get_or_create(
            timeline_post=self.post, user=self.alice
        )
        TimelineLike.objects.get_or_create(
            timeline_post=self.post, user=self.alice
        )
        self.assertEqual(
            TimelineLike.objects.filter(
                timeline_post=self.post, user=self.alice
            ).count(),
            1,
        )
        self.client.force_login(self.viewer)
        ids = [u["id"] for u in self.client.get(self._likers_url()).json()["users"]]
        self.assertEqual(ids, [self.alice.pk])

    def test_removed_post_is_not_found(self):
        TimelineLike.objects.create(timeline_post=self.post, user=self.alice)
        self.post.is_removed = True
        self.post.save(update_fields=["is_removed"])
        self.client.force_login(self.viewer)
        response = self.client.get(self._likers_url())
        self.assertEqual(response.status_code, 404)
        self.assertNotIn("アリス表示", response.content.decode())

    def test_missing_post_is_not_found(self):
        self.client.force_login(self.viewer)
        response = self.client.get(self._likers_url(999999))
        self.assertEqual(response.status_code, 404)

    def test_blocked_liker_is_hidden(self):
        TimelineLike.objects.create(timeline_post=self.post, user=self.alice)
        UserBlock.objects.create(blocker=self.viewer, blocked=self.alice)
        self.client.force_login(self.viewer)
        ids = [u["id"] for u in self.client.get(self._likers_url()).json()["users"]]
        self.assertNotIn(self.alice.pk, ids)


@override_settings(BROWSE_MODE_GATE_ENABLED=False)
class TimelineSharedProductApiTests(TestCase):
    def setUp(self):
        from django.core.cache import cache

        cache.clear()
        self.seller = User.objects.create_user(
            email="flea-share@waseda.jp",
            password="test-pass-12345",
        )
        self.client = Client()

    def _product(self, **kwargs):
        defaults = {
            "seller": self.seller,
            "name": "選択英語リーディング教科書",
            "price": 3500,
            "category": "未分類",
            "status": Product.Status.AVAILABLE,
        }
        defaults.update(kwargs)
        return Product.objects.create(**defaults)

    def _share(self, product=None, **kwargs):
        product = product or self._product(**kwargs)
        self.client.force_login(self.seller)
        res = self.client.post(f"/api/v1/flea/products/{product.pk}/share/")
        self.assertEqual(res.status_code, 200)
        product.refresh_from_db()
        return product

    def _payload_for(self, post_id):
        res = self.client.get(f"/api/v1/timeline/{post_id}/")
        self.assertEqual(res.status_code, 200)
        return res.json()["post"]

    def test_normal_post_has_null_shared_product(self):
        post = TimelinePost.objects.create(author=self.seller, body="普通の投稿")
        self.client.force_login(self.seller)
        payload = self._payload_for(post.pk)
        self.assertIsNone(payload["shared_product"])

    def test_new_share_has_short_body_and_card_metadata(self):
        product = self._share()
        post = product.timeline_share_post
        payload = self._payload_for(post.pk)
        self.assertEqual(payload["body"], "フリマに出品しました！")
        self.assertNotIn("http", payload["body"])
        shared = payload["shared_product"]
        self.assertEqual(shared["id"], product.pk)
        self.assertEqual(shared["name"], product.name)
        self.assertEqual(shared["price"], 3500)
        self.assertEqual(shared["status"], Product.Status.AVAILABLE)
        self.assertFalse(shared["is_sold"])
        self.assertFalse(shared["is_pending"])
        self.assertIn("image_url", shared)
        self.assertEqual(set(shared.keys()), {
            "id",
            "name",
            "price",
            "image_url",
            "status",
            "is_sold",
            "is_pending",
        })

    def test_legacy_unrelated_post_has_no_card(self):
        TimelinePost.objects.create(
            author=self.seller,
            body="【出品シェア】古い本 が出品されました！詳細はこちら：https://wasewase.onrender.com/product/1/",
        )
        self.client.force_login(self.seller)
        feed = self.client.get("/api/v1/timeline/?sort=latest")
        self.assertEqual(feed.status_code, 200)
        matched = next(
            p for p in feed.json()["posts"] if p["body"].startswith("【出品シェア】")
        )
        self.assertIsNone(matched["shared_product"])

    def test_pending_and_sold_status_metadata(self):
        pending = self._share(name="取引中の本", price=100)
        pending.status = Product.Status.PENDING
        pending.save(update_fields=["status"])
        sold = self._share(name="売り切れ本", price=200)
        sold.status = Product.Status.SOLD
        sold.save(update_fields=["status"])
        pending_payload = self._payload_for(pending.timeline_share_post_id)
        sold_payload = self._payload_for(sold.timeline_share_post_id)
        self.assertTrue(pending_payload["shared_product"]["is_pending"])
        self.assertEqual(
            pending_payload["shared_product"]["status"], Product.Status.PENDING
        )
        self.assertTrue(sold_payload["shared_product"]["is_sold"])
        self.assertEqual(sold_payload["shared_product"]["status"], Product.Status.SOLD)

    def test_removed_product_hides_card(self):
        product = self._share()
        post_id = product.timeline_share_post_id
        product.is_removed = True
        product.save(update_fields=["is_removed"])
        payload = self._payload_for(post_id)
        self.assertEqual(payload["body"], "フリマに出品しました！")
        self.assertIsNone(payload["shared_product"])

    def test_deleted_product_leaves_post_and_null_card(self):
        product = self._share()
        post_id = product.timeline_share_post_id
        product.delete()
        self.assertTrue(TimelinePost.objects.filter(pk=post_id).exists())
        feed = self.client.get("/api/v1/timeline/?sort=latest")
        self.assertEqual(feed.status_code, 200)
        payload = self._payload_for(post_id)
        self.assertIsNone(payload["shared_product"])

    def test_feed_and_profile_include_shared_product(self):
        product = self._share()
        self.client.force_login(self.seller)
        feed = self.client.get("/api/v1/timeline/?sort=latest")
        self.assertEqual(feed.status_code, 200)
        feed_post = next(
            p for p in feed.json()["posts"] if p["id"] == product.timeline_share_post_id
        )
        self.assertEqual(feed_post["shared_product"]["id"], product.pk)
        profile = self.client.get(f"/api/v1/profile/{self.seller.pk}/posts/")
        self.assertEqual(profile.status_code, 200)
        profile_post = next(
            p
            for p in profile.json()["posts"]
            if p["id"] == product.timeline_share_post_id
        )
        self.assertEqual(profile_post["shared_product"]["id"], product.pk)

    def test_bookmark_queryset_selects_shared_product(self):
        from .bookmark_services import _timeline_posts_queryset_base
        from .timeline_api_services import serialize_timeline_post

        product = self._share()
        post = _timeline_posts_queryset_base().get(pk=product.timeline_share_post_id)
        payload = serialize_timeline_post(post, self.seller)
        self.assertEqual(payload["shared_product"]["id"], product.pk)

    def test_shared_product_does_not_add_n_plus_one(self):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        self.client.force_login(self.seller)
        for idx in range(5):
            TimelinePost.objects.create(author=self.seller, body=f"plain {idx}")
        with CaptureQueriesContext(connection) as plain:
            self.client.get("/api/v1/timeline/?sort=latest")
        TimelinePost.objects.filter(author=self.seller).delete()
        for idx in range(5):
            self._share(name=f"item-{idx}", price=10 + idx)
        with CaptureQueriesContext(connection) as shared:
            self.client.get("/api/v1/timeline/?sort=latest")
        self.assertLessEqual(
            len(shared),
            len(plain) + 4,
            f"shared_product N+1: plain={len(plain)} shared={len(shared)}",
        )
