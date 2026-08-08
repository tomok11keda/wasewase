"""Phase 8 DM / Group Chat JSON API tests."""

from __future__ import annotations

import json

from django.test import Client, TestCase, override_settings

from .models import Follow, User, UserBlock, UserProfile


@override_settings(BROWSE_MODE_GATE_ENABLED=False)
class DmApiTests(TestCase):
    def setUp(self):
        self.a = User.objects.create_user(
            email="dm-a@waseda.jp", password="test-pass-12345", username="dma"
        )
        self.b = User.objects.create_user(
            email="dm-b@waseda.jp", password="test-pass-12345", username="dmb"
        )
        UserProfile.objects.update_or_create(user=self.a, defaults={"name": "A"})
        UserProfile.objects.update_or_create(user=self.b, defaults={"name": "B"})
        Follow.objects.create(follower=self.a, following=self.b)
        self.client = Client()

    def test_start_send_poll_inbox(self):
        self.client.force_login(self.a)
        start = self.client.post(
            "/api/v1/dm/start/",
            data=json.dumps({"user_id": self.b.pk}),
            content_type="application/json",
        )
        self.assertEqual(start.status_code, 200)
        room_id = start.json()["room_id"]
        self.assertEqual(start.json()["spa_path"], f"/dm/{room_id}")

        send = self.client.post(
            f"/api/v1/dm/rooms/{room_id}/messages/send/",
            data=json.dumps({"body": "こんにちは"}),
            content_type="application/json",
        )
        self.assertEqual(send.status_code, 201)
        self.assertEqual(send.json()["message"]["body"], "こんにちは")

        room = self.client.get(f"/api/v1/dm/rooms/{room_id}/")
        self.assertEqual(room.status_code, 200)
        self.assertTrue(
            any(m["body"] == "こんにちは" for m in room.json()["messages"])
        )

        poll = self.client.get(f"/api/v1/dm/rooms/{room_id}/messages/?after=0")
        self.assertEqual(poll.status_code, 200)
        self.assertIn("latest_id", poll.json())

        inbox = self.client.get("/api/v1/dm/inbox/?tab=dm")
        self.assertEqual(inbox.status_code, 200)
        self.assertTrue(
            any(c["room_id"] == room_id for c in inbox.json()["conversations"])
        )

    def test_start_blocked_rejected(self):
        UserBlock.objects.create(blocker=self.a, blocked=self.b)
        self.client.force_login(self.a)
        start = self.client.post(
            "/api/v1/dm/start/",
            data=json.dumps({"user_id": self.b.pk}),
            content_type="application/json",
        )
        self.assertEqual(start.status_code, 400)
        self.assertEqual(start.json()["error"], "blocked")

    def test_group_create_and_send(self):
        self.client.force_login(self.a)
        created = self.client.post(
            "/api/v1/dm/groups/",
            data=json.dumps({"name": "履修相談", "member_ids": [self.b.pk]}),
            content_type="application/json",
        )
        self.assertEqual(created.status_code, 201)
        room_id = created.json()["room_id"]
        self.assertEqual(created.json()["spa_path"], f"/dm/groups/{room_id}")

        send = self.client.post(
            f"/api/v1/dm/groups/{room_id}/messages/send/",
            data=json.dumps({"body": "グループへようこそ"}),
            content_type="application/json",
        )
        self.assertEqual(send.status_code, 201)

        detail = self.client.get(f"/api/v1/dm/groups/{room_id}/")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()["room"]["name"], "履修相談")


@override_settings(WASE_REACT_SPA=False, BROWSE_MODE_GATE_ENABLED=False)
class ClassicDmUnaffectedTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="classic-dm@waseda.jp",
            password="test-pass-12345",
            username="classicdm",
        )
        UserProfile.objects.update_or_create(
            user=self.user, defaults={"name": "Classic"}
        )
        self.client = Client()

    def test_classic_dm_inbox_still_html(self):
        self.client.force_login(self.user)
        res = self.client.get("/dm/")
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "メッセージ")
        self.assertNotContains(res, 'id="root"')
