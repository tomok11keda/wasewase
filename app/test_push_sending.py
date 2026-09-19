"""Phase 2: production-safe FCM sending, privacy copy, and notification dispatch."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from firebase_admin import messaging

from .board_services import notify_timeline_post_author, timeline_post_link
from .community_services import notify_community_reply, seed_communities
from .follow_services import _notify_follow_request, _notify_followed
from .mention_services import notify_mentions
from .models import (
    Community,
    CommunityThread,
    CommunityThreadReply,
    DevicePushToken,
    Follow,
    Notification,
    Product,
    TimelinePost,
    UserProfile,
)
from .notification_services import (
    build_privacy_safe_push_body,
    create_notification,
    push_payload_link,
)
from .push_services import (
    get_firebase_app,
    notify_user_push,
    reset_firebase_app_for_tests,
    send_push_to_user,
)
from .services import notify_seller


User = get_user_model()
SECRET_DM = "秘密のメッセージ123"
SECRET_COMMENT = "秘密のコメント本文XYZ"
SECRET_SHARE = "campus-only share body"


def _user(email: str, username: str, display_name: str | None = None):
    user = User.objects.create_user(
        email=email, password="test-pass-12345", username=username
    )
    if display_name:
        UserProfile.objects.update_or_create(
            user=user, defaults={"name": display_name}
        )
    return user


class PushSendingIsolationTests(TestCase):
    def setUp(self):
        reset_firebase_app_for_tests()
        self.author = _user("push-author@waseda.jp", "pushauthor", "投稿者")
        self.actor = _user("push-actor@waseda.jp", "pushactor", "表示名太郎")
        self.post = TimelinePost.objects.create(author=self.author, body="hello")

    def tearDown(self):
        reset_firebase_app_for_tests()

    @override_settings(
        PUSH_NOTIFICATIONS_ENABLED=False,
        FIREBASE_CREDENTIALS_JSON="",
        FIREBASE_CREDENTIALS_PATH="",
    )
    def test_disabled_push_is_noop_without_firebase(self):
        DevicePushToken.objects.create(
            user=self.author, token="fcm-token-disabled", platform="ios"
        )
        with patch("app.push_services.get_firebase_app") as mock_app:
            sent = send_push_to_user(
                self.author, title="わせわせ", body="hi", link="/app/"
            )
            self.assertEqual(sent, 0)
            mock_app.assert_not_called()

    @override_settings(PUSH_NOTIFICATIONS_ENABLED=True)
    def test_no_tokens_is_noop(self):
        with patch("app.push_services.get_firebase_app") as mock_app:
            sent = send_push_to_user(
                self.author, title="わせわせ", body="hi", link="/app/"
            )
            self.assertEqual(sent, 0)
            mock_app.assert_not_called()

    @override_settings(
        PUSH_NOTIFICATIONS_ENABLED=True,
        FIREBASE_CREDENTIALS_JSON="{not-json",
        FIREBASE_CREDENTIALS_PATH="",
    )
    def test_invalid_credentials_do_not_crash_startup_or_send(self):
        DevicePushToken.objects.create(
            user=self.author, token="fcm-token-badcred", platform="ios"
        )
        self.assertIsNone(get_firebase_app())
        sent = send_push_to_user(self.author, title="わせわせ", body="hi")
        self.assertEqual(sent, 0)

    @override_settings(PUSH_NOTIFICATIONS_ENABLED=True)
    @patch("app.push_services.notify_user_push", side_effect=RuntimeError("fcm down"))
    def test_create_notification_survives_push_exception(self, _mock_push):
        note = create_notification(
            recipient=self.author,
            message="いいねされました",
            link="/app/posts/1",
            actor=self.actor,
            push_kind="like",
        )
        self.assertTrue(Notification.objects.filter(pk=note.pk).exists())
        self.assertEqual(note.message, "いいねされました")

    @override_settings(PUSH_NOTIFICATIONS_ENABLED=True)
    @patch("app.push_services.notify_user_push")
    def test_like_dispatches_privacy_safe_push_with_exact_post_link(self, mock_push):
        mock_push.return_value = 0
        notify_timeline_post_author(
            self.post,
            self.actor,
            "「pushactorさんがあなたの投稿にいいねしました」",
        )
        mock_push.assert_called_once()
        _args, kwargs = mock_push.call_args
        self.assertEqual(
            kwargs["body"],
            "「表示名太郎さんがあなたの投稿にいいねしました」",
        )
        self.assertEqual(kwargs["title"], "わせわせ")
        self.assertEqual(kwargs["link"], f"/app/posts/{self.post.pk}")
        self.assertIsInstance(kwargs["notification_id"], int)
        self.assertEqual(kwargs["notification_type"], "like")

    @override_settings(PUSH_NOTIFICATIONS_ENABLED=True)
    @patch("app.push_services.notify_user_push")
    def test_follow_and_follow_request_privacy_copy(self, mock_push):
        mock_push.return_value = 0
        _notify_followed(self.actor, self.author)
        _notify_follow_request(self.actor, self.author)
        bodies = [call.kwargs["body"] for call in mock_push.call_args_list]
        self.assertEqual(
            bodies[0], "「表示名太郎さんがあなたをフォローしました」"
        )
        self.assertEqual(
            bodies[1], "「表示名太郎さんからフォローリクエストが届きました」"
        )

    @override_settings(PUSH_NOTIFICATIONS_ENABLED=True)
    @patch("app.push_services.notify_user_push")
    def test_self_like_does_not_notify_or_push(self, mock_push):
        notify_timeline_post_author(
            self.post,
            self.author,
            "「投稿者さんがあなたの投稿にいいねしました」",
        )
        self.assertFalse(Notification.objects.filter(recipient=self.author).exists())
        mock_push.assert_not_called()

    @override_settings(PUSH_NOTIFICATIONS_ENABLED=True)
    @patch("app.push_services.notify_user_push")
    def test_comment_body_not_in_push(self, mock_push):
        mock_push.return_value = 0
        create_notification(
            recipient=self.author,
            message=f"コメント: {SECRET_COMMENT}",
            link=timeline_post_link(self.post),
            actor=self.actor,
            push_kind="comment",
        )
        _args, kwargs = mock_push.call_args
        self.assertNotIn(SECRET_COMMENT, kwargs["body"])
        self.assertIn("コメントしました", kwargs["body"])
        self.assertEqual(kwargs["link"], f"/app/posts/{self.post.pk}")

    @override_settings(PUSH_NOTIFICATIONS_ENABLED=True)
    @patch("app.push_services.notify_user_push")
    def test_mention_actor_and_link(self, mock_push):
        mock_push.return_value = 0
        notify_mentions(
            body=f"hey @{self.author.username} {SECRET_COMMENT}",
            actor=self.actor,
            link=timeline_post_link(self.post),
        )
        mock_push.assert_called_once()
        _args, kwargs = mock_push.call_args
        self.assertNotIn(SECRET_COMMENT, kwargs["body"])
        self.assertIn("メンション", kwargs["body"])
        self.assertEqual(kwargs["link"], f"/app/posts/{self.post.pk}")


class PushMulticastTests(TestCase):
    def setUp(self):
        reset_firebase_app_for_tests()
        self.user = _user("push-multi@waseda.jp", "pushmulti")
        DevicePushToken.objects.create(
            user=self.user, token="keep-token-aaa", platform="ios"
        )
        DevicePushToken.objects.create(
            user=self.user, token="stale-token-bbb", platform="ios"
        )

    def tearDown(self):
        reset_firebase_app_for_tests()

    @override_settings(PUSH_NOTIFICATIONS_ENABLED=True)
    @patch("app.push_services.get_firebase_app", return_value=object())
    def test_unregistered_tokens_are_deleted(self, _mock_app):
        tokens = list(
            DevicePushToken.objects.filter(user=self.user).values_list(
                "token", flat=True
            )
        )
        responses = []
        for token in tokens:
            if token == "stale-token-bbb":
                responses.append(
                    SimpleNamespace(
                        success=False,
                        exception=messaging.UnregisteredError("not registered"),
                    )
                )
            else:
                responses.append(SimpleNamespace(success=True, exception=None))
        batch = SimpleNamespace(responses=responses, success_count=1)

        with patch(
            "firebase_admin.messaging.send_each_for_multicast", return_value=batch
        ):
            sent = send_push_to_user(
                self.user, title="わせわせ", body="hi", link="/app/dm/1"
            )

        self.assertEqual(sent, 1)
        self.assertTrue(DevicePushToken.objects.filter(token="keep-token-aaa").exists())
        self.assertFalse(DevicePushToken.objects.filter(token="stale-token-bbb").exists())

    @override_settings(PUSH_NOTIFICATIONS_ENABLED=True)
    @patch("app.push_services.get_firebase_app", return_value=object())
    def test_temporary_failure_does_not_delete_tokens(self, _mock_app):
        with patch(
            "firebase_admin.messaging.send_each_for_multicast",
            side_effect=RuntimeError("network"),
        ):
            sent = notify_user_push(self.user, body="hi", link="/app/")
        self.assertEqual(sent, 0)
        self.assertEqual(DevicePushToken.objects.filter(user=self.user).count(), 2)

    @override_settings(PUSH_NOTIFICATIONS_ENABLED=True)
    @patch("app.push_services.get_firebase_app", return_value=object())
    def test_quota_response_does_not_delete_tokens(self, _mock_app):
        batch = SimpleNamespace(
            responses=[
                SimpleNamespace(success=False, exception=RuntimeError("quota")),
                SimpleNamespace(success=False, exception=RuntimeError("quota")),
            ],
            success_count=0,
        )
        with patch(
            "firebase_admin.messaging.send_each_for_multicast", return_value=batch
        ):
            send_push_to_user(self.user, title="わせわせ", body="hi", link="/app/")
        self.assertEqual(DevicePushToken.objects.filter(user=self.user).count(), 2)

    @override_settings(PUSH_NOTIFICATIONS_ENABLED=True)
    def test_multiple_devices_are_loaded(self):
        tokens = list(
            DevicePushToken.objects.filter(user=self.user).values_list("token", flat=True)
        )
        self.assertEqual(len(tokens), 2)

    @override_settings(PUSH_NOTIFICATIONS_ENABLED=True)
    @patch("app.push_services.get_firebase_app", return_value=object())
    def test_payload_uses_string_ids_and_omits_full_token_from_logs(self, _mock_app):
        captured: dict = {}

        def fake_send_with_fail(multicast, app=None):
            captured["data"] = dict(multicast.data or {})
            captured["title"] = multicast.notification.title
            captured["body"] = multicast.notification.body
            captured["tokens"] = list(multicast.tokens)
            return SimpleNamespace(
                responses=[
                    SimpleNamespace(success=False, exception=RuntimeError("quota")),
                    SimpleNamespace(success=False, exception=RuntimeError("quota")),
                ],
                success_count=0,
            )

        with patch(
            "firebase_admin.messaging.send_each_for_multicast",
            side_effect=fake_send_with_fail,
        ):
            with self.assertLogs("app.push_services", level="WARNING") as logs:
                send_push_to_user(
                    self.user,
                    title="わせわせ",
                    body="「表示名太郎さんからメッセージが届きました」",
                    link="/app/dm/9",
                    notification_id=123,
                    notification_type="dm",
                )

        self.assertEqual(captured["data"]["link"], "/app/dm/9")
        self.assertEqual(captured["data"]["notification_id"], "123")
        self.assertIsInstance(captured["data"]["link"], str)
        self.assertIsInstance(captured["data"]["notification_id"], str)
        self.assertEqual(captured["title"], "わせわせ")
        self.assertEqual(len(captured["tokens"]), 2)
        joined = "\n".join(logs.output)
        self.assertNotIn("keep-token-aaa", joined)
        self.assertNotIn("stale-token-bbb", joined)
        self.assertNotIn(SECRET_DM, joined)

    @override_settings(PUSH_NOTIFICATIONS_ENABLED=True)
    @patch("app.push_services.get_firebase_app", return_value=object())
    def test_apns_looking_tokens_are_not_sent(self, _mock_app):
        DevicePushToken.objects.create(
            user=self.user, token="a" * 64, platform="ios"
        )
        captured = {}

        def fake_send(multicast, app=None):
            captured["tokens"] = list(multicast.tokens)
            return SimpleNamespace(responses=[], success_count=0)

        with patch(
            "firebase_admin.messaging.send_each_for_multicast", side_effect=fake_send
        ):
            send_push_to_user(self.user, title="わせわせ", body="hi", link="/app/")

        self.assertNotIn("a" * 64, captured["tokens"])
        self.assertIn("keep-token-aaa", captured["tokens"])
        self.assertTrue(DevicePushToken.objects.filter(token="a" * 64).exists())


class PushEventWiringTests(TestCase):
    def setUp(self):
        self.seller = _user("push-seller2@waseda.jp", "pushseller2", "出品者")
        self.buyer = _user("push-buyer2@waseda.jp", "pushbuyer2", "購入者")

    @override_settings(PUSH_NOTIFICATIONS_ENABLED=True)
    @patch("app.push_services.notify_user_push")
    def test_seller_helper_still_pushes_once(self, mock_push):
        product = Product.objects.create(
            seller=self.seller,
            name="push item",
            price=100,
            category="未分類",
        )
        mock_push.return_value = 0
        notify_seller(
            product,
            "コメントがつきました",
            actor_id=self.buyer.id,
            actor=self.buyer,
            push_kind="flea_comment",
        )
        self.assertEqual(mock_push.call_count, 1)
        self.assertEqual(Notification.objects.filter(recipient=self.seller).count(), 1)
        self.assertNotIn("コメントがつきました", mock_push.call_args.kwargs["body"])
        self.assertIn("コメントしました", mock_push.call_args.kwargs["body"])

    @override_settings(PUSH_NOTIFICATIONS_ENABLED=True)
    @patch("app.push_services.notify_user_push")
    def test_dm_send_privacy_and_success_on_push_failure(self, mock_push):
        mock_push.side_effect = RuntimeError("fcm down")
        from .dm_api_services import send_dm_message
        from .dm_services import get_or_create_dm_room

        Follow.objects.create(follower=self.buyer, following=self.seller)
        Follow.objects.create(follower=self.seller, following=self.buyer)
        room, _created = get_or_create_dm_room(self.buyer, self.seller)
        message = send_dm_message(room, self.buyer, SECRET_DM)
        self.assertEqual(message.body, SECRET_DM)
        note = Notification.objects.get(recipient=self.seller)
        self.assertIn(SECRET_DM[:10], note.message)
        mock_push.assert_called_once()
        body = mock_push.call_args.kwargs["body"]
        self.assertNotIn(SECRET_DM, body)
        self.assertIn("メッセージが届きました", body)
        self.assertTrue(str(mock_push.call_args.kwargs["link"]).startswith("/app/dm/"))

    @override_settings(PUSH_NOTIFICATIONS_ENABLED=True)
    @patch("app.push_services.notify_user_push")
    def test_dm_request_body_not_in_push(self, mock_push):
        mock_push.return_value = 0
        from .dm_request_services import _notify_message_request
        from .dm_services import get_or_create_dm_room

        room, _created = get_or_create_dm_room(self.buyer, self.seller)
        _notify_message_request(
            recipient=self.seller,
            sender=self.buyer,
            room=room,
            preview_body=SECRET_DM,
            is_follow_up=False,
        )
        body = mock_push.call_args.kwargs["body"]
        self.assertNotIn(SECRET_DM, body)
        self.assertIn("メッセージリクエスト", body)

    @override_settings(PUSH_NOTIFICATIONS_ENABLED=True)
    @patch("app.push_services.notify_user_push")
    def test_community_reply_body_not_in_push(self, mock_push):
        mock_push.return_value = 0
        seed_communities()
        community = Community.objects.filter(is_active=True).first()
        thread = CommunityThread.objects.create(
            community=community, author=self.seller, title="秘密スレ", body="thread"
        )
        reply = CommunityThreadReply.objects.create(
            thread=thread, author=self.buyer, body=SECRET_COMMENT
        )
        notify_community_reply(reply=reply, thread=thread)
        body = mock_push.call_args.kwargs["body"]
        self.assertNotIn(SECRET_COMMENT, body)
        self.assertNotIn("秘密スレ", body)
        self.assertIn("返信しました", body)
        self.assertIn("/communities/", mock_push.call_args.kwargs["link"])

    @override_settings(PUSH_NOTIFICATIONS_ENABLED=True)
    @patch("app.push_services.notify_user_push")
    def test_structured_share_ugc_not_in_push(self, mock_push):
        mock_push.return_value = 0
        from .share_dm_services import send_share_dm
        from .dm_services import get_or_create_dm_room

        Follow.objects.create(follower=self.buyer, following=self.seller)
        Follow.objects.create(follower=self.seller, following=self.buyer)
        get_or_create_dm_room(self.buyer, self.seller)
        post = TimelinePost.objects.create(author=self.buyer, body=SECRET_SHARE)
        send_share_dm(
            self.buyer,
            partner_id=self.seller.pk,
            target_type="timeline",
            target_id=post.pk,
        )
        body = mock_push.call_args.kwargs["body"]
        self.assertNotIn(SECRET_SHARE, body)
        self.assertIn("シェアされました", body)

    @override_settings(PUSH_NOTIFICATIONS_ENABLED=True)
    @patch("app.push_services.notify_user_push")
    def test_flea_chat_body_not_in_push(self, mock_push):
        mock_push.return_value = 0
        create_notification(
            recipient=self.seller,
            message=f"「商品」のチャット: {SECRET_DM}",
            link="/app/flea/chats/1",
            actor=self.buyer,
            push_kind="flea_trade_chat",
        )
        body = mock_push.call_args.kwargs["body"]
        self.assertNotIn(SECRET_DM, body)
        self.assertEqual(body, "取引チャットにメッセージが届きました")


class PushPayloadHelperTests(TestCase):
    def test_hash_anchor_maps_to_exact_post(self):
        self.assertEqual(push_payload_link("/#post-42"), "/app/posts/42")
        self.assertEqual(push_payload_link("/app/posts/9"), "/app/posts/9")

    def test_privacy_body_never_echoes_ugc_message(self):
        user = _user("priv@waseda.jp", "privuser", "花子")
        body = build_privacy_safe_push_body(kind="dm", actor=user, push_body=None)
        self.assertEqual(body, "「花子さんからメッセージが届きました」")
        self.assertNotIn(SECRET_DM, body)
