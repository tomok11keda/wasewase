"""Phase B internal DM sharing: live ACL share cards."""

from __future__ import annotations

import json

from django.test import Client, TestCase, override_settings

from .models import (
    Follow,
    Notification,
    Product,
    TimelinePost,
    User,
    UserBlock,
    UserDirectMessage,
    UserProfile,
)
from .ugc_services import block_user


@override_settings(BROWSE_MODE_GATE_ENABLED=True, WASE_REACT_SPA=True)
class SocialSharingPhaseBTests(TestCase):
    def setUp(self):
        self.a = User.objects.create_user(
            email="share-a@waseda.jp",
            password="test-pass-12345",
            username="sharea",
        )
        self.b = User.objects.create_user(
            email="share-b@waseda.jp",
            password="test-pass-12345",
            username="shareb",
        )
        UserProfile.objects.update_or_create(
            user=self.a, defaults={"name": "Alice"}
        )
        UserProfile.objects.update_or_create(
            user=self.b, defaults={"name": "Bob"}
        )
        Follow.objects.create(follower=self.a, following=self.b)
        Follow.objects.create(follower=self.b, following=self.a)
        self.post = TimelinePost.objects.create(
            author=self.a,
            body="campus-only share body",
        )
        self.product = Product.objects.create(
            seller=self.a,
            name="シェア教科書",
            price=3000,
            description="秘密の出品説明",
            category="未分類",
        )
        self.client_a = Client()
        self.client_b = Client()
        self.client_a.force_login(self.a)
        self.client_b.force_login(self.b)
        start = self.client_a.post(
            "/api/v1/dm/start/",
            data=json.dumps({"user_id": self.b.pk}),
            content_type="application/json",
        )
        self.assertEqual(start.status_code, 200)
        self.room_id = start.json()["room_id"]
        hello = self.client_a.post(
            f"/api/v1/dm/rooms/{self.room_id}/messages/send/",
            data=json.dumps({"body": "こんにちは"}),
            content_type="application/json",
        )
        self.assertEqual(hello.status_code, 201)

    def _send_share(self, client, *, user_id, target_type, target_id):
        return client.post(
            "/api/v1/dm/share/send/",
            data=json.dumps(
                {
                    "user_id": user_id,
                    "target_type": target_type,
                    "target_id": target_id,
                }
            ),
            content_type="application/json",
        )

    def test_a_visible_timeline_share_card(self):
        res = self._send_share(
            self.client_a,
            user_id=self.b.pk,
            target_type="timeline",
            target_id=self.post.pk,
        )
        self.assertEqual(res.status_code, 201)
        message = res.json()["message"]
        self.assertEqual(message["message_kind"], "share")
        self.assertEqual(message["body"], "投稿をシェアしました")
        stored = UserDirectMessage.objects.get(pk=message["id"])
        self.assertEqual(stored.body, "投稿をシェアしました")
        self.assertEqual(stored.share_target_type, "timeline")
        self.assertEqual(stored.share_target_id, self.post.pk)
        share = message["share"]
        self.assertTrue(share["available"])
        self.assertEqual(share["type"], "timeline")
        self.assertEqual(share["content"]["body_preview"], "campus-only share body")

        room = self.client_b.get(f"/api/v1/dm/rooms/{self.room_id}/")
        self.assertEqual(room.status_code, 200)
        shares = [m for m in room.json()["messages"] if m.get("message_kind") == "share"]
        self.assertEqual(len(shares), 1)
        self.assertTrue(shares[0]["share"]["available"])
        blob = json.dumps(room.json())
        self.assertNotIn("share-a@waseda.jp", blob)
        self.assertNotIn("share-b@waseda.jp", blob)

    def test_b_removed_timeline_stays_but_unavailable(self):
        self._send_share(
            self.client_a,
            user_id=self.b.pk,
            target_type="timeline",
            target_id=self.post.pk,
        )
        self.post.is_removed = True
        self.post.save(update_fields=["is_removed"])
        room = self.client_b.get(f"/api/v1/dm/rooms/{self.room_id}/")
        shares = [m for m in room.json()["messages"] if m.get("message_kind") == "share"]
        self.assertEqual(len(shares), 1)
        self.assertFalse(shares[0]["share"]["available"])
        self.assertNotIn("content", shares[0]["share"])
        self.assertNotIn("campus-only share body", json.dumps(room.json()))
        self.assertTrue(
            UserDirectMessage.objects.filter(
                room_id=self.room_id, message_kind="share"
            ).exists()
        )

    def test_c_private_account_hides_card(self):
        self._send_share(
            self.client_a,
            user_id=self.b.pk,
            target_type="timeline",
            target_id=self.post.pk,
        )
        Follow.objects.filter(follower=self.b, following=self.a).delete()
        profile = self.a.profile
        profile.is_private = True
        profile.save(update_fields=["is_private"])
        room = self.client_b.get(f"/api/v1/dm/rooms/{self.room_id}/")
        shares = [m for m in room.json()["messages"] if m.get("message_kind") == "share"]
        self.assertFalse(shares[0]["share"]["available"])
        self.assertNotIn("campus-only share body", json.dumps(room.json()))

    def test_d_block_hides_card(self):
        self._send_share(
            self.client_a,
            user_id=self.b.pk,
            target_type="timeline",
            target_id=self.post.pk,
        )
        block_user(self.b, self.a)
        room = self.client_b.get(f"/api/v1/dm/rooms/{self.room_id}/")
        shares = [m for m in room.json()["messages"] if m.get("message_kind") == "share"]
        self.assertFalse(shares[0]["share"]["available"])
        self.assertNotIn("campus-only share body", json.dumps(room.json()))

    def test_e_visible_flea_share_card(self):
        res = self._send_share(
            self.client_a,
            user_id=self.b.pk,
            target_type="flea",
            target_id=self.product.pk,
        )
        self.assertEqual(res.status_code, 201)
        share = res.json()["message"]["share"]
        self.assertTrue(share["available"])
        self.assertEqual(share["content"]["name"], "シェア教科書")
        self.assertEqual(share["content"]["price"], 3000)
        blob = json.dumps(res.json())
        self.assertNotIn("秘密の出品説明", blob)
        self.assertNotIn("share-a@waseda.jp", blob)

        room = self.client_b.get(f"/api/v1/dm/rooms/{self.room_id}/")
        shares = [m for m in room.json()["messages"] if m.get("message_kind") == "share"]
        self.assertTrue(shares[0]["share"]["available"])
        self.assertNotIn("秘密の出品説明", json.dumps(room.json()))

    def test_f_removed_flea_unavailable(self):
        self._send_share(
            self.client_a,
            user_id=self.b.pk,
            target_type="flea",
            target_id=self.product.pk,
        )
        self.product.is_removed = True
        self.product.save(update_fields=["is_removed"])
        room = self.client_b.get(f"/api/v1/dm/rooms/{self.room_id}/")
        shares = [m for m in room.json()["messages"] if m.get("message_kind") == "share"]
        self.assertFalse(shares[0]["share"]["available"])
        self.assertNotIn("シェア教科書", json.dumps(shares[0]))

    def test_g_anonymous_cannot_share(self):
        anon = Client()
        recipients = anon.get("/api/v1/dm/share/recipients/")
        self.assertEqual(recipients.status_code, 401)
        send = self._send_share(
            anon,
            user_id=self.b.pk,
            target_type="timeline",
            target_id=self.post.pk,
        )
        self.assertEqual(send.status_code, 401)

    def test_h_browse_mode_cannot_share(self):
        browse = Client()
        entered = browse.post(
            "/api/v1/auth/browse/",
            data=json.dumps({"next": "/app/"}),
            content_type="application/json",
        )
        self.assertEqual(entered.status_code, 200)
        recipients = browse.get("/api/v1/dm/share/recipients/")
        self.assertEqual(recipients.status_code, 401)
        send = self._send_share(
            browse,
            user_id=self.b.pk,
            target_type="timeline",
            target_id=self.post.pk,
        )
        self.assertEqual(send.status_code, 401)

    def test_i_self_send_rejected(self):
        res = self._send_share(
            self.client_a,
            user_id=self.a.pk,
            target_type="timeline",
            target_id=self.post.pk,
        )
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["error"], "own_user")

    def test_j_invalid_target_type_rejected(self):
        res = self._send_share(
            self.client_a,
            user_id=self.b.pk,
            target_type="course",
            target_id=self.post.pk,
        )
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["error"], "invalid_target_type")

    def test_k_invalid_target_id_rejected(self):
        res = self._send_share(
            self.client_a,
            user_id=self.b.pk,
            target_type="timeline",
            target_id=999999,
        )
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["error"], "invalid_target")

    def test_l_normal_text_dm_still_works(self):
        send = self.client_b.post(
            f"/api/v1/dm/rooms/{self.room_id}/messages/send/",
            data=json.dumps({"body": "了解です"}),
            content_type="application/json",
        )
        self.assertEqual(send.status_code, 201)
        message = send.json()["message"]
        self.assertEqual(message["body"], "了解です")
        self.assertEqual(message.get("message_kind"), "text")
        self.assertIsNone(message.get("share"))

    def test_m_share_dm_unread_and_inbox_order(self):
        before = self.client_b.get("/api/v1/dm/inbox/?tab=dm").json()
        before_item = next(
            c for c in before["conversations"] if c["room_id"] == self.room_id
        )
        self._send_share(
            self.client_a,
            user_id=self.b.pk,
            target_type="timeline",
            target_id=self.post.pk,
        )
        inbox = self.client_b.get("/api/v1/dm/inbox/?tab=dm").json()
        item = next(c for c in inbox["conversations"] if c["room_id"] == self.room_id)
        self.assertGreater(item["unread_count"], before_item["unread_count"])
        self.assertEqual(item["latest_body"], "投稿をシェアしました")
        self.assertNotIn("campus-only share body", json.dumps(inbox))
        self.assertEqual(inbox["conversations"][0]["room_id"], self.room_id)

    def test_n_share_payload_has_no_email_or_private_fields(self):
        res = self._send_share(
            self.client_a,
            user_id=self.b.pk,
            target_type="flea",
            target_id=self.product.pk,
        )
        blob = json.dumps(res.json())
        self.assertNotIn("@waseda.jp", blob)
        self.assertNotIn("秘密の出品説明", blob)
        self.assertNotIn("stripe", blob.lower())
        content = res.json()["message"]["share"]["content"]
        self.assertEqual(set(content), {"id", "name", "price", "image_url", "seller"})

    def test_notification_does_not_leak_body(self):
        self._send_share(
            self.client_a,
            user_id=self.b.pk,
            target_type="timeline",
            target_id=self.post.pk,
        )
        note = Notification.objects.filter(recipient=self.b).latest("pk")
        self.assertEqual(note.message, "Aliceさんから投稿がシェアされました")
        self.assertNotIn("campus-only share body", note.message)

    def test_recipients_row_and_not_a_partner(self):
        recipients = self.client_a.get("/api/v1/dm/share/recipients/")
        self.assertEqual(recipients.status_code, 200)
        data = recipients.json()
        ids = [row["user_id"] for row in data["recipients"]]
        self.assertIn(self.b.pk, ids)
        self.assertNotIn(self.a.pk, ids)
        stranger = User.objects.create_user(
            email="share-c@waseda.jp",
            password="test-pass-12345",
            username="sharec",
        )
        UserProfile.objects.update_or_create(
            user=stranger, defaults={"name": "Cara"}
        )
        denied = self._send_share(
            self.client_a,
            user_id=stranger.pk,
            target_type="timeline",
            target_id=self.post.pk,
        )
        self.assertEqual(denied.status_code, 400)
        self.assertEqual(denied.json()["error"], "not_a_partner")

    def test_blocked_partner_excluded_from_recipients(self):
        UserBlock.objects.create(blocker=self.a, blocked=self.b)
        recipients = self.client_a.get("/api/v1/dm/share/recipients/")
        ids = [row["user_id"] for row in recipients.json()["all_recipients"]]
        self.assertNotIn(self.b.pk, ids)

    def test_send_unavailable_target_rejected(self):
        self.post.is_removed = True
        self.post.save(update_fields=["is_removed"])
        res = self._send_share(
            self.client_a,
            user_id=self.b.pk,
            target_type="timeline",
            target_id=self.post.pk,
        )
        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.json()["error"], "unavailable")
        self.assertFalse(
            UserDirectMessage.objects.filter(message_kind="share").exists()
        )
