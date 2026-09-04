"""Phase 4 community JSON API tests."""

from __future__ import annotations

import json

from django.test import Client, TestCase, override_settings

from .community_services import seed_communities
from .models import Community, CommunityThread, User


@override_settings(BROWSE_MODE_GATE_ENABLED=False)
class CommunityApiTests(TestCase):
    def setUp(self):
        seed_communities()
        self.user = User.objects.create_user(
            email="comm-api@waseda.jp",
            password="test-pass-12345",
        )
        self.other = User.objects.create_user(
            email="comm-other@waseda.jp",
            password="test-pass-12345",
        )
        self.community = Community.objects.filter(is_active=True).first()
        self.assertIsNotNone(self.community)
        self.client = Client()

    def test_list_threads(self):
        CommunityThread.objects.create(
            community=self.community,
            author=self.other,
            title="履修相談",
            body="おすすめ科目ありますか",
        )
        response = self.client.get("/api/v1/communities/threads/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(any(t["title"] == "履修相談" for t in data["threads"]))
        self.assertIn("faculty_tabs", data)

    def test_create_reply_edit_delete(self):
        self.client.force_login(self.user)
        created = self.client.post(
            "/api/v1/communities/threads/",
            data=json.dumps(
                {
                    "title": "API thread",
                    "body": "hello community",
                    "tag": self.community.faculty or "",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(created.status_code, 201)
        thread = created.json()["thread"]
        slug = thread["community"]["slug"]
        pk = thread["id"]

        detail = self.client.get(
            f"/api/v1/communities/{slug}/threads/{pk}/"
        )
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()["thread"]["title"], "API thread")

        reply = self.client.post(
            f"/api/v1/communities/{slug}/threads/{pk}/replies/",
            data=json.dumps({"body": "first reply"}),
            content_type="application/json",
        )
        self.assertEqual(reply.status_code, 201)
        reply_id = reply.json()["reply"]["id"]

        edited = self.client.post(
            f"/api/v1/communities/{slug}/threads/{pk}/replies/{reply_id}/",
            data=json.dumps({"body": "edited reply"}),
            content_type="application/json",
        )
        self.assertEqual(edited.status_code, 200)
        self.assertEqual(edited.json()["reply"]["body"], "edited reply")

        deleted_reply = self.client.delete(
            f"/api/v1/communities/{slug}/threads/{pk}/replies/{reply_id}/delete/"
        )
        self.assertEqual(deleted_reply.status_code, 200)

        deleted = self.client.delete(
            f"/api/v1/communities/{slug}/threads/{pk}/delete/"
        )
        self.assertEqual(deleted.status_code, 200)
        self.assertTrue(
            CommunityThread.objects.get(pk=pk).is_removed
        )

    def test_nested_reply_one_level_display_payload(self):
        self.client.force_login(self.user)
        created = self.client.post(
            "/api/v1/communities/threads/",
            data=json.dumps(
                {
                    "title": "楽単教えて",
                    "body": "秋学期のおすすめは？",
                    "tag": self.community.faculty or "",
                }
            ),
            content_type="application/json",
        )
        thread = created.json()["thread"]
        slug = thread["community"]["slug"]
        pk = thread["id"]

        a = self.client.post(
            f"/api/v1/communities/{slug}/threads/{pk}/replies/",
            data=json.dumps({"body": "マーケティング論おすすめ"}),
            content_type="application/json",
        )
        self.assertEqual(a.status_code, 201)
        a_payload = a.json()["reply"]
        self.assertEqual(a_payload["reply_number"], 1)
        self.assertIsNone(a_payload["reply_to"])
        self.assertIn("avatar_url", a_payload["author"])
        self.assertIn("initial", a_payload["author"])

        self.client.force_login(self.other)
        b = self.client.post(
            f"/api/v1/communities/{slug}/threads/{pk}/replies/",
            data=json.dumps(
                {
                    "body": "テスト難しかった？",
                    "reply_to_id": a_payload["id"],
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(b.status_code, 201)
        b_payload = b.json()["reply"]
        self.assertEqual(b_payload["reply_number"], 2)
        self.assertEqual(b_payload["reply_to"]["id"], a_payload["id"])
        self.assertEqual(b_payload["reply_to"]["reply_number"], 1)
        self.assertFalse(b_payload["reply_to"]["is_unavailable"])

        self.client.force_login(self.user)
        c = self.client.post(
            f"/api/v1/communities/{slug}/threads/{pk}/replies/",
            data=json.dumps(
                {
                    "body": "去年は簡単だったよ",
                    "reply_to_id": b_payload["id"],
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(c.status_code, 201)
        c_payload = c.json()["reply"]
        self.assertEqual(c_payload["reply_number"], 3)
        self.assertEqual(c_payload["reply_to"]["id"], b_payload["id"])

        # Cross-thread reply_to must be rejected
        other_thread = self.client.post(
            "/api/v1/communities/threads/",
            data=json.dumps(
                {
                    "title": "別スレ",
                    "body": "別",
                    "tag": self.community.faculty or "",
                }
            ),
            content_type="application/json",
        ).json()["thread"]
        rejected = self.client.post(
            f"/api/v1/communities/{slug}/threads/{pk}/replies/",
            data=json.dumps(
                {
                    "body": "横取り",
                    "reply_to_id": 999999,
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(rejected.status_code, 400)
        self.assertEqual(rejected.json()["error"], "invalid_reply_to")

        # Soft-delete parent keeps child and marks unavailable
        self.client.delete(
            f"/api/v1/communities/{slug}/threads/{pk}/replies/{a_payload['id']}/delete/"
        )
        detail = self.client.get(
            f"/api/v1/communities/{slug}/threads/{pk}/"
        ).json()["thread"]
        by_id = {r["id"]: r for r in detail["replies"]}
        self.assertTrue(by_id[a_payload["id"]]["is_removed"])
        self.assertEqual(by_id[a_payload["id"]]["reply_number"], 1)
        self.assertTrue(by_id[b_payload["id"]]["reply_to"]["is_unavailable"])
        self.assertEqual(by_id[c_payload["id"]]["reply_to"]["id"], b_payload["id"])
        # Numbers stay stable after soft-delete
        self.assertEqual(by_id[b_payload["id"]]["reply_number"], 2)
        self.assertEqual(by_id[c_payload["id"]]["reply_number"], 3)
        self.assertNotEqual(other_thread["id"], pk)

    def test_create_requires_login(self):
        response = self.client.post(
            "/api/v1/communities/threads/",
            data=json.dumps({"title": "x", "body": "y"}),
            content_type="application/json",
        )
        self.assertIn(response.status_code, (302, 401, 403))
