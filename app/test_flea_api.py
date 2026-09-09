"""Phase 5 flea JSON API tests."""

from __future__ import annotations

import json
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from .bookmark_services import BookmarkServiceError
from .models import (
    ChatRoom,
    ChatRoomMembership,
    Comment,
    Message,
    Notification,
    Product,
    TradeMessage,
    User,
)

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

    def test_anonymous_cannot_create_comment(self):
        res = self.client.post(
            f"/api/v1/flea/products/{self.product.pk}/comments/",
            data=json.dumps({"body": "匿名でコメントします"}),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 401)
        self.assertEqual(res.json()["error"], "unauthorized")
        self.assertFalse(
            Comment.objects.filter(product=self.product).exists()
        )
        self.assertFalse(
            Notification.objects.filter(recipient=self.seller).exists()
        )

    def test_authenticated_comment_notifies_seller(self):
        self.client.force_login(self.buyer)
        res = self.client.post(
            f"/api/v1/flea/products/{self.product.pk}/comments/",
            data=json.dumps({"body": "まだありますか？"}),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 201)
        data = res.json()
        self.assertTrue(data["ok"])
        comment = Comment.objects.get(product=self.product, body="まだありますか？")
        self.assertEqual(comment.author_id, self.buyer.pk)
        self.assertEqual(data["comment"]["id"], comment.pk)
        self.assertEqual(data["comment"]["body"], "まだありますか？")
        notes = Notification.objects.filter(recipient=self.seller)
        self.assertEqual(notes.count(), 1)
        self.assertIn("コメント", notes.get().message)

    def test_seller_comment_does_not_notify_self(self):
        self.client.force_login(self.seller)
        res = self.client.post(
            f"/api/v1/flea/products/{self.product.pk}/comments/",
            data=json.dumps({"body": "出品者からの補足です"}),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 201)
        comment = Comment.objects.get(
            product=self.product, body="出品者からの補足です"
        )
        self.assertEqual(comment.author_id, self.seller.pk)
        self.assertFalse(
            Notification.objects.filter(recipient=self.seller).exists()
        )

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

    def test_cannot_delete_product_with_negotiation_chat(self):
        self.client.force_login(self.buyer)
        start = self.client.post(
            f"/api/v1/flea/products/{self.product.pk}/chat/start/"
        )
        self.assertEqual(start.status_code, 200)
        room_id = start.json()["room_id"]

        self.client.force_login(self.seller)
        detail = self.client.get(f"/api/v1/flea/products/{self.product.pk}/")
        self.assertEqual(detail.status_code, 200)
        self.assertFalse(detail.json()["product"]["can_delete"])

        deleted = self.client.post(
            f"/api/v1/flea/products/{self.product.pk}/delete/"
        )
        self.assertEqual(deleted.status_code, 400)
        self.assertEqual(deleted.json()["error"], "has_trade_history")
        self.assertTrue(Product.objects.filter(pk=self.product.pk).exists())
        self.assertTrue(ChatRoom.objects.filter(pk=room_id).exists())

    def test_cannot_delete_pending_or_sold_product(self):
        self.client.force_login(self.buyer)
        buy = self.client.post(
            f"/api/v1/flea/products/{self.product.pk}/purchase/"
        )
        self.assertEqual(buy.status_code, 200)
        room_id = buy.json()["room_id"]

        self.client.force_login(self.seller)
        pending_delete = self.client.post(
            f"/api/v1/flea/products/{self.product.pk}/delete/"
        )
        self.assertEqual(pending_delete.status_code, 400)
        self.assertEqual(pending_delete.json()["error"], "pending")
        self.assertTrue(Product.objects.filter(pk=self.product.pk).exists())

        handover = self.client.post(
            f"/api/v1/flea/chats/{room_id}/handover-complete/"
        )
        self.assertEqual(handover.status_code, 200)
        self.product.refresh_from_db()
        self.assertTrue(self.product.is_sold)

        sold_delete = self.client.post(
            f"/api/v1/flea/products/{self.product.pk}/delete/"
        )
        self.assertEqual(sold_delete.status_code, 400)
        self.assertEqual(sold_delete.json()["error"], "sold")
        self.assertTrue(Product.objects.filter(pk=self.product.pk).exists())
        self.assertTrue(ChatRoom.objects.filter(pk=room_id).exists())
        self.assertTrue(Message.objects.filter(chat_room_id=room_id).exists())


