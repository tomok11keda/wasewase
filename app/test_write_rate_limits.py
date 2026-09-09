"""Write-path rate limit regressions (timeline / chat / report)."""

from __future__ import annotations

from unittest.mock import patch

from django.contrib.messages import get_messages
from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from app.course_services import create_offering
from app.group_chat_services import group_room_link
from app.models import (
    ChatMessage,
    ChatRoom,
    ChatRoomInvitation,
    ChatRoomMembership,
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
    TIMELINE_POST_SCOPE,
    allow_chat_message,
    allow_timeline_comment,
    allow_timeline_like,
    allow_timeline_post,
)
from app.services import build_product_share_timeline_body


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

    def _chat_key(self, user) -> str:
        return f"rl:{CHAT_MESSAGE_SCOPE}:{user.pk}"

    def _make_group(self, owner) -> ChatRoom:
        room = ChatRoom.objects.create(
            kind=ChatRoom.Kind.GROUP,
            name="rl-classic-group",
            created_by=owner,
        )
        ChatRoomMembership.objects.create(
            room=room,
            user=owner,
            role=ChatRoomMembership.Role.OWNER,
        )
        return room

    def test_classic_group_send_succeeds_under_limit(self):
        room = self._make_group(self.user_a)
        before_updated = room.updated_at
        self.client.force_login(self.user_a)
        res = self.client.post(
            reverse("send_group_message", args=[room.pk]),
            {"body": "hello group"},
        )
        self.assertEqual(res.status_code, 302)
        self.assertEqual(res["Location"], group_room_link(room))
        message = ChatMessage.objects.get(room=room)
        self.assertEqual(message.sender, self.user_a)
        self.assertEqual(message.body, "hello group")
        room.refresh_from_db()
        self.assertGreater(room.updated_at, before_updated)
        self.assertEqual(cache.get(self._chat_key(self.user_a)), 1)

    def test_classic_group_send_exhausted_does_not_mutate(self):
        room = self._make_group(self.user_a)
        room.refresh_from_db()
        before_updated = room.updated_at
        self._exhaust(allow_chat_message, self.user_a, CHAT_MESSAGE_LIMIT)
        self.client.force_login(self.user_a)
        res = self.client.post(
            reverse("send_group_message", args=[room.pk]),
            {
                "body": "spam after limit",
                "next": "https://evil.example/phish",
            },
        )
        self.assertEqual(res.status_code, 302)
        msgs = [m.message for m in get_messages(res.wsgi_request)]
        self.assertIn(RATE_LIMIT_USER_MESSAGE, msgs)
        self.assertEqual(res["Location"], group_room_link(room))
        self.assertNotIn("evil.example", res["Location"])
        self.assertFalse(ChatMessage.objects.filter(room=room).exists())
        room.refresh_from_db()
        self.assertEqual(room.updated_at, before_updated)
        self.assertFalse(Notification.objects.exists())

    def test_api_group_then_classic_shares_bucket(self):
        room = self._make_group(self.user_a)
        self.client.force_login(self.user_a)
        api = self.client.post(
            f"/api/v1/dm/groups/{room.pk}/messages/send/",
            data={"body": "api first"},
            content_type="application/json",
        )
        self.assertEqual(api.status_code, 201, api.content)
        self.assertEqual(cache.get(self._chat_key(self.user_a)), 1)
        for _ in range(CHAT_MESSAGE_LIMIT - 1):
            self.assertTrue(allow_chat_message(self.user_a))
        self.assertFalse(allow_chat_message(self.user_a))

        classic = self.client.post(
            reverse("send_group_message", args=[room.pk]),
            {"body": "classic after api"},
        )
        self.assertEqual(classic.status_code, 302)
        self.assertIn(
            RATE_LIMIT_USER_MESSAGE,
            [m.message for m in get_messages(classic.wsgi_request)],
        )
        self.assertEqual(ChatMessage.objects.filter(room=room).count(), 1)
        self.assertEqual(ChatMessage.objects.get(room=room).body, "api first")

    def test_classic_group_then_api_shares_bucket(self):
        room = self._make_group(self.user_a)
        self.client.force_login(self.user_a)
        classic = self.client.post(
            reverse("send_group_message", args=[room.pk]),
            {"body": "classic first"},
        )
        self.assertEqual(classic.status_code, 302)
        self.assertEqual(cache.get(self._chat_key(self.user_a)), 1)
        for _ in range(CHAT_MESSAGE_LIMIT - 1):
            self.assertTrue(allow_chat_message(self.user_a))
        self.assertFalse(allow_chat_message(self.user_a))

        api = self.client.post(
            f"/api/v1/dm/groups/{room.pk}/messages/send/",
            data={"body": "api after classic"},
            content_type="application/json",
        )
        self.assertEqual(api.status_code, 429)
        self.assertEqual(api.json()["error"], "rate_limited")
        self.assertEqual(ChatMessage.objects.filter(room=room).count(), 1)

    def test_classic_group_then_api_dm_shares_chat_scope(self):
        room = self._make_group(self.user_a)
        dm = UserDirectMessageRoom.objects.create(
            user_a=self.user_a, user_b=self.user_b
        )
        self.client.force_login(self.user_a)
        classic = self.client.post(
            reverse("send_group_message", args=[room.pk]),
            {"body": "classic group"},
        )
        self.assertEqual(classic.status_code, 302)
        self.assertEqual(cache.get(self._chat_key(self.user_a)), 1)
        for _ in range(CHAT_MESSAGE_LIMIT - 1):
            self.assertTrue(allow_chat_message(self.user_a))
        self.assertFalse(allow_chat_message(self.user_a))

        api = self.client.post(
            f"/api/v1/dm/rooms/{dm.pk}/messages/send/",
            data={"body": "dm after group"},
            content_type="application/json",
        )
        self.assertEqual(api.status_code, 429)
        self.assertEqual(api.json()["error"], "rate_limited")

    def test_classic_group_pending_invitee_cannot_send_or_consume_budget(self):
        room = self._make_group(self.user_a)
        ChatRoomInvitation.objects.create(
            room=room,
            inviter=self.user_a,
            invitee=self.user_b,
            status=ChatRoomInvitation.Status.PENDING,
        )
        self.client.force_login(self.user_b)
        res = self.client.post(
            reverse("send_group_message", args=[room.pk]),
            {"body": "pending should not send"},
        )
        self.assertEqual(res.status_code, 302)
        self.assertEqual(res["Location"], reverse("user_dm_inbox"))
        self.assertFalse(ChatMessage.objects.filter(room=room).exists())
        self.assertIsNone(cache.get(self._chat_key(self.user_b)))

    def test_classic_group_non_member_does_not_consume_budget(self):
        room = self._make_group(self.user_a)
        self.client.force_login(self.user_b)
        res = self.client.post(
            reverse("send_group_message", args=[room.pk]),
            {"body": "outsider"},
        )
        self.assertEqual(res.status_code, 302)
        self.assertEqual(res["Location"], reverse("user_dm_inbox"))
        self.assertFalse(ChatMessage.objects.filter(room=room).exists())
        self.assertIsNone(cache.get(self._chat_key(self.user_b)))

    def _post_key(self, user) -> str:
        return f"rl:{TIMELINE_POST_SCOPE}:{user.pk}"

    def _make_share_product(self, seller, *, status=Product.Status.AVAILABLE) -> Product:
        return Product.objects.create(
            seller=seller,
            name="rl share book",
            price=800,
            category="本",
            course_name="経済学",
            professor_name="RL教授",
            status=status,
        )

    def _share_posts(self, user):
        return TimelinePost.objects.filter(author=user, body__startswith="【出品シェア】")

    def test_api_flea_share_succeeds_under_limit(self):
        product = self._make_share_product(self.user_a)
        self.client.force_login(self.user_a)
        res = self.client.post(reverse("api_v1_flea_product_share", args=[product.pk]))
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json().get("ok"))
        detail_url = f"http://testserver{reverse('product_detail', args=[product.pk])}"
        post = self._share_posts(self.user_a).get()
        self.assertEqual(post.author, self.user_a)
        self.assertEqual(
            post.body, build_product_share_timeline_body(product, detail_url)
        )
        self.assertEqual(post.course_name, "経済学")
        self.assertEqual(post.professor_name, "RL教授")
        self.assertEqual(cache.get(self._post_key(self.user_a)), 1)

    def test_classic_flea_share_succeeds_under_limit(self):
        product = self._make_share_product(self.user_a)
        self.client.force_login(self.user_a)
        res = self.client.post(
            reverse("share_product_to_timeline", args=[product.pk]),
        )
        self.assertEqual(res.status_code, 302)
        self.assertEqual(
            res["Location"], reverse("product_detail", args=[product.pk])
        )
        detail_url = f"http://testserver{reverse('product_detail', args=[product.pk])}"
        post = self._share_posts(self.user_a).get()
        self.assertEqual(post.author, self.user_a)
        self.assertEqual(
            post.body, build_product_share_timeline_body(product, detail_url)
        )
        self.assertEqual(cache.get(self._post_key(self.user_a)), 1)

    def test_api_flea_share_exhausted_does_not_create_post(self):
        product = self._make_share_product(self.user_a)
        before_status = product.status
        self._exhaust(allow_timeline_post, self.user_a, TIMELINE_POST_LIMIT)
        self.client.force_login(self.user_a)
        res = self.client.post(reverse("api_v1_flea_product_share", args=[product.pk]))
        self.assertEqual(res.status_code, 429)
        body = res.json()
        self.assertEqual(body["error"], "rate_limited")
        self.assertEqual(body["message"], RATE_LIMIT_USER_MESSAGE)
        self.assertFalse(self._share_posts(self.user_a).exists())
        product.refresh_from_db()
        self.assertEqual(product.status, before_status)
        self.assertFalse(Notification.objects.exists())

    def test_classic_flea_share_exhausted_does_not_mutate(self):
        product = self._make_share_product(self.user_a)
        before_status = product.status
        self._exhaust(allow_timeline_post, self.user_a, TIMELINE_POST_LIMIT)
        self.client.force_login(self.user_a)
        res = self.client.post(
            reverse("share_product_to_timeline", args=[product.pk]),
            {"next": "https://evil.example/phish"},
        )
        self._assert_classic_rate_limited(res)
        self.assertEqual(
            res["Location"], reverse("product_detail", args=[product.pk])
        )
        self.assertFalse(self._share_posts(self.user_a).exists())
        product.refresh_from_db()
        self.assertEqual(product.status, before_status)
        self.assertFalse(Notification.objects.exists())

    def test_api_timeline_then_flea_share_shares_bucket(self):
        product = self._make_share_product(self.user_a)
        self.client.force_login(self.user_a)
        api = self.client.post("/api/v1/timeline/", data={"body": "normal first"})
        self.assertEqual(api.status_code, 201, api.content)
        self.assertEqual(cache.get(self._post_key(self.user_a)), 1)
        for _ in range(TIMELINE_POST_LIMIT - 1):
            self.assertTrue(allow_timeline_post(self.user_a))
        self.assertFalse(allow_timeline_post(self.user_a))

        share = self.client.post(
            reverse("api_v1_flea_product_share", args=[product.pk])
        )
        self.assertEqual(share.status_code, 429)
        self.assertEqual(share.json()["error"], "rate_limited")
        self.assertFalse(self._share_posts(self.user_a).exists())
        self.assertEqual(
            TimelinePost.objects.filter(author=self.user_a).count(), 1
        )

    def test_api_flea_share_then_timeline_shares_bucket(self):
        product = self._make_share_product(self.user_a)
        self.client.force_login(self.user_a)
        share = self.client.post(
            reverse("api_v1_flea_product_share", args=[product.pk])
        )
        self.assertEqual(share.status_code, 200)
        self.assertEqual(cache.get(self._post_key(self.user_a)), 1)
        for _ in range(TIMELINE_POST_LIMIT - 1):
            self.assertTrue(allow_timeline_post(self.user_a))
        self.assertFalse(allow_timeline_post(self.user_a))

        api = self.client.post("/api/v1/timeline/", data={"body": "after share"})
        self.assertEqual(api.status_code, 429)
        self.assertEqual(api.json()["error"], "rate_limited")
        self.assertEqual(self._share_posts(self.user_a).count(), 1)
        self.assertEqual(
            TimelinePost.objects.filter(author=self.user_a).count(), 1
        )

        classic = self.client.post(
            reverse("board_compose"),
            {"body": "classic after share"},
        )
        self._assert_classic_rate_limited(classic)
        self.assertEqual(
            TimelinePost.objects.filter(author=self.user_a).count(), 1
        )

    def test_api_flea_share_then_classic_share_shares_bucket(self):
        product = self._make_share_product(self.user_a)
        self.client.force_login(self.user_a)
        api = self.client.post(reverse("api_v1_flea_product_share", args=[product.pk]))
        self.assertEqual(api.status_code, 200)
        self.assertEqual(cache.get(self._post_key(self.user_a)), 1)
        for _ in range(TIMELINE_POST_LIMIT - 1):
            self.assertTrue(allow_timeline_post(self.user_a))
        self.assertFalse(allow_timeline_post(self.user_a))

        classic = self.client.post(
            reverse("share_product_to_timeline", args=[product.pk]),
        )
        self._assert_classic_rate_limited(classic)
        self.assertEqual(
            classic["Location"], reverse("product_detail", args=[product.pk])
        )
        self.assertEqual(self._share_posts(self.user_a).count(), 1)

    def test_api_flea_share_non_seller_does_not_consume_budget(self):
        product = self._make_share_product(self.user_a)
        self.client.force_login(self.user_b)
        res = self.client.post(reverse("api_v1_flea_product_share", args=[product.pk]))
        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.json()["error"], "forbidden")
        self.assertFalse(self._share_posts(self.user_b).exists())
        self.assertIsNone(cache.get(self._post_key(self.user_b)))

    def test_classic_flea_share_non_seller_does_not_consume_budget(self):
        product = self._make_share_product(self.user_a)
        self.client.force_login(self.user_b)
        res = self.client.post(
            reverse("share_product_to_timeline", args=[product.pk]),
        )
        self.assertEqual(res.status_code, 302)
        self.assertEqual(
            res["Location"], reverse("product_detail", args=[product.pk])
        )
        msgs = [m.message for m in get_messages(res.wsgi_request)]
        self.assertIn("自分の出品のみスレッドにシェアできます。", msgs)
        self.assertFalse(self._share_posts(self.user_b).exists())
        self.assertIsNone(cache.get(self._post_key(self.user_b)))

    def test_api_flea_share_sold_product_does_not_consume_budget(self):
        product = self._make_share_product(self.user_a, status=Product.Status.SOLD)
        self.client.force_login(self.user_a)
        res = self.client.post(reverse("api_v1_flea_product_share", args=[product.pk]))
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["error"], "not_available")
        self.assertFalse(self._share_posts(self.user_a).exists())
        self.assertIsNone(cache.get(self._post_key(self.user_a)))

    def test_classic_flea_share_pending_product_does_not_consume_budget(self):
        product = self._make_share_product(self.user_a, status=Product.Status.PENDING)
        self.client.force_login(self.user_a)
        res = self.client.post(
            reverse("share_product_to_timeline", args=[product.pk]),
        )
        self.assertEqual(res.status_code, 302)
        self.assertEqual(
            res["Location"], reverse("product_detail", args=[product.pk])
        )
        msgs = [m.message for m in get_messages(res.wsgi_request)]
        self.assertIn("出品中の商品のみシェアできます。", msgs)
        self.assertFalse(self._share_posts(self.user_a).exists())
        self.assertIsNone(cache.get(self._post_key(self.user_a)))
