"""Flea product comments stay flat; Timeline threading fields must not leak."""

from __future__ import annotations

import json

from django.test import Client, TestCase, override_settings
from django.urls import reverse

from .models import Comment, Product, TimelinePost, User


@override_settings(BROWSE_MODE_GATE_ENABLED=False)
class FleaCommentThreadIsolationTests(TestCase):
    def setUp(self):
        self.seller = User.objects.create_user(
            email="flea-thread-seller@waseda.jp",
            password="test-pass-12345",
        )
        self.buyer = User.objects.create_user(
            email="flea-thread-buyer@waseda.jp",
            password="test-pass-12345",
        )
        self.other = User.objects.create_user(
            email="flea-thread-other@waseda.jp",
            password="test-pass-12345",
        )
        self.product = Product.objects.create(
            seller=self.seller,
            name="スレッド隔離テスト商品",
            price=800,
            description="コメント回帰確認",
            category="未分類",
            faculty="政治経済学部",
            handover_campus="waseda",
            status=Product.Status.AVAILABLE,
        )
        self.post = TimelinePost.objects.create(
            author=self.buyer,
            body="timeline sibling post",
        )
        self.client = Client()

    def _create_flea_comment(self, user, body, extra=None):
        self.client.force_login(user)
        payload = {"body": body}
        if extra:
            payload.update(extra)
        return self.client.post(
            f"/api/v1/flea/products/{self.product.pk}/comments/",
            data=json.dumps(payload),
            content_type="application/json",
        )

    def test_create_list_payload_stays_flat_and_legacy(self):
        first = self._create_flea_comment(self.buyer, "まだありますか？")
        self.assertEqual(first.status_code, 201)
        payload = first.json()["comment"]
        self.assertEqual(
            set(payload.keys()),
            {"id", "body", "created_at", "created_at_label", "author"},
        )
        self.assertNotIn("parent_comment_id", payload)
        self.assertNotIn("reply_to", payload)
        self.assertNotIn("is_deleted", payload)
        self.assertNotIn("reply_count", payload)
        self.assertEqual(payload["body"], "まだありますか？")

        stored = Comment.objects.get(pk=payload["id"])
        self.assertEqual(stored.product_id, self.product.pk)
        self.assertIsNone(stored.timeline_post_id)
        self.assertIsNone(stored.parent_comment_id)
        self.assertFalse(stored.is_author_deleted)

        second = self._create_flea_comment(self.other, "興味あります")
        self.assertEqual(second.status_code, 201)

        detail = self.client.get(f"/api/v1/flea/products/{self.product.pk}/")
        self.assertEqual(detail.status_code, 200)
        comments = detail.json()["product"]["comments"]
        self.assertEqual(
            [row["body"] for row in comments],
            ["まだありますか？", "興味あります"],
        )
        self.assertEqual(len(comments), 2)
        for row in comments:
            self.assertEqual(
                set(row.keys()),
                {"id", "body", "created_at", "created_at_label", "author"},
            )

    def test_parent_comment_id_on_flea_create_is_ignored(self):
        timeline_comment = Comment.objects.create(
            timeline_post=self.post,
            author=self.buyer,
            body="timeline parent",
        )
        flea_comment = Comment.objects.create(
            product=self.product,
            author=self.seller,
            body="existing flea comment",
        )
        res = self._create_flea_comment(
            self.buyer,
            "parent_comment_id should not stick",
            extra={"parent_comment_id": timeline_comment.pk},
        )
        self.assertEqual(res.status_code, 201)
        created = Comment.objects.get(pk=res.json()["comment"]["id"])
        self.assertIsNone(created.parent_comment_id)
        self.assertEqual(created.product_id, self.product.pk)
        self.assertIsNone(created.timeline_post_id)
        self.assertFalse(created.is_author_deleted)

        res_flea_parent = self._create_flea_comment(
            self.other,
            "flea parent also ignored",
            extra={"parent_comment_id": flea_comment.pk},
        )
        self.assertEqual(res_flea_parent.status_code, 201)
        created_flea = Comment.objects.get(
            pk=res_flea_parent.json()["comment"]["id"]
        )
        self.assertIsNone(created_flea.parent_comment_id)

    def test_flea_delete_hard_deletes_and_does_not_tombstone(self):
        created = self._create_flea_comment(self.buyer, "削除します").json()[
            "comment"
        ]
        comment_id = created["id"]
        timeline_delete = self.client.delete(
            f"/api/v1/timeline/comments/{comment_id}/"
        )
        self.assertEqual(timeline_delete.status_code, 400)
        self.assertEqual(
            timeline_delete.json()["error"], "not_timeline_comment"
        )
        self.assertTrue(Comment.objects.filter(pk=comment_id).exists())

        deleted = self.client.post(
            reverse("delete_comment", args=[comment_id])
        )
        self.assertEqual(deleted.status_code, 302)
        self.assertFalse(Comment.objects.filter(pk=comment_id).exists())

        detail = self.client.get(f"/api/v1/flea/products/{self.product.pk}/")
        self.assertEqual(detail.json()["product"]["comments"], [])

    def test_orm_parent_on_flea_comment_does_not_thread_or_tombstone(self):
        parent = Comment.objects.create(
            product=self.product,
            author=self.buyer,
            body="orm parent",
        )
        child = Comment.objects.create(
            product=self.product,
            author=self.other,
            body="orm child",
            parent_comment=parent,
        )
        detail = self.client.get(f"/api/v1/flea/products/{self.product.pk}/")
        comments = detail.json()["product"]["comments"]
        self.assertEqual(
            [row["body"] for row in comments],
            ["orm parent", "orm child"],
        )
        for row in comments:
            self.assertNotIn("parent_comment_id", row)
            self.assertNotIn("is_deleted", row)

        self.client.force_login(self.buyer)
        self.client.post(reverse("delete_comment", args=[parent.pk]))
        self.assertFalse(Comment.objects.filter(pk=parent.pk).exists())
        child.refresh_from_db()
        self.assertTrue(Comment.objects.filter(pk=child.pk).exists())
        self.assertIsNone(child.parent_comment_id)
        self.assertEqual(child.body, "orm child")
        self.assertFalse(child.is_author_deleted)
        after = self.client.get(f"/api/v1/flea/products/{self.product.pk}/")
        self.assertEqual(
            [row["body"] for row in after.json()["product"]["comments"]],
            ["orm child"],
        )
