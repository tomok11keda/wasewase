"""Timeline comment threading (parent_comment, tombstone, order, API)."""

from __future__ import annotations

import json

from django.test import Client, TestCase, override_settings

from .comment_thread_services import TOMBSTONE_BODY
from .models import Comment, TimelinePost, User


@override_settings(BROWSE_MODE_GATE_ENABLED=False)
class TimelineCommentThreadTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="thread-a@waseda.jp",
            password="test-pass-12345",
        )
        self.other = User.objects.create_user(
            email="thread-b@waseda.jp",
            password="test-pass-12345",
        )
        self.post = TimelinePost.objects.create(
            author=self.user,
            body="thread root post",
        )
        self.other_post = TimelinePost.objects.create(
            author=self.other,
            body="another post",
        )
        self.client = Client()
        self.client.force_login(self.user)

    def _comment(self, body, *, post=None, parent_id=None, user=None):
        if user is not None:
            self.client.force_login(user)
        payload = {"body": body}
        if parent_id is not None:
            payload["parent_comment_id"] = parent_id
        target = post or self.post
        response = self.client.post(
            f"/api/v1/timeline/{target.pk}/comments/",
            data=json.dumps(payload),
            content_type="application/json",
        )
        if user is not None:
            self.client.force_login(self.user)
        return response

    def test_direct_comment_omits_parent_and_keeps_legacy_fields(self):
        response = self._comment("top level")
        self.assertEqual(response.status_code, 201)
        comment = response.json()["comment"]
        self.assertEqual(comment["body"], "top level")
        self.assertIsNone(comment["parent_comment_id"])
        self.assertIsNone(comment["reply_to"])
        self.assertFalse(comment["is_deleted"])
        self.assertEqual(comment["reply_count"], 0)
        self.assertIn("author", comment)
        self.assertIn("created_at", comment)
        self.assertIn("can_delete", comment)
        self.assertEqual(response.json()["comment_count"], 1)

    def test_reply_to_comment_and_reply_to_reply(self):
        root = self._comment("A").json()["comment"]
        child = self._comment("B", parent_id=root["id"]).json()["comment"]
        grand = self._comment("C", parent_id=child["id"]).json()["comment"]
        self.assertEqual(child["parent_comment_id"], root["id"])
        self.assertEqual(child["reply_to"]["id"], root["id"])
        self.assertFalse(child["reply_to"]["is_unavailable"])
        self.assertEqual(grand["parent_comment_id"], child["id"])

        detail = self.client.get(f"/api/v1/timeline/{self.post.pk}/")
        bodies = [row["body"] for row in detail.json()["post"]["comments"]]
        self.assertEqual(bodies, ["A", "B", "C"])
        comments = {row["id"]: row for row in detail.json()["post"]["comments"]}
        self.assertEqual(comments[root["id"]]["reply_count"], 1)
        self.assertEqual(comments[child["id"]]["reply_count"], 1)
        self.assertEqual(detail.json()["post"]["comment_count"], 3)

    def test_three_or_more_levels_and_sibling_roots_keep_thread_order(self):
        a = self._comment("A").json()["comment"]
        b = self._comment("B").json()["comment"]
        a1 = self._comment("A1", parent_id=a["id"]).json()["comment"]
        a2 = self._comment("A2", parent_id=a1["id"]).json()["comment"]
        a3 = self._comment("A3", parent_id=a2["id"]).json()["comment"]
        a4 = self._comment("A4", parent_id=a3["id"]).json()["comment"]
        b1 = self._comment("B1", parent_id=b["id"]).json()["comment"]
        detail = self.client.get(f"/api/v1/timeline/{self.post.pk}/")
        self.assertEqual(
            [row["body"] for row in detail.json()["post"]["comments"]],
            ["A", "A1", "A2", "A3", "A4", "B", "B1"],
        )
        self.assertEqual(a4["parent_comment_id"], a3["id"])
        self.assertEqual(b1["parent_comment_id"], b["id"])

    def test_rejects_missing_other_post_and_unavailable_parents(self):
        missing = self._comment("nope", parent_id=999999)
        self.assertEqual(missing.status_code, 400)
        self.assertEqual(missing.json()["error"], "parent_not_found")

        foreign = self._comment("x", post=self.other_post).json()["comment"]
        wrong = self._comment("nope", parent_id=foreign["id"])
        self.assertEqual(wrong.status_code, 400)
        self.assertEqual(wrong.json()["error"], "parent_wrong_post")

        parent = self._comment("live").json()["comment"]
        Comment.objects.filter(pk=parent["id"]).update(is_removed=True)
        removed = self._comment("nope", parent_id=parent["id"])
        self.assertEqual(removed.status_code, 400)
        self.assertEqual(removed.json()["error"], "parent_unavailable")

    def test_cannot_reply_to_author_deleted_parent(self):
        parent = self._comment("keep children").json()["comment"]
        self._comment("child", parent_id=parent["id"])
        deleted = self.client.delete(f"/api/v1/timeline/comments/{parent['id']}/")
        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(deleted.json()["comment"]["body"], TOMBSTONE_BODY)
        self.assertTrue(deleted.json()["comment"]["is_deleted"])
        blocked = self._comment("nope", parent_id=parent["id"])
        self.assertEqual(blocked.status_code, 400)
        self.assertEqual(blocked.json()["error"], "parent_unavailable")

    def test_delete_leaf_removes_row_parent_with_replies_is_tombstone(self):
        parent = self._comment("parent").json()["comment"]
        child = self._comment("child", parent_id=parent["id"]).json()["comment"]
        tombstone = self.client.delete(f"/api/v1/timeline/comments/{parent['id']}/")
        stored = Comment.objects.get(pk=parent["id"])
        self.assertTrue(stored.is_author_deleted)
        self.assertEqual(stored.body, "")
        self.assertEqual(tombstone.json()["comment_count"], 1)
        self.assertEqual(tombstone.json()["comment"]["body"], TOMBSTONE_BODY)
        self.assertIsNone(tombstone.json()["comment"]["author"])

        detail = self.client.get(f"/api/v1/timeline/{self.post.pk}/")
        comments = detail.json()["post"]["comments"]
        self.assertEqual(len(comments), 2)
        self.assertEqual(comments[0]["body"], TOMBSTONE_BODY)
        self.assertIsNone(comments[0]["author"])
        self.assertEqual(comments[1]["body"], "child")
        self.assertTrue(comments[1]["reply_to"]["is_unavailable"])
        self.assertEqual(comments[1]["reply_to"]["username"], "")
        self.assertEqual(comments[1]["reply_to"]["display_name"], "")

        gone = self.client.delete(f"/api/v1/timeline/comments/{child['id']}/")
        self.assertEqual(gone.status_code, 200)
        self.assertNotIn("comment", gone.json())
        self.assertFalse(Comment.objects.filter(pk=child["id"]).exists())
        self.assertFalse(Comment.objects.filter(pk=parent["id"]).exists())
        after = self.client.get(f"/api/v1/timeline/{self.post.pk}/")
        self.assertEqual(after.json()["post"]["comments"], [])
        self.assertEqual(after.json()["post"]["comment_count"], 0)

    def test_list_payload_still_includes_comments_array_for_compat(self):
        self._comment("compat")
        listed = self.client.get("/api/v1/timeline/")
        matched = next(
            post for post in listed.json()["posts"] if post["id"] == self.post.pk
        )
        self.assertEqual(matched["comments"][0]["body"], "compat")
        self.assertIn("parent_comment_id", matched["comments"][0])
        self.assertEqual(matched["comment_count"], 1)
