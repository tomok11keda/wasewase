"""Message request (non-follower DM) API tests."""

from __future__ import annotations

from django.test import Client, TestCase, override_settings

from .models import (
    Follow,
    Notification,
    User,
    UserDirectMessage,
    UserDirectMessageRequest,
    UserDirectMessageRoom,
)
from .dm_services import get_or_create_dm_room


@override_settings(BROWSE_MODE_GATE_ENABLED=False)
class MessageRequestApiTests(TestCase):
    def setUp(self):
        self.alice = User.objects.create_user(
            email="req-alice@waseda.jp",
            password="test-pass-12345",
            username="reqalice",
        )
        self.bob = User.objects.create_user(
            email="req-bob@waseda.jp",
            password="test-pass-12345",
            username="reqbob",
        )
        self.client = Client()

    def test_non_follower_dm_becomes_message_request(self):
        self.client.force_login(self.alice)
        start = self.client.post(
            "/api/v1/dm/start/",
            data={"user_id": self.bob.pk},
            content_type="application/json",
        )
        self.assertEqual(start.status_code, 200)
        room_id = start.json()["room_id"]

        sent = self.client.post(
            f"/api/v1/dm/rooms/{room_id}/messages/send/",
            data={"body": "はじめまして"},
            content_type="application/json",
        )
        self.assertEqual(sent.status_code, 201)
        self.assertTrue(
            UserDirectMessageRequest.objects.filter(
                room_id=room_id,
                to_user=self.bob,
                status=UserDirectMessageRequest.Status.PENDING,
            ).exists()
        )
        note = Notification.objects.filter(recipient=self.bob).latest("pk")
        self.assertIn("メッセージリクエスト", note.message)

        # Bob: not in normal inbox, but in requests
        self.client.force_login(self.bob)
        inbox = self.client.get("/api/v1/dm/inbox/").json()
        self.assertEqual(inbox["message_request_count"], 1)
        self.assertFalse(
            any(
                c["kind"] == "dm" and c["room_id"] == room_id
                for c in inbox["conversations"]
            )
        )
        requests = self.client.get("/api/v1/dm/message-requests/").json()
        self.assertEqual(requests["count"], 1)

        room = self.client.get(f"/api/v1/dm/rooms/{room_id}/").json()
        self.assertEqual(room["room"]["request_status"], "pending_request")
        self.assertFalse(room["room"]["can_send"])

        denied = self.client.post(
            f"/api/v1/dm/rooms/{room_id}/messages/send/",
            data={"body": "まだ承認前"},
            content_type="application/json",
        )
        self.assertEqual(denied.status_code, 403)

        accepted = self.client.post(
            f"/api/v1/dm/rooms/{room_id}/requests/accept/",
            content_type="application/json",
        )
        self.assertEqual(accepted.status_code, 200)
        self.assertEqual(accepted.json()["room"]["request_status"], "active")
        inbox2 = self.client.get("/api/v1/dm/inbox/").json()
        self.assertEqual(inbox2["message_request_count"], 0)
        self.assertTrue(
            any(
                c["kind"] == "dm" and c["room_id"] == room_id
                for c in inbox2["conversations"]
            )
        )

    def test_follower_dm_is_normal(self):
        Follow.objects.create(follower=self.bob, following=self.alice)
        self.client.force_login(self.alice)
        start = self.client.post(
            "/api/v1/dm/start/",
            data={"user_id": self.bob.pk},
            content_type="application/json",
        )
        room_id = start.json()["room_id"]
        self.client.post(
            f"/api/v1/dm/rooms/{room_id}/messages/send/",
            data={"body": "フォロー済み宛"},
            content_type="application/json",
        )
        self.assertFalse(
            UserDirectMessageRequest.objects.filter(room_id=room_id).exists()
        )
        self.client.force_login(self.bob)
        inbox = self.client.get("/api/v1/dm/inbox/").json()
        self.assertEqual(inbox["message_request_count"], 0)
        self.assertTrue(
            any(c["room_id"] == room_id for c in inbox["conversations"])
        )

    def test_existing_dm_without_request_stays_normal(self):
        room, _ = get_or_create_dm_room(self.alice, self.bob)
        UserDirectMessage.objects.create(
            room=room, sender=self.alice, body="既存の会話"
        )
        self.client.force_login(self.alice)
        self.client.post(
            f"/api/v1/dm/rooms/{room.pk}/messages/send/",
            data={"body": "続き"},
            content_type="application/json",
        )
        self.assertFalse(
            UserDirectMessageRequest.objects.filter(room=room).exists()
        )

    def test_decline_hides_request(self):
        self.client.force_login(self.alice)
        room_id = self.client.post(
            "/api/v1/dm/start/",
            data={"user_id": self.bob.pk},
            content_type="application/json",
        ).json()["room_id"]
        self.client.post(
            f"/api/v1/dm/rooms/{room_id}/messages/send/",
            data={"body": "拒否テスト"},
            content_type="application/json",
        )
        self.client.force_login(self.bob)
        declined = self.client.post(
            f"/api/v1/dm/rooms/{room_id}/requests/decline/",
            content_type="application/json",
        )
        self.assertEqual(declined.status_code, 200)
        inbox = self.client.get("/api/v1/dm/inbox/").json()
        self.assertEqual(inbox["message_request_count"], 0)
        forbidden = self.client.get(f"/api/v1/dm/rooms/{room_id}/")
        self.assertEqual(forbidden.status_code, 403)

    def test_inbox_survives_missing_request_table(self):
        """本番で 0043 未適用でも inbox が HTML 500 にならないこと。"""
        from unittest.mock import patch

        from django.db.utils import ProgrammingError

        self.client.force_login(self.bob)
        with patch(
            "app.dm_request_services.UserDirectMessageRequest.objects.filter",
            side_effect=ProgrammingError(
                "no such table: app_userdirectmessagerequest"
            ),
        ):
            inbox = self.client.get("/api/v1/dm/inbox/")
        self.assertEqual(inbox.status_code, 200)
        data = inbox.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["message_request_count"], 0)
        self.assertIn("conversations", data)
