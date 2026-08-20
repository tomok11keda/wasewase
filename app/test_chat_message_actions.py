"""ChatMessage 返信・削除・通報（Group / Course Talk 共通）の API テスト。"""

from __future__ import annotations

from django.test import Client, TestCase, override_settings

from app.course_services import create_offering
from app.models import (
    ChatMessage,
    ChatRoomMembership,
    ContentReport,
    User,
)


@override_settings(BROWSE_MODE_GATE_ENABLED=False)
class ChatMessageReplyDeleteTests(TestCase):
    def setUp(self):
        self.alice = User.objects.create_user(
            email="reply-alice@waseda.jp",
            password="test-pass-12345",
            username="replyalice",
        )
        self.bob = User.objects.create_user(
            email="reply-bob@waseda.jp",
            password="test-pass-12345",
            username="replybob",
        )
        self.client = Client()
        self.client.force_login(self.alice)
        created = self.client.post(
            "/api/v1/dm/groups/",
            data={"name": "返信テスト組", "member_ids": [self.bob.pk]},
            content_type="application/json",
        )
        self.assertEqual(created.status_code, 201, created.content)
        self.room_id = created.json()["room_id"]
        # Bob accepts invite so both can send
        bob_client = Client()
        bob_client.force_login(self.bob)
        accept = bob_client.post(
            f"/api/v1/dm/groups/{self.room_id}/invitations/accept/",
            data={},
            content_type="application/json",
        )
        self.assertEqual(accept.status_code, 200, accept.content)
        self.bob_client = bob_client

    def _send(self, client, body, reply_to_id=None, room_id=None):
        payload = {"body": body}
        if reply_to_id is not None:
            payload["reply_to_id"] = reply_to_id
        return client.post(
            f"/api/v1/dm/groups/{room_id or self.room_id}/messages/send/",
            data=payload,
            content_type="application/json",
        )

    def test_send_without_reply(self):
        res = self._send(self.client, "普通の投稿")
        self.assertEqual(res.status_code, 201, res.content)
        msg = res.json()["message"]
        self.assertIsNone(msg.get("reply_to"))
        self.assertFalse(msg.get("is_deleted"))

    def test_reply_same_room_success(self):
        parent = self._send(self.client, "親メッセージ").json()["message"]
        res = self._send(self.bob_client, "返信です", reply_to_id=parent["id"])
        self.assertEqual(res.status_code, 201, res.content)
        msg = res.json()["message"]
        self.assertEqual(msg["reply_to"]["id"], parent["id"])
        self.assertEqual(msg["reply_to"]["text_preview"], "親メッセージ")
        self.assertFalse(msg["reply_to"]["is_unavailable"])
        db = ChatMessage.objects.get(pk=msg["id"])
        self.assertEqual(db.reply_to_id, parent["id"])

    def test_reply_wrong_room_rejected(self):
        other = self.client.post(
            "/api/v1/dm/groups/",
            data={"name": "別ルーム", "member_ids": [self.bob.pk]},
            content_type="application/json",
        )
        self.assertEqual(other.status_code, 201, other.content)
        other_id = other.json()["room_id"]
        parent = self._send(self.client, "別室の親", room_id=other_id).json()[
            "message"
        ]
        res = self._send(self.bob_client, "横取り返信", reply_to_id=parent["id"])
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json().get("error"), "reply_wrong_room")

    def test_reply_missing_id_rejected(self):
        res = self._send(self.client, "存在しないへ", reply_to_id=999999)
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json().get("error"), "reply_not_found")

    def test_reply_to_hidden_allowed_with_unavailable_preview(self):
        parent = self._send(self.client, "後で隠す").json()["message"]
        ChatMessage.objects.filter(pk=parent["id"]).update(is_hidden=True)
        res = self._send(self.bob_client, "hiddenへ返信", reply_to_id=parent["id"])
        self.assertEqual(res.status_code, 201, res.content)
        preview = res.json()["message"]["reply_to"]
        self.assertTrue(preview["is_unavailable"])
        self.assertEqual(preview["text_preview"], "削除されたメッセージ")

    def test_author_soft_delete_and_reply_preview(self):
        parent = self._send(self.client, "消す予定").json()["message"]
        reply = self._send(
            self.bob_client, "残る返信", reply_to_id=parent["id"]
        ).json()["message"]
        deleted = self.client.post(
            f"/api/v1/dm/groups/{self.room_id}/messages/{parent['id']}/delete/",
            data={},
            content_type="application/json",
        )
        self.assertEqual(deleted.status_code, 200, deleted.content)
        tomb = deleted.json()["message"]
        self.assertTrue(tomb["is_deleted"])
        self.assertEqual(tomb["body"], "")

        room = self.bob_client.get(f"/api/v1/dm/groups/{self.room_id}/")
        messages = {m["id"]: m for m in room.json()["messages"]}
        self.assertTrue(messages[parent["id"]]["is_deleted"])
        self.assertIn(reply["id"], messages)
        self.assertTrue(messages[reply["id"]]["reply_to"]["is_unavailable"])
        self.assertEqual(
            messages[reply["id"]]["reply_to"]["text_preview"],
            "削除されたメッセージ",
        )
        # FK は残る
        self.assertEqual(
            ChatMessage.objects.get(pk=reply["id"]).reply_to_id, parent["id"]
        )

    def test_cannot_delete_others_message(self):
        parent = self._send(self.client, "Aliceの投稿").json()["message"]
        res = self.bob_client.post(
            f"/api/v1/dm/groups/{self.room_id}/messages/{parent['id']}/delete/",
            data={},
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.json().get("error"), "forbidden")
        self.assertIsNone(ChatMessage.objects.get(pk=parent["id"]).deleted_at)


