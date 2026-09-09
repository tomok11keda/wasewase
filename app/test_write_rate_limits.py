"""Write-path rate limit regressions (timeline / chat / report)."""

from __future__ import annotations

from unittest.mock import patch

from django.contrib.messages import get_messages
from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from app.course_services import create_offering
from app.models import (
    ChatRoom,
    Comment,
    Notification,
    Product,
    TimelineLike,
    TimelinePost,
    User,
    UserDirectMessageRoom,
)
from app.rate_limit_services import (
    CHAT_MESSAGE_LIMIT,
    CHAT_MESSAGE_SCOPE,
    RATE_LIMIT_USER_MESSAGE,
    REPORT_LIMIT,
    TIMELINE_COMMENT_LIMIT,
    TIMELINE_COMMENT_SCOPE,
    TIMELINE_LIKE_LIMIT,
    TIMELINE_LIKE_SCOPE,
    TIMELINE_POST_LIMIT,
    allow_chat_message,
    allow_timeline_comment,
    allow_timeline_like,
    allow_timeline_post,
)


@override_settings(BROWSE_MODE_GATE_ENABLED=False)
class WriteRateLimitTests(TestCase):
    def setUp(self):
        from django.core.cache import cache

        cache.clear()
        self.user_a = User.objects.create_user(
            email="rl-a@waseda.jp", password="pass12345", username="rla"
        )
        self.user_b = User.objects.create_user(
            email="rl-b@waseda.jp", password="pass12345", username="rlb"
        )
        self.client = Client()
        self.post = TimelinePost.objects.create(
            author=self.user_b, body="rate limit target", faculty="法学部"
        )

    def tearDown(self):
        from django.core.cache import cache

        cache.clear()
        super().tearDown()

    def _exhaust(self, allow_fn, user, limit: int) -> None:
        for _ in range(limit):
            self.assertTrue(allow_fn(user))
        self.assertFalse(allow_fn(user))

    def test_timeline_post_burst_returns_429(self):
        self.client.force_login(self.user_a)
        with patch("app.timeline_api_views.allow_timeline_post", return_value=False):
            res = self.client.post(
                "/api/v1/timeline/",
                data={"body": "spam"},
            )
        self.assertEqual(res.status_code, 429)
        body = res.json()
        self.assertEqual(body["error"], "rate_limited")
        self.assertIn("短時間", body.get("message", ""))

    def test_timeline_comment_burst_returns_429(self):
        self.client.force_login(self.user_a)
        with patch(
            "app.timeline_api_views.allow_timeline_comment", return_value=False
        ):
            res = self.client.post(
                f"/api/v1/timeline/{self.post.pk}/comments/",
                data={"body": "spam comment"},
                content_type="application/json",
            )
        self.assertEqual(res.status_code, 429)
        self.assertEqual(res.json()["error"], "rate_limited")

    def test_timeline_like_normal_budget_allows_many(self):
        """いいねは余裕のある limit。数回では制限されない。"""
        self.assertGreaterEqual(TIMELINE_LIKE_LIMIT, 20)
        for _ in range(10):
            self.assertTrue(allow_timeline_like(self.user_a))

    def test_scopes_do_not_interfere(self):
        from django.core.cache import cache

        cache.clear()
        self._exhaust(allow_timeline_post, self.user_a, TIMELINE_POST_LIMIT)
        self.assertFalse(allow_timeline_post(self.user_a))
        self.assertTrue(allow_timeline_like(self.user_a))
        self.assertTrue(allow_chat_message(self.user_a))
        self.assertTrue(allow_timeline_post(self.user_b))

    def test_users_isolated(self):
        from django.core.cache import cache

        cache.clear()
        self._exhaust(allow_chat_message, self.user_a, CHAT_MESSAGE_LIMIT)
        self.assertFalse(allow_chat_message(self.user_a))
        self.assertTrue(allow_chat_message(self.user_b))

    def test_dm_send_rate_limited(self):
        room = UserDirectMessageRoom.objects.create(
            user_a=self.user_a, user_b=self.user_b
        )
        self.client.force_login(self.user_a)
        with patch("app.dm_api_views.allow_chat_message", return_value=False):
            res = self.client.post(
                f"/api/v1/dm/rooms/{room.pk}/messages/send/",
                data='{"body":"hi"}',
                content_type="application/json",
            )
        self.assertEqual(res.status_code, 429)
        self.assertEqual(res.json()["error"], "rate_limited")

    def test_group_and_trade_and_course_share_chat_scope_key(self):
        from django.core.cache import cache

        cache.clear()
        key = f"rl:{CHAT_MESSAGE_SCOPE}:{self.user_a.pk}"
        self.assertTrue(allow_chat_message(self.user_a))
        self.assertEqual(cache.get(key), 1)

    def test_group_send_rate_limited(self):
        room = ChatRoom.objects.create(
            kind=ChatRoom.Kind.GROUP, name="rl-group", created_by=self.user_a
        )
        self.client.force_login(self.user_a)
        with patch("app.dm_api_views.allow_chat_message", return_value=False):
            res = self.client.post(
                f"/api/v1/dm/groups/{room.pk}/messages/send/",
                data='{"body":"hi"}',
                content_type="application/json",
            )
        self.assertEqual(res.status_code, 429)
        self.assertEqual(res.json()["error"], "rate_limited")

    def test_trade_chat_send_rate_limited(self):
        product = Product.objects.create(
            seller=self.user_a,
            name="rl product",
            price=100,
            category="本",
            status=Product.Status.AVAILABLE,
        )
        room = ChatRoom.objects.create(
            product=product,
            buyer=self.user_b,
            deal_status=ChatRoom.DealStatus.NEGOTIATING,
        )
        self.client.force_login(self.user_b)
        with patch("app.flea_api_views.allow_chat_message", return_value=False):
            res = self.client.post(
                f"/api/v1/flea/chats/{room.pk}/messages/send/",
                data='{"body":"hi"}',
                content_type="application/json",
            )
        self.assertEqual(res.status_code, 429)
        self.assertEqual(res.json()["error"], "rate_limited")

    def test_course_talk_send_rate_limited(self):
        self.client.force_login(self.user_a)
        offering, _ = create_offering(
            user=self.user_a,
            title="RL Course",
            instructor="Prof",
            academic_year=2026,
            semester="spring",
            day_of_week=0,
            period=1,
            force_create=True,
        )
        open_res = self.client.post(
            f"/api/v1/courses/offerings/{offering.pk}/talk/",
            data={},
            content_type="application/json",
        )
        self.assertEqual(open_res.status_code, 200, open_res.content)
        room_id = open_res.json()["room"]["id"]
        with patch(
            "app.course_chat_api_views.allow_chat_message", return_value=False
        ):
            res = self.client.post(
                f"/api/v1/courses/talk/{room_id}/messages/send/",
                data='{"body":"hi"}',
                content_type="application/json",
            )
        self.assertEqual(res.status_code, 429)
        self.assertEqual(res.json()["error"], "rate_limited")

    def test_report_burst_returns_429(self):
        self.client.force_login(self.user_a)
        with patch("app.rate_limit_services.allow_report", return_value=False):
            res = self.client.post(
                reverse("submit_report", args=["post", self.post.pk]),
                data={"reason": "spam"},
                HTTP_ACCEPT="application/json",
                HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            )
        self.assertEqual(res.status_code, 429)
        body = res.json()
        self.assertEqual(body["error"], "rate_limited")
        self.assertIn("短時間", body.get("message", ""))

    def test_comment_limit_constant_is_chat_friendlier_than_posts(self):
        self.assertGreater(TIMELINE_COMMENT_LIMIT, TIMELINE_POST_LIMIT)
        self.assertGreaterEqual(CHAT_MESSAGE_LIMIT, 40)
        self.assertGreaterEqual(REPORT_LIMIT, 5)
        self.assertLessEqual(REPORT_LIMIT, 20)

    def _assert_classic_rate_limited(self, response, *, evil_absent=True):
        self.assertEqual(response.status_code, 302)
        msgs = [m.message for m in get_messages(response.wsgi_request)]
        self.assertIn(RATE_LIMIT_USER_MESSAGE, msgs)
        location = response.get("Location", "")
        self.assertTrue(location)
        if evil_absent:
            self.assertNotIn("evil.example", location)

    def _comment_key(self, user) -> str:
        return f"rl:{TIMELINE_COMMENT_SCOPE}:{user.pk}"

    def _like_key(self, user) -> str:
        return f"rl:{TIMELINE_LIKE_SCOPE}:{user.pk}"

    def test_classic_comment_succeeds_under_limit(self):
        self.client.force_login(self.user_a)
        res = self.client.post(
            reverse("board_timeline_comment", args=[self.post.pk]),
            {"body": "ok comment"},
        )
        self.assertEqual(res.status_code, 302)
        comment = Comment.objects.get(timeline_post=self.post)
        self.assertEqual(comment.author, self.user_a)
        self.assertEqual(comment.body, "ok comment")
        self.assertEqual(
            Notification.objects.filter(recipient=self.user_b).count(), 1
        )
        self.assertEqual(cache.get(self._comment_key(self.user_a)), 1)

    def test_classic_comment_exhausted_blocks_comment_and_notifications(self):
        mentioned = User.objects.create_user(
            email="rl-c@waseda.jp", password="pass12345", username="rlc"
        )
        self._exhaust(allow_timeline_comment, self.user_a, TIMELINE_COMMENT_LIMIT)
        self.client.force_login(self.user_a)
        res = self.client.post(
            reverse("board_timeline_comment", args=[self.post.pk]),
            {
                "body": "spam @rlc",
                "next": "https://evil.example/phish",
            },
        )
        self._assert_classic_rate_limited(res)
        self.assertFalse(Comment.objects.filter(timeline_post=self.post).exists())
        self.assertFalse(Notification.objects.filter(recipient=self.user_b).exists())
        self.assertFalse(Notification.objects.filter(recipient=mentioned).exists())

    def test_api_comment_then_classic_shares_bucket(self):
        self.client.force_login(self.user_a)
        api = self.client.post(
            f"/api/v1/timeline/{self.post.pk}/comments/",
            data={"body": "api first"},
            content_type="application/json",
        )
        self.assertEqual(api.status_code, 201)
        self.assertEqual(cache.get(self._comment_key(self.user_a)), 1)
        for _ in range(TIMELINE_COMMENT_LIMIT - 1):
            self.assertTrue(allow_timeline_comment(self.user_a))
        self.assertFalse(allow_timeline_comment(self.user_a))

        classic = self.client.post(
            reverse("board_timeline_comment", args=[self.post.pk]),
            {"body": "classic after api"},
        )
        self._assert_classic_rate_limited(classic)
        self.assertEqual(Comment.objects.filter(timeline_post=self.post).count(), 1)
        self.assertEqual(
            Comment.objects.get(timeline_post=self.post).body, "api first"
        )

    def test_classic_comment_then_api_shares_bucket(self):
        self.client.force_login(self.user_a)
        classic = self.client.post(
            reverse("board_timeline_comment", args=[self.post.pk]),
            {"body": "classic first"},
        )
        self.assertEqual(classic.status_code, 302)
        self.assertEqual(cache.get(self._comment_key(self.user_a)), 1)
        for _ in range(TIMELINE_COMMENT_LIMIT - 1):
            self.assertTrue(allow_timeline_comment(self.user_a))
        self.assertFalse(allow_timeline_comment(self.user_a))

        api = self.client.post(
            f"/api/v1/timeline/{self.post.pk}/comments/",
            data={"body": "api after classic"},
            content_type="application/json",
        )
        self.assertEqual(api.status_code, 429)
        self.assertEqual(api.json()["error"], "rate_limited")
        self.assertEqual(Comment.objects.filter(timeline_post=self.post).count(), 1)

    def test_classic_like_succeeds_under_limit(self):
        self.client.force_login(self.user_a)
        res = self.client.post(reverse("board_timeline_like", args=[self.post.pk]))
        self.assertEqual(res.status_code, 302)
        self.assertTrue(
            TimelineLike.objects.filter(
                timeline_post=self.post, user=self.user_a
            ).exists()
        )
        self.post.refresh_from_db()
        self.assertEqual(self.post.like_count, 1)
        self.assertEqual(
            Notification.objects.filter(recipient=self.user_b).count(), 1
        )
        self.assertEqual(cache.get(self._like_key(self.user_a)), 1)

    def test_classic_like_exhausted_does_not_mutate(self):
        self._exhaust(allow_timeline_like, self.user_a, TIMELINE_LIKE_LIMIT)
        self.client.force_login(self.user_a)
        res = self.client.post(
            reverse("board_timeline_like", args=[self.post.pk]),
            {"next": "https://evil.example/phish"},
        )
        self._assert_classic_rate_limited(res)
        self.assertFalse(
            TimelineLike.objects.filter(
                timeline_post=self.post, user=self.user_a
            ).exists()
        )
        self.post.refresh_from_db()
        self.assertEqual(self.post.like_count, 0)
        self.assertFalse(Notification.objects.filter(recipient=self.user_b).exists())

    def test_classic_unlike_blocked_when_exhausted(self):
        TimelineLike.objects.create(timeline_post=self.post, user=self.user_a)
        self.post.like_count = 1
        self.post.save(update_fields=["like_count"])
        self._exhaust(allow_timeline_like, self.user_a, TIMELINE_LIKE_LIMIT)
        self.client.force_login(self.user_a)
        res = self.client.post(reverse("board_timeline_like", args=[self.post.pk]))
        self._assert_classic_rate_limited(res)
        self.assertTrue(
            TimelineLike.objects.filter(
                timeline_post=self.post, user=self.user_a
            ).exists()
        )
        self.post.refresh_from_db()
        self.assertEqual(self.post.like_count, 1)

    def test_api_like_then_classic_shares_bucket(self):
        self.client.force_login(self.user_a)
        api = self.client.post(f"/api/v1/timeline/{self.post.pk}/like/")
        self.assertEqual(api.status_code, 200)
        self.assertTrue(api.json()["liked"])
        self.assertEqual(cache.get(self._like_key(self.user_a)), 1)
        for _ in range(TIMELINE_LIKE_LIMIT - 1):
            self.assertTrue(allow_timeline_like(self.user_a))
        self.assertFalse(allow_timeline_like(self.user_a))

        classic = self.client.post(reverse("board_timeline_like", args=[self.post.pk]))
        self._assert_classic_rate_limited(classic)
        self.assertTrue(
            TimelineLike.objects.filter(
                timeline_post=self.post, user=self.user_a
            ).exists()
        )
        self.post.refresh_from_db()
        self.assertEqual(self.post.like_count, 1)

    def test_classic_like_then_api_shares_bucket(self):
        self.client.force_login(self.user_a)
        classic = self.client.post(reverse("board_timeline_like", args=[self.post.pk]))
        self.assertEqual(classic.status_code, 302)
        self.assertEqual(cache.get(self._like_key(self.user_a)), 1)
        for _ in range(TIMELINE_LIKE_LIMIT - 1):
            self.assertTrue(allow_timeline_like(self.user_a))
        self.assertFalse(allow_timeline_like(self.user_a))

        api = self.client.post(f"/api/v1/timeline/{self.post.pk}/like/")
        self.assertEqual(api.status_code, 429)
        self.assertEqual(api.json()["error"], "rate_limited")
        self.assertTrue(
            TimelineLike.objects.filter(
                timeline_post=self.post, user=self.user_a
            ).exists()
        )