@override_settings(BROWSE_MODE_GATE_ENABLED=True, WASE_REACT_SPA=False)
class FleaCommentBrowseModeAuthTests(TestCase):
    def setUp(self):
        self.seller = User.objects.create_user(
            email="flea-browse-seller@waseda.jp",
            password="test-pass-12345",
        )
        self.product = Product.objects.create(
            seller=self.seller,
            name="閲覧モード教科書",
            price=800,
            description="コメント投稿不可確認",
            category="未分類",
            faculty="政治経済学部",
            handover_campus="waseda",
            status=Product.Status.AVAILABLE,
        )
        self.client = Client()

    def test_browse_mode_anonymous_cannot_create_comment(self):
        enter = self.client.get(reverse("enter_browse_mode"))
        self.assertEqual(enter.status_code, 302)
        detail = self.client.get(f"/api/v1/flea/products/{self.product.pk}/")
        self.assertEqual(detail.status_code, 200)

        res = self.client.post(
            f"/api/v1/flea/products/{self.product.pk}/comments/",
            data=json.dumps({"body": "閲覧モードから投稿"}),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 401)
        self.assertEqual(res.json()["error"], "unauthorized")
        self.assertFalse(
            Comment.objects.filter(product=self.product).exists()
        )
        self.assertFalse(
            Notification.objects.filter(recipient=self.seller).exists()
        )


_TRADE_STATE_ORACLE_ERRORS = frozenset(
    {"not_seller", "not_negotiating", "not_available"}
)


