"""Phase 7 profile / search JSON API tests."""

from __future__ import annotations

from unittest.mock import patch

from django.test import Client, TestCase, override_settings

from .models import (
    Community,
    CommunityThread,
    Follow,
    FollowRequest,
    Product,
    TimelinePost,
    User,
    UserProfile,
)
from .ugc_services import block_user


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
        community = Community.objects.filter(is_active=True).first()
        if community is None:
            community = Community.objects.create(
                slug="prof-search-board",
                name="検索テスト板",
                description="test",
                category=Community.Category.GENERAL,
                is_active=True,
            )
        CommunityThread.objects.create(
            community=community,
            author=self.other,
            title="検索対象スレ",
            body="コミュニティの話題です",
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

    def test_search_discover_empty_query(self):
        response = self.client.get("/api/v1/search/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["ok"])
        self.assertIn("discover", data)
        discover = data["discover"]
        self.assertIn("trending", discover)
        self.assertIn("communities", discover)
        self.assertIn("products", discover)
        self.assertTrue(isinstance(discover["trending"], list))
        self.assertTrue(isinstance(discover["communities"], list))
        self.assertTrue(isinstance(discover["products"], list))
        self.assertGreaterEqual(len(discover["trending"]), 1)
        self.assertGreaterEqual(len(discover["products"]), 1)
        self.assertGreaterEqual(len(discover["communities"]), 1)
        trending_kinds = {row.get("kind") for row in discover["trending"]}
        self.assertTrue({"post", "product", "thread"}.issubset(trending_kinds))
        # With multiple kinds available, diversified feed should not open with a long same-kind run.
        kinds_seq = [row.get("kind") for row in discover["trending"]]
        if len(kinds_seq) >= 2:
            self.assertNotEqual(kinds_seq[0], kinds_seq[1])
        self.assertTrue(
            all(row.get("kind") == "thread" for row in discover["communities"])
        )

    def test_bookmarks_own_only(self):
        denied = self.client.get(f"/api/v1/profile/{self.other.pk}/bookmarks/")
        self.assertEqual(denied.status_code, 403)
        self.client.force_login(self.other)
        ok = self.client.get(f"/api/v1/profile/{self.other.pk}/bookmarks/")
        self.assertEqual(ok.status_code, 200)
        self.assertIn("posts", ok.json())


@override_settings(BROWSE_MODE_GATE_ENABLED=False)
class FollowListApiTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            email="flist-owner@waseda.jp",
            password="test-pass-12345",
            username="flistowner",
        )
        self.alice = User.objects.create_user(
            email="flist-a@waseda.jp",
            password="test-pass-12345",
            username="flistalice",
        )
        self.bob = User.objects.create_user(
            email="flist-b@waseda.jp",
            password="test-pass-12345",
            username="flistbob",
        )
        self.dana = User.objects.create_user(
            email="flist-d@waseda.jp",
            password="test-pass-12345",
            username="flistdana",
        )
        UserProfile.objects.update_or_create(
            user=self.owner, defaults={"name": "オーナー", "is_private": False}
        )
        for user, name in (
            (self.alice, "アリス"),
            (self.bob, "ボブ"),
            (self.dana, "ダナ"),
        ):
            UserProfile.objects.update_or_create(
                user=user, defaults={"name": name, "is_private": False}
            )
        self.client = Client()

    def _ids(self, payload):
        return [row["id"] for row in payload["users"]]

    def test_own_followers_and_following(self):
        Follow.objects.create(follower=self.alice, following=self.owner)
        Follow.objects.create(follower=self.owner, following=self.dana)
        self.client.force_login(self.owner)
        followers = self.client.get(f"/api/v1/profile/{self.owner.pk}/followers/")
        following = self.client.get(f"/api/v1/profile/{self.owner.pk}/following/")
        self.assertEqual(followers.status_code, 200, followers.content)
        self.assertEqual(following.status_code, 200, following.content)
        self.assertEqual(self._ids(followers.json()), [self.alice.pk])
        self.assertEqual(self._ids(following.json()), [self.dana.pk])
        self.assertEqual(followers.json()["count"], 1)
        self.assertEqual(following.json()["count"], 1)
        self.assertFalse(followers.json()["has_more"])

    def test_public_profile_other_viewer(self):
        Follow.objects.create(follower=self.alice, following=self.owner)
        Follow.objects.create(follower=self.owner, following=self.dana)
        self.client.force_login(self.bob)
        followers = self.client.get(f"/api/v1/profile/{self.owner.pk}/followers/")
        following = self.client.get(f"/api/v1/profile/{self.owner.pk}/following/")
        self.assertEqual(followers.status_code, 200)
        self.assertEqual(following.status_code, 200)
        self.assertEqual(self._ids(followers.json()), [self.alice.pk])
        self.assertEqual(self._ids(following.json()), [self.dana.pk])

    def test_private_followed_and_unapproved(self):
        UserProfile.objects.filter(user=self.owner).update(is_private=True)
        Follow.objects.create(follower=self.alice, following=self.owner)
        Follow.objects.create(follower=self.owner, following=self.dana)
        self.client.force_login(self.alice)
        self.assertEqual(
            self.client.get(f"/api/v1/profile/{self.owner.pk}/followers/").status_code,
            200,
        )
        self.assertEqual(
            self.client.get(f"/api/v1/profile/{self.owner.pk}/following/").status_code,
            200,
        )
        self.client.force_login(self.bob)
        denied_f = self.client.get(f"/api/v1/profile/{self.owner.pk}/followers/")
        denied_g = self.client.get(f"/api/v1/profile/{self.owner.pk}/following/")
        self.assertEqual(denied_f.status_code, 403)
        self.assertEqual(denied_f.json()["error"], "forbidden")
        self.assertEqual(denied_g.status_code, 403)
        shell = self.client.get(f"/api/v1/profile/{self.owner.pk}/")
        self.assertEqual(shell.status_code, 200)
        self.assertFalse(shell.json()["can_view_content"])

    def test_pending_request_not_listed_or_counted(self):
        UserProfile.objects.filter(user=self.owner).update(is_private=True)
        FollowRequest.objects.create(from_user=self.alice, to_user=self.owner)
        self.client.force_login(self.owner)
        followers = self.client.get(f"/api/v1/profile/{self.owner.pk}/followers/")
        self.assertEqual(followers.status_code, 200)
        self.assertEqual(followers.json()["users"], [])
        self.assertEqual(followers.json()["count"], 0)
        shell = self.client.get(f"/api/v1/profile/{self.owner.pk}/")
        self.assertEqual(shell.json()["stats"]["follower_count"], 0)
        self.client.force_login(self.alice)
        denied = self.client.get(f"/api/v1/profile/{self.owner.pk}/followers/")
        self.assertEqual(denied.status_code, 403)

    def test_bilateral_block_hides_third_party_rows_and_counts(self):
        Follow.objects.create(follower=self.alice, following=self.owner)
        Follow.objects.create(follower=self.bob, following=self.owner)
        Follow.objects.create(follower=self.dana, following=self.owner)
        Follow.objects.create(follower=self.owner, following=self.alice)
        Follow.objects.create(follower=self.owner, following=self.bob)
        Follow.objects.create(follower=self.owner, following=self.dana)
        block_user(self.alice, self.bob)

        self.client.force_login(self.alice)
        followers = self.client.get(f"/api/v1/profile/{self.owner.pk}/followers/")
        following = self.client.get(f"/api/v1/profile/{self.owner.pk}/following/")
        self.assertEqual(followers.status_code, 200)
        self.assertCountEqual(
            self._ids(followers.json()), [self.alice.pk, self.dana.pk]
        )
        self.assertEqual(followers.json()["count"], 2)
        self.assertCountEqual(
            self._ids(following.json()), [self.alice.pk, self.dana.pk]
        )
        self.assertEqual(following.json()["count"], 2)
        shell = self.client.get(f"/api/v1/profile/{self.owner.pk}/")
        self.assertEqual(shell.json()["stats"]["follower_count"], 2)
        self.assertEqual(shell.json()["stats"]["following_count"], 2)

        self.client.force_login(self.bob)
        followers_b = self.client.get(f"/api/v1/profile/{self.owner.pk}/followers/")
        following_b = self.client.get(f"/api/v1/profile/{self.owner.pk}/following/")
        self.assertCountEqual(
            self._ids(followers_b.json()), [self.bob.pk, self.dana.pk]
        )
        self.assertCountEqual(
            self._ids(following_b.json()), [self.bob.pk, self.dana.pk]
        )
        self.assertNotIn(self.alice.pk, self._ids(followers_b.json()))
        self.assertNotIn(self.alice.pk, self._ids(following_b.json()))

        self.client.force_login(self.dana)
        visible = self.client.get(f"/api/v1/profile/{self.owner.pk}/followers/")
        self.assertCountEqual(
            self._ids(visible.json()),
            [self.alice.pk, self.bob.pk, self.dana.pk],
        )

    def test_direct_blocked_counterpart_lists_forbidden_shell_unchanged(self):
        block_user(self.alice, self.bob)
        self.client.force_login(self.alice)
        denied = self.client.get(f"/api/v1/profile/{self.bob.pk}/followers/")
        self.assertEqual(denied.status_code, 403)
        shell = self.client.get(f"/api/v1/profile/{self.bob.pk}/")
        self.assertEqual(shell.status_code, 200)
        self.client.force_login(self.bob)
        self.assertEqual(
            self.client.get(f"/api/v1/profile/{self.alice.pk}/following/").status_code,
            403,
        )
        shell_b = self.client.get(f"/api/v1/profile/{self.alice.pk}/")
        self.assertEqual(shell_b.status_code, 200)

    def test_anonymous_rejected_and_no_email(self):
        Follow.objects.create(follower=self.alice, following=self.owner)
        guest = Client()
        res = guest.get(f"/api/v1/profile/{self.owner.pk}/followers/")
        self.assertEqual(res.status_code, 401)
        self.assertEqual(res.json().get("error"), "unauthorized")
        self.client.force_login(self.alice)
        data = self.client.get(f"/api/v1/profile/{self.owner.pk}/followers/").json()
        self.assertEqual(data["users"][0]["id"], self.alice.pk)
        blob = str(data)
        self.assertNotIn("flist-a@waseda.jp", blob)
        self.assertNotIn("email", data["users"][0])

    def test_missing_user_404(self):
        self.client.force_login(self.alice)
        res = self.client.get("/api/v1/profile/999999/followers/")
        self.assertEqual(res.status_code, 404)

    def test_has_more_when_over_cap(self):
        Follow.objects.create(follower=self.alice, following=self.owner)
        Follow.objects.create(follower=self.bob, following=self.owner)
        Follow.objects.create(follower=self.dana, following=self.owner)
        self.client.force_login(self.owner)
        with patch("app.profile_api_services.FOLLOW_LIST_LIMIT", 2):
            res = self.client.get(f"/api/v1/profile/{self.owner.pk}/followers/")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["count"], 3)
        self.assertEqual(len(data["users"]), 2)
        self.assertTrue(data["has_more"])
