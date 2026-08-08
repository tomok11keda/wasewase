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

    def test_create_requires_login(self):
        response = self.client.post(
            "/api/v1/communities/threads/",
            data=json.dumps({"title": "x", "body": "y"}),
            content_type="application/json",
        )
        self.assertIn(response.status_code, (302, 401, 403))
