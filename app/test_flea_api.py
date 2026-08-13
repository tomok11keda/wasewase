"""Phase 5 flea JSON API tests."""

from __future__ import annotations

import json
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings

from .bookmark_services import BookmarkServiceError
from .models import ChatRoom, Message, Product, User

_MINIMAL_GIF = (
    b"GIF89a\x01\x00\x01\x00\x80\x00\x00\xff\xff\xff\x00\x00\x00!\xf9\x04"
    b"\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"
)


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
        self.assertIn("user_has_bookmarked", product)
        self.assertFalse(product["user_has_bookmarked"])

    @patch("app.bookmark_services.toggle_product_bookmark", return_value=True)
    def test_product_bookmark_toggle(self, mock_toggle):
        self.client.force_login(self.buyer)
        response = self.client.post(
            f"/api/v1/flea/products/{self.product.pk}/bookmark/"
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        self.assertTrue(response.json()["bookmarked"])
        mock_toggle.assert_called_once_with(self.buyer, self.product.pk)

    @patch(
        "app.bookmark_services.toggle_product_bookmark",
        side_effect=BookmarkServiceError("unavailable"),
    )
    def test_product_bookmark_unavailable(self, mock_toggle):
        self.client.force_login(self.buyer)
        response = self.client.post(
            f"/api/v1/flea/products/{self.product.pk}/bookmark/"
        )
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["error"], "bookmark_unavailable")
        mock_toggle.assert_called_once()

    @patch("app.bookmark_services.is_product_bookmarked", return_value=True)
    def test_product_detail_reflects_bookmark_state(self, mock_is_bookmarked):
        self.client.force_login(self.buyer)
        detail = self.client.get(f"/api/v1/flea/products/{self.product.pk}/")
        self.assertEqual(detail.status_code, 200)
        self.assertTrue(detail.json()["product"]["user_has_bookmarked"])
        mock_is_bookmarked.assert_called_once_with(self.buyer, self.product.pk)

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

        # Idempotent: second complete must not 500
        handover2 = self.client.post(
            f"/api/v1/flea/chats/{room_id}/handover-complete/"
        )
        self.assertEqual(handover2.status_code, 200)
        self.assertEqual(handover2.json()["product_status"], Product.Status.SOLD)
        self.assertTrue(handover2.json()["ok"])

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

    def _make_pending_negotiating_room(self):
        """0036 移行ギャップ再現: 商品は取引中だが deal_status が negotiating。"""
        self.product.status = Product.Status.PENDING
        self.product.buyer = self.buyer
        self.product.save(update_fields=["status", "buyer"])
        return ChatRoom.objects.create(
            product=self.product,
            buyer=self.buyer,
            deal_status=ChatRoom.DealStatus.NEGOTIATING,
        )

    def test_seller_handover_heals_pending_negotiating_room(self):
        room = self._make_pending_negotiating_room()

        self.client.force_login(self.seller)
        detail = self.client.get(f"/api/v1/flea/chats/{room.pk}/")
        self.assertEqual(detail.status_code, 200)
        self.assertTrue(detail.json()["room"]["can_complete_handover"])
        self.assertFalse(detail.json()["room"]["can_confirm_trade"])

        handover = self.client.post(
            f"/api/v1/flea/chats/{room.pk}/handover-complete/"
        )
        self.assertEqual(handover.status_code, 200)
        self.assertEqual(handover.json()["product_status"], Product.Status.SOLD)
        self.product.refresh_from_db()
        room.refresh_from_db()
        self.assertTrue(self.product.is_sold)
        self.assertEqual(room.deal_status, ChatRoom.DealStatus.CONFIRMED)

    def test_negotiating_available_room_cannot_handover(self):
        """値下げ交渉中（available）は受け渡し完了不可。取引開始が必要。"""
        self.client.force_login(self.buyer)
        start = self.client.post(
            f"/api/v1/flea/products/{self.product.pk}/chat/start/"
        )
        room_id = start.json()["room_id"]

        self.client.force_login(self.seller)
        detail = self.client.get(f"/api/v1/flea/chats/{room_id}/")
        self.assertTrue(detail.json()["room"]["can_confirm_trade"])
        self.assertFalse(detail.json()["room"]["can_complete_handover"])
        bad = self.client.post(f"/api/v1/flea/chats/{room_id}/handover-complete/")
        self.assertEqual(bad.status_code, 400)
        self.assertEqual(bad.json()["error"], "not_pending")
        self.product.refresh_from_db()
        self.assertEqual(self.product.status, Product.Status.AVAILABLE)

    def test_handover_rejects_buyer_and_outsider(self):
        self.client.force_login(self.buyer)
        purchase = self.client.post(
            f"/api/v1/flea/products/{self.product.pk}/purchase/"
        )
        room_id = purchase.json()["room_id"]

        buyer_try = self.client.post(
            f"/api/v1/flea/chats/{room_id}/handover-complete/"
        )
        self.assertEqual(buyer_try.status_code, 400)
        self.assertEqual(buyer_try.json()["error"], "not_seller")
        self.product.refresh_from_db()
        self.assertEqual(self.product.status, Product.Status.PENDING)

        outsider = User.objects.create_user(
            email="flea-outsider@waseda.jp",
            password="test-pass-12345",
        )
        self.client.force_login(outsider)
        outsider_try = self.client.post(
            f"/api/v1/flea/chats/{room_id}/handover-complete/"
        )
        self.assertEqual(outsider_try.status_code, 403)
        self.assertEqual(outsider_try.json()["error"], "forbidden")

    def test_handover_does_not_double_complete_and_chat_still_readable(self):
        self.client.force_login(self.buyer)
        purchase = self.client.post(
            f"/api/v1/flea/products/{self.product.pk}/purchase/"
        )
        room_id = purchase.json()["room_id"]
        self.client.post(
            f"/api/v1/flea/chats/{room_id}/messages/send/",
            data=json.dumps({"body": "まだあります"}),
            content_type="application/json",
        )

        self.client.force_login(self.seller)
        first = self.client.post(
            f"/api/v1/flea/chats/{room_id}/handover-complete/"
        )
        self.assertEqual(first.status_code, 200)
        second = self.client.post(
            f"/api/v1/flea/chats/{room_id}/handover-complete/"
        )
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.json()["product_status"], Product.Status.SOLD)

        msgs = self.client.get(f"/api/v1/flea/chats/{room_id}/messages/")
        self.assertEqual(msgs.status_code, 200)
        bodies = [m["body"] for m in msgs.json()["messages"]]
        self.assertTrue(any("まだあります" in b for b in bodies))
        self.assertTrue(
            Message.objects.filter(chat_room_id=room_id, is_system=True).exists()
        )

    def test_exhibit_requires_image(self):
        self.client.force_login(self.seller)
        before = Product.objects.count()
        created = self.client.post(
            "/api/v1/flea/products/",
            data={
                "name": "画像なし出品",
                "price": "800",
                "handover_campus": "toyama",
                "description": "軽量",
                "faculty": "法学部",
            },
        )
        self.assertEqual(created.status_code, 400)
        body = created.json()
        self.assertFalse(body.get("ok", True))
        self.assertEqual(body["error"], "validation_failed")
        self.assertIn("image", body["errors"])
        self.assertIn(
            "商品画像を1枚以上追加してください",
            body["errors"]["image"][0]["message"],
        )
        self.assertEqual(Product.objects.count(), before)

    def test_exhibit_and_delete(self):
        self.client.force_login(self.seller)
        image = SimpleUploadedFile(
            "stand.gif", _MINIMAL_GIF, content_type="image/gif"
        )
        created = self.client.post(
            "/api/v1/flea/products/",
            data={
                "name": "ノートPCスタンド",
                "price": "800",
                "handover_campus": "toyama",
                "description": "軽量",
                "faculty": "法学部",
                "image": image,
            },
        )
        self.assertEqual(created.status_code, 201)
        pk = created.json()["product"]["id"]

        deleted = self.client.post(f"/api/v1/flea/products/{pk}/delete/")
        self.assertEqual(deleted.status_code, 200)
        self.assertFalse(Product.objects.filter(pk=pk).exists())
