"""Phase 7 profile / search JSON API tests."""

from __future__ import annotations

from django.test import Client, TestCase, override_settings

from .models import Product, TimelinePost, User, UserProfile


@override_settings(BROWSE_MODE_GATE_ENABLED=False)
class ProfileSearchApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="prof-api@waseda.jp",
            password="test-pass-12345",
            username="profapi",
        )
        self.other = User.objects.create_user(
            email="prof-other@waseda.jp",
            password="test-pass-12345",
            username="profother",
        )
        UserProfile.objects.update_or_create(
            user=self.user,
            defaults={"name": "プロフ本人", "bio": "hello", "is_timetable_public": True},
        )
        UserProfile.objects.update_or_create(
            user=self.other,
            defaults={"name": "プロフ他人", "is_timetable_public": False},
        )
        TimelinePost.objects.create(author=self.other, body="検索対象の投稿です")
        Product.objects.create(
            seller=self.other,
            name="プロフ出品",
            price=900,
            description="",
            category="未分類",
            handover_campus="waseda",
            status=Product.Status.AVAILABLE,
        )
        self.client = Client()

    def test_profile_detail_posts_products_follow(self):
        detail = self.client.get(f"/api/v1/profile/{self.other.pk}/")
        self.assertEqual(detail.status_code, 200)
        data = detail.json()
        self.assertEqual(data["user"]["display_name"], "プロフ他人")
        self.assertFalse(data["is_own"])
        self.assertFalse(data["can_view_timetable"])

        posts = self.client.get(f"/api/v1/profile/{self.other.pk}/posts/")
        self.assertEqual(posts.status_code, 200)
        self.assertTrue(any("検索対象" in p["body"] for p in posts.json()["posts"]))

        products = self.client.get(f"/api/v1/profile/{self.other.pk}/products/")
        self.assertEqual(products.status_code, 200)
        self.assertTrue(any(p["name"] == "プロフ出品" for p in products.json()["products"]))

        self.client.force_login(self.user)
        follow = self.client.post(f"/api/v1/profile/{self.other.pk}/follow/")
        self.assertEqual(follow.status_code, 200)
        self.assertTrue(follow.json()["is_following"])

        unfollow = self.client.post(f"/api/v1/profile/{self.other.pk}/follow/")
        self.assertFalse(unfollow.json()["is_following"])

        block = self.client.post(f"/api/v1/profile/{self.other.pk}/block/")
        self.assertTrue(block.json()["is_blocked"])

    def test_search_tabs(self):
        posts = self.client.get("/api/v1/search/", {"q": "検索対象", "tab": "all"})
        self.assertEqual(posts.status_code, 200)
        self.assertGreaterEqual(posts.json()["post_count"], 1)

        users = self.client.get("/api/v1/search/", {"q": "プロフ他人", "tab": "users"})
        self.assertEqual(users.status_code, 200)
        self.assertTrue(
            any(u and u.get("display_name") == "プロフ他人" for u in users.json()["users"])
        )

        products = self.client.get("/api/v1/search/", {"q": "プロフ出品", "tab": "products"})
        self.assertEqual(products.status_code, 200)
        pdata = products.json()
        self.assertGreaterEqual(pdata.get("product_count", 0), 1)
        self.assertTrue(
            any(r.get("kind") == "product" for r in pdata.get("results") or [])
        )

        recommended = self.client.get("/api/v1/search/", {"q": "プロフ", "tab": "all"})
        kinds = {r.get("kind") for r in recommended.json().get("results") or []}
        self.assertIn("product", kinds)

    def test_bookmarks_own_only(self):
        denied = self.client.get(f"/api/v1/profile/{self.other.pk}/bookmarks/")
        self.assertEqual(denied.status_code, 403)
        self.client.force_login(self.other)
        ok = self.client.get(f"/api/v1/profile/{self.other.pk}/bookmarks/")
        self.assertEqual(ok.status_code, 200)
        self.assertIn("posts", ok.json())