@override_settings(BROWSE_MODE_GATE_ENABLED=False)
class CourseTalkReplyDeleteReportTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="ctalk-a@waseda.jp", password="test-pass-12345"
        )
        self.other = User.objects.create_user(
            email="ctalk-b@waseda.jp", password="test-pass-12345"
        )
        self.client = Client()
        self.client.force_login(self.user)
        offering, _ = create_offering(
            user=self.user,
            title="返信トーク授業",
            instructor="教員",
            academic_year=2026,
            semester="spring",
            day_of_week=3,
            period=2,
            force_create=True,
        )
        self.offering = offering
        opened = self.client.post(
            f"/api/v1/courses/offerings/{offering.pk}/talk/",
            data={},
            content_type="application/json",
        )
        self.assertEqual(opened.status_code, 200, opened.content)
        self.room_id = opened.json()["room"]["id"]
        other = Client()
        other.force_login(self.other)
        other.post(
            f"/api/v1/courses/offerings/{offering.pk}/talk/",
            data={},
            content_type="application/json",
        )
        self.other_client = other

    def _send(self, client, body, reply_to_id=None):
        payload = {"body": body}
        if reply_to_id is not None:
            payload["reply_to_id"] = reply_to_id
        return client.post(
            f"/api/v1/courses/talk/{self.room_id}/messages/send/",
            data=payload,
            content_type="application/json",
        )

    def test_course_talk_reply_and_delete(self):
        parent = self._send(self.client, "質問です").json()["message"]
        reply = self._send(
            self.other_client, "答えます", reply_to_id=parent["id"]
        )
        self.assertEqual(reply.status_code, 200, reply.content)
        self.assertEqual(reply.json()["message"]["reply_to"]["id"], parent["id"])

        deleted = self.client.post(
            f"/api/v1/courses/talk/{self.room_id}/messages/{parent['id']}/delete/",
            data={},
            content_type="application/json",
        )
        self.assertEqual(deleted.status_code, 200, deleted.content)
        self.assertTrue(deleted.json()["message"]["is_deleted"])

        denied = self.other_client.post(
            f"/api/v1/courses/talk/{self.room_id}/messages/{parent['id']}/delete/",
            data={},
            content_type="application/json",
        )
        # already soft-deleted by author → forbidden for other (or already gone)
        self.assertIn(denied.status_code, (403, 400))

    def test_report_chat_message_and_self_reject_and_duplicate(self):
        msg = self._send(self.client, "通報対象").json()["message"]

        self_report = self.client.post(
            f"/report/chat_message/{msg['id']}/",
            data={"reason": ContentReport.Reason.SPAM},
            HTTP_ACCEPT="application/json",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(self_report.status_code, 400)

        ok = self.other_client.post(
            f"/report/chat_message/{msg['id']}/",
            data={"reason": ContentReport.Reason.HARASSMENT},
            HTTP_ACCEPT="application/json",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(ok.status_code, 200, ok.content)
        self.assertTrue(ok.json().get("ok"))
        self.assertEqual(
            ContentReport.objects.filter(
                reporter=self.other,
                target_type=ContentReport.TargetType.CHAT_MESSAGE,
                target_id=msg["id"],
            ).count(),
            1,
        )

        dup = self.other_client.post(
            f"/report/chat_message/{msg['id']}/",
            data={"reason": ContentReport.Reason.SPAM},
            HTTP_ACCEPT="application/json",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(dup.status_code, 200)
        self.assertTrue(dup.json().get("ok"))
        self.assertEqual(
            ContentReport.objects.filter(
                reporter=self.other,
                target_type=ContentReport.TargetType.CHAT_MESSAGE,
                target_id=msg["id"],
            ).count(),
            1,
        )

    def test_permissions_require_login_and_membership(self):
        guest = Client()
        res = guest.post(
            f"/api/v1/courses/talk/{self.room_id}/messages/send/",
            data={"body": "x"},
            content_type="application/json",
        )
        self.assertIn(res.status_code, (401, 302, 403))

        # Leave then cannot send
        self.other_client.post(
            f"/api/v1/courses/offerings/{self.offering.pk}/talk/leave/",
            data={},
            content_type="application/json",
        )
        denied = self.other_client.post(
            f"/api/v1/courses/talk/{self.room_id}/messages/send/",
            data={"body": "退出後"},
            content_type="application/json",
        )
        self.assertIn(denied.status_code, (403, 404))
        self.assertFalse(
            ChatRoomMembership.objects.filter(
                room_id=self.room_id, user=self.other
            ).exists()
        )
