"""Phase 5 flea JSON API tests."""

from __future__ import annotations

import json

from django.test import Client, TestCase, override_settings

from .models import Product, User


@override_settings(BROWSE_MODE_GATE_ENABLED=False)
class FleaApiTests(TestCase):
    def setUp(self):
        self.seller = User.objects.create_user(
            email="flea-seller@waseda.jp",
            password="test-pass-12345",
        )
        self.buyer = User.objects.create_user(
            email="flea-buyer@waseda.jp",
            password="test-pass-12345",
        )
        self.product = Product.objects.create(
            seller=self.seller,
            name="線形代数の教科書",
            price=1200,
            description="ほぼ新品",
            category="未分類",
            faculty="政治経済学部",
            handover_campus="waseda",
            status=Product.Status.AVAILABLE,
        )
        self.client = Client()

    def test_list_and_detail(self):
        response = self.client.get("/api/v1/flea/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(any(p["name"] == "線形代数の教科書" for p in data["products"]))
        self.assertIn("faculty_tabs", data)
        self.assertIn("campus_tabs", data)

        detail = self.client.get(f"/api/v1/flea/products/{self.product.pk}/")
        self.assertEqual(detail.status_code, 200)
        product = detail.json()["product"]
        self.assertEqual(product["name"], "線形代数の教科書")
        self.assertFalse(product["can_purchase"])

    def test_purchase_like_comment_chat(self):
        self.client.force_login(self.buyer)

        like = self.client.post(f"/api/v1/flea/products/{self.product.pk}/like/")
        self.assertEqual(like.status_code, 200)
        self.assertTrue(like.json()["liked"])

        comment = self.client.post(
            f"/api/v1/flea/products/{self.product.pk}/comments/",
            data=json.dumps({"body": "まだありますか？"}),
            content_type="application/json",
        )
        self.assertEqual(comment.status_code, 201)

        detail = self.client.get(f"/api/v1/flea/products/{self.product.pk}/")
        self.assertTrue(detail.json()["product"]["can_purchase"])

        purchase = self.client.post(
            f"/api/v1/flea/products/{self.product.pk}/purchase/"
        )
        self.assertEqual(purchase.status_code, 200)
        room_id = purchase.json()["room_id"]
        self.assertTrue(room_id)

        self.product.refresh_from_db()
        self.assertEqual(self.product.status, Product.Status.PENDING)
        self.assertEqual(self.product.buyer_id, self.buyer.id)

        chat = self.client.get(f"/api/v1/flea/chats/{room_id}/")
        self.assertEqual(chat.status_code, 200)
        self.assertFalse(chat.json()["room"]["is_seller"])

        send = self.client.post(
            f"/api/v1/flea/chats/{room_id}/messages/send/",
            data=json.dumps({"body": "受け渡しは早稲田で"}),
            content_type="application/json",
        )
        self.assertEqual(send.status_code, 201)

        msgs = self.client.get(f"/api/v1/flea/chats/{room_id}/messages/")
        self.assertEqual(msgs.status_code, 200)
        self.assertTrue(
            any("受け渡しは早稲田で" in m["body"] for m in msgs.json()["messages"])
        )

        # Seller completes handover
        self.client.force_login(self.seller)
        handover = self.client.post(
            f"/api/v1/flea/chats/{room_id}/handover-complete/"
        )
        self.assertEqual(handover.status_code, 200)
        self.assertEqual(handover.json()["product_status"], Product.Status.SOLD)
        self.product.refresh_from_db()
        self.assertTrue(self.product.is_sold)

    def test_cannot_buy_own_product(self):
        self.client.force_login(self.seller)
        response = self.client.post(
            f"/api/v1/flea/products/{self.product.pk}/purchase/"
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "own_product")

    def test_negotiate_then_confirm(self):
        self.client.force_login(self.buyer)
        start = self.client.post(
            f"/api/v1/flea/products/{self.product.pk}/chat/start/"
        )
        self.assertEqual(start.status_code, 200)
        room_id = start.json()["room_id"]
        self.product.refresh_from_db()
        self.assertEqual(self.product.status, Product.Status.AVAILABLE)

        self.client.force_login(self.seller)
        confirm = self.client.post(f"/api/v1/flea/chats/{room_id}/confirm/")
        self.assertEqual(confirm.status_code, 200)
        self.assertEqual(confirm.json()["product_status"], Product.Status.PENDING)

    def test_exhibit_and_delete(self):
        self.client.force_login(self.seller)
        created = self.client.post(
            "/api/v1/flea/products/",
            data={
                "name": "ノートPCスタンド",
                "price": "800",
                "handover_campus": "toyama",
                "description": "軽量",
                "faculty": "法学部",
            },
        )
        self.assertEqual(created.status_code, 201)
        pk = created.json()["product"]["id"]

        deleted = self.client.post(f"/api/v1/flea/products/{pk}/delete/")
        self.assertEqual(deleted.status_code, 200)
        self.assertFalse(Product.objects.filter(pk=pk).exists())
