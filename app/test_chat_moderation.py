"""ChatMessage 運営削除・異議申し立てのテスト。"""

from __future__ import annotations

from django.test import Client, TestCase, override_settings

from app.models import (
    ChatMessage,
    ChatMessageModerationAppeal,
    ContentReport,
    User,
)
from app.moderation_services import (
    accept_chat_message_appeal,
    hide_chat_message,
    reject_chat_message_appeal,
    submit_chat_message_appeal,
)


@override_settings(BROWSE_MODE_GATE_ENABLED=False)
class ChatMessageModerationTests(TestCase):
    def setUp(self):
        self.alice = User.objects.create_user(
            email="mod-alice@waseda.jp",
            password="test-pass-12345",
            username="modalice",
        )
        self.bob = User.objects.create_user(
            email="mod-bob@waseda.jp",
            password="test-pass-12345",
            username="modbob",
        )
        self.staff = User.objects.create_user(
            email="mod-staff@waseda.jp",
            password="test-pass-12345",
            username="modstaff",
            is_staff=True,
        )
        self.alice_client = Client()
        self.alice_client.force_login(self.alice)
        self.bob_client = Client()
        self.bob_client.force_login(self.bob)
        created = self.alice_client.post(
            "/api/v1/dm/groups/",
            data={"name": "運営削除テスト組", "member_ids": [self.bob.pk]},
            content_type="application/json",
        )
        self.assertEqual(created.status_code, 201, created.content)
        self.room_id = created.json()["room_id"]
        accept = self.bob_client.post(
            f"/api/v1/dm/groups/{self.room_id}/invitations/accept/",
            data={},
            content_type="application/json",
        )
        self.assertEqual(accept.status_code, 200, accept.content)

    def _send(self, client, body):
        return client.post(
            f"/api/v1/dm/groups/{self.room_id}/messages/send/",
            data={"body": body},
            content_type="application/json",
        )

    def _room_messages(self, client):
        room = client.get(f"/api/v1/dm/groups/{self.room_id}/")
        self.assertEqual(room.status_code, 200, room.content)
        return {m["id"]: m for m in room.json()["messages"]}

    def _appeal(self, client, message_id, explanation="理由です"):
        return client.post(
            f"/api/v1/chat/messages/{message_id}/appeals/",
            data={"explanation": explanation},
            content_type="application/json",
        )

    def test_normal_message_still_visible(self):
        res = self._send(self.alice_client, "普通の投稿")
        self.assertEqual(res.status_code, 201, res.content)
        msg = res.json()["message"]
        self.assertEqual(msg["body"], "普通の投稿")
        self.assertFalse(msg.get("is_removed"))
        self.assertFalse(msg.get("is_deleted"))
        listed = self._room_messages(self.bob_client)[msg["id"]]
        self.assertEqual(listed["body"], "普通の投稿")
        self.assertFalse(listed.get("can_appeal"))

    def test_staff_removed_message_is_placeholder_and_body_is_hidden(self):
        unique = "SECRET_MODERATION_BODY_XYZ"
        msg = self._send(self.alice_client, unique).json()["message"]
        db = ChatMessage.objects.get(pk=msg["id"])
        hide_chat_message(message=db, moderator=self.staff, reason="危害")
        db.refresh_from_db()
        self.assertTrue(db.is_hidden)
        self.assertEqual(db.body, unique)
        self.assertIsNotNone(db.removed_at)

        alice_view = self._room_messages(self.alice_client)[msg["id"]]
        bob_view = self._room_messages(self.bob_client)[msg["id"]]
        for view in (alice_view, bob_view):
            self.assertTrue(view["is_removed"])
            self.assertEqual(view["body"], "")
            self.assertNotIn(unique, view["body"])
        raw_alice = self.alice_client.get(f"/api/v1/dm/groups/{self.room_id}/").content.decode()
        raw_bob = self.bob_client.get(f"/api/v1/dm/groups/{self.room_id}/").content.decode()
        self.assertNotIn(unique, raw_alice)
        self.assertNotIn(unique, raw_bob)
        self.assertTrue(alice_view["can_appeal"])
        self.assertFalse(bob_view["can_appeal"])
        self.assertIsNone(bob_view["appeal_status"])

        inbox = self.bob_client.get("/api/v1/dm/inbox/?tab=dm")
        self.assertEqual(inbox.status_code, 200, inbox.content)
        inbox_json = inbox.json()
        self.assertNotIn(unique, inbox.content.decode())
        latest_bodies = [c.get("latest_body", "") for c in inbox_json["conversations"]]
        self.assertTrue(any("運営により削除" in body for body in latest_bodies))

    def test_sender_can_appeal_others_cannot(self):
        msg = self._send(self.alice_client, "対象").json()["message"]
        hide_chat_message(
            message=ChatMessage.objects.get(pk=msg["id"]),
            moderator=self.staff,
        )
        ok = self._appeal(self.alice_client, msg["id"], "誤解です")
        self.assertEqual(ok.status_code, 201, ok.content)
        self.assertTrue(ok.json().get("ok"))
        self.assertEqual(
            ChatMessageModerationAppeal.objects.filter(
                message_id=msg["id"], appellant=self.alice
            ).count(),
            1,
        )
        denied = self._appeal(self.bob_client, msg["id"], "他人です")
        self.assertEqual(denied.status_code, 403)
        self.assertEqual(denied.json().get("error"), "forbidden")
        self.assertFalse(
            ChatMessageModerationAppeal.objects.filter(appellant=self.bob).exists()
        )

    def test_anonymous_cannot_appeal(self):
        msg = self._send(self.alice_client, "匿名ブロック").json()["message"]
        hide_chat_message(
            message=ChatMessage.objects.get(pk=msg["id"]),
            moderator=self.staff,
        )
        guest = Client()
        res = guest.post(
            f"/api/v1/chat/messages/{msg['id']}/appeals/",
            data={"explanation": "guest"},
            content_type="application/json",
        )
        self.assertIn(res.status_code, (401, 302, 403))
        self.assertFalse(ChatMessageModerationAppeal.objects.exists())

    def test_duplicate_pending_appeal_rejected(self):
        msg = self._send(self.alice_client, "重複").json()["message"]
        hide_chat_message(
            message=ChatMessage.objects.get(pk=msg["id"]),
            moderator=self.staff,
        )
        first = self._appeal(self.alice_client, msg["id"])
        self.assertEqual(first.status_code, 201, first.content)
        second = self._appeal(self.alice_client, msg["id"], "二回目")
        self.assertEqual(second.status_code, 400)
        self.assertEqual(second.json().get("error"), "already_pending")
        self.assertEqual(
            ChatMessageModerationAppeal.objects.filter(message_id=msg["id"]).count(),
            1,
        )
        listed = self._room_messages(self.alice_client)[msg["id"]]
        self.assertEqual(listed["appeal_status"], "pending")
        self.assertFalse(listed["can_appeal"])

    def test_accept_restores_message(self):
        unique = "復元される本文"
        msg = self._send(self.alice_client, unique).json()["message"]
        db = ChatMessage.objects.get(pk=msg["id"])
        hide_chat_message(message=db, moderator=self.staff)
        appeal = submit_chat_message_appeal(
            message=ChatMessage.objects.get(pk=msg["id"]),
            user=self.alice,
            explanation="誤解でした",
        )
        accept_chat_message_appeal(appeal, self.staff, note="認容")
        db.refresh_from_db()
        appeal.refresh_from_db()
        self.assertFalse(db.is_hidden)
        self.assertIsNone(db.removed_at)
        self.assertEqual(appeal.status, ChatMessageModerationAppeal.Status.ACCEPTED)
        listed = self._room_messages(self.bob_client)[msg["id"]]
        self.assertFalse(listed["is_removed"])
        self.assertEqual(listed["body"], unique)

    def test_reject_keeps_removed(self):
        unique = "却下後も隠す"
        msg = self._send(self.alice_client, unique).json()["message"]
        hide_chat_message(
            message=ChatMessage.objects.get(pk=msg["id"]),
            moderator=self.staff,
        )
        appeal = submit_chat_message_appeal(
            message=ChatMessage.objects.get(pk=msg["id"]),
            user=self.alice,
            explanation="お願いします",
        )
        reject_chat_message_appeal(appeal, self.staff, note="維持")
        db = ChatMessage.objects.get(pk=msg["id"])
        appeal.refresh_from_db()
        self.assertTrue(db.is_hidden)
        self.assertEqual(db.body, unique)
        self.assertEqual(appeal.status, ChatMessageModerationAppeal.Status.REJECTED)
        listed = self._room_messages(self.bob_client)[msg["id"]]
        self.assertTrue(listed["is_removed"])
        self.assertEqual(listed["body"], "")
        self.assertNotIn(unique, listed["body"])

    def test_hide_marks_related_content_reports_handled(self):
        msg = self._send(self.alice_client, "通報対象").json()["message"]
        ContentReport.objects.create(
            reporter=self.bob,
            target_type=ContentReport.TargetType.CHAT_MESSAGE,
            target_id=msg["id"],
            reason=ContentReport.Reason.HARASSMENT,
        )
        other = User.objects.create_user(
            email="mod-carol@waseda.jp",
            password="test-pass-12345",
            username="modcarol",
        )
        ContentReport.objects.create(
            reporter=other,
            target_type=ContentReport.TargetType.CHAT_MESSAGE,
            target_id=msg["id"],
            reason=ContentReport.Reason.INAPPROPRIATE,
        )
        hide_chat_message(
            message=ChatMessage.objects.get(pk=msg["id"]),
            moderator=self.staff,
        )
        reports = list(
            ContentReport.objects.filter(
                target_type=ContentReport.TargetType.CHAT_MESSAGE,
                target_id=msg["id"],
            )
        )
        self.assertEqual(len(reports), 2)
        for report in reports:
            self.assertIsNotNone(report.handled_at)
            self.assertEqual(report.handled_by_id, self.staff.pk)

    def test_cannot_appeal_others_id_rewrite_or_visible_message(self):
        visible = self._send(self.alice_client, "見える").json()["message"]
        res = self._appeal(self.alice_client, visible["id"])
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json().get("error"), "not_removed")

        hidden = self._send(self.alice_client, "隠す").json()["message"]
        hide_chat_message(
            message=ChatMessage.objects.get(pk=hidden["id"]),
            moderator=self.staff,
        )
        rewritten = self._appeal(self.bob_client, hidden["id"])
        self.assertEqual(rewritten.status_code, 403)
