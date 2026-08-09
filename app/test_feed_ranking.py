"""Feed ranking: timeline X-style + community BBS-style."""

from __future__ import annotations

from datetime import timedelta

from django.test import Client, TestCase, override_settings
from django.utils import timezone

from .models import Community, CommunityThread, TimelinePost, User, UserProfile


@override_settings(BROWSE_MODE_GATE_ENABLED=False)
class TimelineRankingApiTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.author = User.objects.create_user(
            email="rank-a@waseda.jp",
            password="test-pass-12345",
            username="ranka",
        )
        UserProfile.objects.filter(user=self.author).update(department="商学部")
        now = timezone.now()
        self.hot = TimelinePost.objects.create(
            author=self.author,
            body="hot engagement post",
            like_count=20,
            created_at=now - timedelta(hours=6),
        )
        # created_at is auto_now_add; force via update
        TimelinePost.objects.filter(pk=self.hot.pk).update(
            created_at=now - timedelta(hours=6),
            like_count=20,
        )
        self.fresh = TimelinePost.objects.create(
            author=self.author,
            body="brand new quiet post",
            like_count=0,
        )
        TimelinePost.objects.filter(pk=self.fresh.pk).update(
            created_at=now - timedelta(minutes=5),
            like_count=0,
        )

    def test_default_sort_is_recommended(self):
        response = self.client.get("/api/v1/timeline/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data.get("sort"), "recommended")
        ids = [p["id"] for p in data["posts"]]
        self.assertIn(self.hot.pk, ids)

    def test_latest_is_chronological(self):
        response = self.client.get("/api/v1/timeline/", {"sort": "latest"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data.get("sort"), "latest")
        ids = [p["id"] for p in data["posts"]]
        self.assertEqual(ids[0], self.fresh.pk)

    def test_recommended_prefers_engagement_over_quiet_old(self):
        # Make hot much older but highly liked; quiet mid-age with no engagement
        now = timezone.now()
        quiet = TimelinePost.objects.create(
            author=self.author,
            body="quiet mid age",
            like_count=0,
        )
        TimelinePost.objects.filter(pk=quiet.pk).update(
            created_at=now - timedelta(hours=3),
            like_count=0,
        )
        TimelinePost.objects.filter(pk=self.hot.pk).update(
            created_at=now - timedelta(hours=10),
            like_count=50,
        )
        response = self.client.get("/api/v1/timeline/")
        ids = [p["id"] for p in response.json()["posts"]]
        self.assertLess(ids.index(self.hot.pk), ids.index(quiet.pk))


@override_settings(BROWSE_MODE_GATE_ENABLED=False)
class CommunityRankingApiTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            email="rank-c@waseda.jp",
            password="test-pass-12345",
            username="rankc",
        )
        self.community = Community.objects.filter(is_active=True).first()
        if self.community is None:
            self.community = Community.objects.create(
                slug="rank-test",
                name="ランクテスト板",
                description="test",
                category=Community.Category.GENERAL,
                is_active=True,
            )
        now = timezone.now()
        self.active = CommunityThread.objects.create(
            community=self.community,
            author=self.user,
            title="活発スレ",
            body="lots of talk",
        )
        CommunityThread.objects.filter(pk=self.active.pk).update(
            created_at=now - timedelta(days=2),
            updated_at=now - timedelta(minutes=30),
        )
        # replies_count comes from annotation; create replies
        from .models import CommunityThreadReply

        for i in range(5):
            CommunityThreadReply.objects.create(
                thread=self.active,
                author=self.user,
                body=f"reply {i}",
            )
        self.brand_new = CommunityThread.objects.create(
            community=self.community,
            author=self.user,
            title="できたてスレ",
            body="hello",
        )

    def test_default_community_sort_recommended(self):
        response = self.client.get("/api/v1/communities/threads/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data.get("sort"), "recommended")
        titles = [t["title"] for t in data["threads"]]
        self.assertIn("活発スレ", titles)
        self.assertIn("できたてスレ", titles)

    def test_latest_orders_by_created(self):
        response = self.client.get(
            "/api/v1/communities/threads/",
            {"sort": "latest"},
        )
        data = response.json()
        self.assertEqual(data.get("sort"), "latest")
        self.assertEqual(data["threads"][0]["id"], self.brand_new.pk)