@override_settings(BROWSE_MODE_GATE_ENABLED=False)
class TradeChatKindAclTests(TestCase):
    """Trade Chat は kind=PRODUCT + participant ACL を business validation より先に見る。"""

    def setUp(self):
        self.seller = User.objects.create_user(
            email="trade-acl-seller@waseda.jp",
            password="test-pass-12345",
        )
        self.buyer = User.objects.create_user(
            email="trade-acl-buyer@waseda.jp",
            password="test-pass-12345",
        )
        self.member = User.objects.create_user(
            email="trade-acl-member@waseda.jp",
            password="test-pass-12345",
        )
        self.outsider = User.objects.create_user(
            email="trade-acl-outsider@waseda.jp",
            password="test-pass-12345",
        )
        self.product = Product.objects.create(
            seller=self.seller,
            name="ACL教科書",
            price=1500,
            description="desc",
            category="未分類",
            faculty="政治経済学部",
            handover_campus="waseda",
            status=Product.Status.AVAILABLE,
        )
        self.client = Client()

    def _group_room(self, user):
        room = ChatRoom.objects.create(
            kind=ChatRoom.Kind.GROUP,
            name="security-group",
            created_by=user,
        )
        ChatRoomMembership.objects.create(
            room=room,
            user=user,
            role=ChatRoomMembership.Role.OWNER,
        )
        return room

    def _course_room(self, user):
        room = ChatRoom.objects.create(
            kind=ChatRoom.Kind.COURSE,
            name="security-course",
            created_by=user,
        )
        ChatRoomMembership.objects.create(
            room=room,
            user=user,
            role=ChatRoomMembership.Role.MEMBER,
        )
        return room

    def _negotiating_product_room(self):
        return ChatRoom.objects.create(
            product=self.product,
            buyer=self.buyer,
            kind=ChatRoom.Kind.PRODUCT,
            deal_status=ChatRoom.DealStatus.NEGOTIATING,
        )

    def _assert_not_state_oracle(self, response):
        self.assertNotEqual(response.status_code, 500)
        content_type = response.headers.get("Content-Type", "")
        if "application/json" in content_type:
            payload = response.json()
            self.assertNotIn(payload.get("error"), _TRADE_STATE_ORACLE_ERRORS)
            body = json.dumps(payload)
            self.assertNotIn("secret-group-body", body)
            self.assertNotIn("secret-course-body", body)

    def test_wrong_kind_group_detail_is_404(self):
        room = self._group_room(self.member)
        Message.objects.create(
            chat_room=room, sender=self.member, body="secret-group-body"
        )
        self.client.force_login(self.member)
        res = self.client.get(f"/api/v1/flea/chats/{room.pk}/")
        self.assertEqual(res.status_code, 404)
        self._assert_not_state_oracle(res)

    def test_wrong_kind_course_detail_is_404(self):
        room = self._course_room(self.member)
        self.client.force_login(self.member)
        res = self.client.get(f"/api/v1/flea/chats/{room.pk}/")
        self.assertEqual(res.status_code, 404)
        self.assertNotEqual(res.status_code, 500)

    def test_wrong_kind_messages_do_not_leak_bodies(self):
        group = self._group_room(self.member)
        course = self._course_room(self.member)
        Message.objects.create(
            chat_room=group, sender=self.member, body="secret-group-body"
        )
        Message.objects.create(
            chat_room=course, sender=self.member, body="secret-course-body"
        )
        self.client.force_login(self.member)
        for room in (group, course):
            for suffix in ("", "?before=1", "?after=1"):
                res = self.client.get(
                    f"/api/v1/flea/chats/{room.pk}/messages/{suffix}"
                )
                self.assertEqual(res.status_code, 404)
                self._assert_not_state_oracle(res)

    def test_wrong_kind_send_does_not_create_message(self):
        group = self._group_room(self.member)
        course = self._course_room(self.member)
        self.client.force_login(self.member)
        for room in (group, course):
            before_messages = Message.objects.count()
            before_trade = TradeMessage.objects.count()
            before_notes = Notification.objects.count()
            res = self.client.post(
                f"/api/v1/flea/chats/{room.pk}/messages/send/",
                data=json.dumps({"body": "cross-kind leak"}),
                content_type="application/json",
            )
            self.assertEqual(res.status_code, 404)
            self.assertNotEqual(res.status_code, 500)
            self.assertEqual(Message.objects.count(), before_messages)
            self.assertEqual(TradeMessage.objects.count(), before_trade)
            self.assertEqual(Notification.objects.count(), before_notes)

    def test_wrong_kind_confirm_is_404_without_mutation(self):
        group = self._group_room(self.member)
        course = self._course_room(self.member)
        self.client.force_login(self.member)
        for room in (group, course):
            res = self.client.post(f"/api/v1/flea/chats/{room.pk}/confirm/")
            self.assertEqual(res.status_code, 404)
            self._assert_not_state_oracle(res)
            self.product.refresh_from_db()
            self.assertEqual(self.product.status, Product.Status.AVAILABLE)

    def test_wrong_kind_handover_api_and_classic_are_404(self):
        group = self._group_room(self.member)
        course = self._course_room(self.member)
        self.client.force_login(self.member)
        for room in (group, course):
            api = self.client.post(
                f"/api/v1/flea/chats/{room.pk}/handover-complete/"
            )
            self.assertEqual(api.status_code, 404)
            self._assert_not_state_oracle(api)
            classic = self.client.post(
                reverse("complete_product_handover", args=[room.pk])
            )
            self.assertEqual(classic.status_code, 404)
            self.product.refresh_from_db()
            self.assertEqual(self.product.status, Product.Status.AVAILABLE)

    def test_outsider_product_confirm_is_acl_first_regardless_of_state(self):
        room = self._negotiating_product_room()
        self.client.force_login(self.outsider)
        states = [
            (Product.Status.AVAILABLE, ChatRoom.DealStatus.NEGOTIATING),
            (Product.Status.AVAILABLE, ChatRoom.DealStatus.CONFIRMED),
            (Product.Status.PENDING, ChatRoom.DealStatus.CONFIRMED),
            (Product.Status.SOLD, ChatRoom.DealStatus.CLOSED),
        ]
        for product_status, deal_status in states:
            self.product.status = product_status
            if product_status == Product.Status.PENDING:
                self.product.buyer = self.buyer
            elif product_status == Product.Status.AVAILABLE:
                self.product.buyer = None
            self.product.save(update_fields=["status", "buyer"])
            room.deal_status = deal_status
            room.save(update_fields=["deal_status", "updated_at"])

            res = self.client.post(f"/api/v1/flea/chats/{room.pk}/confirm/")
            self.assertEqual(res.status_code, 403, msg=(product_status, deal_status))
            self.assertEqual(res.json()["error"], "forbidden")
            self._assert_not_state_oracle(res)
            self.product.refresh_from_db()
            self.assertEqual(self.product.status, product_status)
            room.refresh_from_db()
            self.assertEqual(room.deal_status, deal_status)

    def test_buyer_confirm_still_returns_not_seller_after_acl(self):
        room = self._negotiating_product_room()
        self.client.force_login(self.buyer)
        res = self.client.post(f"/api/v1/flea/chats/{room.pk}/confirm/")
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["error"], "not_seller")
        self.product.refresh_from_db()
        self.assertEqual(self.product.status, Product.Status.AVAILABLE)

    def test_valid_seller_confirm_still_succeeds(self):
        room = self._negotiating_product_room()
        self.client.force_login(self.seller)
        res = self.client.post(f"/api/v1/flea/chats/{room.pk}/confirm/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["product_status"], Product.Status.PENDING)
        self.product.refresh_from_db()
        self.assertEqual(self.product.status, Product.Status.PENDING)

    def test_valid_participant_detail_messages_send(self):
        room = self._negotiating_product_room()
        self.client.force_login(self.buyer)
        detail = self.client.get(f"/api/v1/flea/chats/{room.pk}/")
        self.assertEqual(detail.status_code, 200)
        send = self.client.post(
            f"/api/v1/flea/chats/{room.pk}/messages/send/",
            data=json.dumps({"body": "受け渡し希望"}),
            content_type="application/json",
        )
        self.assertEqual(send.status_code, 201)
        msgs = self.client.get(f"/api/v1/flea/chats/{room.pk}/messages/")
        self.assertEqual(msgs.status_code, 200)
        self.assertTrue(
            any("受け渡し希望" in m["body"] for m in msgs.json()["messages"])
        )
        older = self.client.get(
            f"/api/v1/flea/chats/{room.pk}/messages/?before={msgs.json()['messages'][0]['id']}"
        )
        self.assertEqual(older.status_code, 200)
        newer = self.client.get(
            f"/api/v1/flea/chats/{room.pk}/messages/?after=0"
        )
        self.assertEqual(newer.status_code, 200)

    def test_unauthorized_product_send_still_denied(self):
        room = self._negotiating_product_room()
        self.client.force_login(self.outsider)
        before = Message.objects.filter(chat_room=room).count()
        res = self.client.post(
            f"/api/v1/flea/chats/{room.pk}/messages/send/",
            data=json.dumps({"body": "outsider leak"}),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 403)
        self.assertEqual(Message.objects.filter(chat_room=room).count(), before)

    def test_product_null_room_is_404(self):
        room = ChatRoom.objects.create(
            kind=ChatRoom.Kind.PRODUCT,
            product=None,
            buyer=self.buyer,
        )
        self.client.force_login(self.buyer)
        res = self.client.get(f"/api/v1/flea/chats/{room.pk}/")
        self.assertEqual(res.status_code, 404)

    def test_nonexistent_room_is_404_not_500(self):
        missing = 9_999_999
        self.client.force_login(self.buyer)
        paths = [
            (self.client.get, f"/api/v1/flea/chats/{missing}/"),
            (self.client.get, f"/api/v1/flea/chats/{missing}/messages/"),
            (self.client.post, f"/api/v1/flea/chats/{missing}/messages/send/"),
            (self.client.post, f"/api/v1/flea/chats/{missing}/confirm/"),
            (self.client.post, f"/api/v1/flea/chats/{missing}/handover-complete/"),
        ]
        for method, path in paths:
            if method is self.client.post:
                res = method(
                    path, data=json.dumps({}), content_type="application/json"
                )
            else:
                res = method(path)
            self.assertEqual(res.status_code, 404, msg=path)
            self.assertNotEqual(res.status_code, 500)

    def test_classic_wrong_kind_confirm_send_handover_are_safe_deny(self):
        rooms = (self._group_room(self.member), self._course_room(self.member))
        self.client.force_login(self.member)
        for room in rooms:
            Message.objects.create(
                chat_room=room, sender=self.member, body="secret-group-body"
            )
            before_messages = Message.objects.count()
            confirm = self.client.post(
                reverse("confirm_product_trade", args=[room.pk])
            )
            self.assertEqual(confirm.status_code, 404)
            send = self.client.post(
                reverse("send_chat_message", args=[room.pk]),
                {"body": "classic cross-kind"},
            )
            self.assertEqual(send.status_code, 404)
            messages_poll = self.client.get(
                reverse("chat_room_messages", args=[room.pk])
            )
            self.assertEqual(messages_poll.status_code, 404)
            handover = self.client.post(
                reverse("complete_product_handover", args=[room.pk])
            )
            self.assertEqual(handover.status_code, 404)
            self.assertEqual(Message.objects.count(), before_messages)
            self.product.refresh_from_db()
            self.assertEqual(self.product.status, Product.Status.AVAILABLE)

    def test_classic_outsider_confirm_acl_first(self):
        room = self._negotiating_product_room()
        self.client.force_login(self.outsider)
        res = self.client.post(reverse("confirm_product_trade", args=[room.pk]))
        self.assertEqual(res.status_code, 302)
        self.assertEqual(
            res["Location"], reverse("product_detail", args=[self.product.pk])
        )
        self.product.refresh_from_db()
        self.assertEqual(self.product.status, Product.Status.AVAILABLE)
        room.refresh_from_db()
        self.assertEqual(room.deal_status, ChatRoom.DealStatus.NEGOTIATING)

    def test_classic_valid_seller_confirm_and_handover(self):
        room = self._negotiating_product_room()
        self.client.force_login(self.seller)
        confirm = self.client.post(reverse("confirm_product_trade", args=[room.pk]))
        self.assertEqual(confirm.status_code, 302)
        self.product.refresh_from_db()
        self.assertEqual(self.product.status, Product.Status.PENDING)
        handover = self.client.post(
            reverse("complete_product_handover", args=[room.pk])
        )
        self.assertEqual(handover.status_code, 302)
        self.product.refresh_from_db()
        self.assertTrue(self.product.is_sold)
