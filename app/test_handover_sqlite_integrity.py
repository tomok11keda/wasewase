"""Reproduce: SQLite sender_id NOT NULL must not roll back sold status."""
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import Client, TransactionTestCase

from app.models import ChatRoom, Product
from app.product_trade_schema_services import MESSAGE_TABLE
from app.trade_chat_services import complete_handover_by_seller, post_system_message


User = get_user_model()


def _force_sender_not_null():
    with connection.cursor() as c:
        c.execute("PRAGMA foreign_keys=OFF")
        c.execute(
            f"""
            CREATE TABLE {MESSAGE_TABLE}_nn (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                body TEXT NOT NULL,
                created_at DATETIME NOT NULL,
                chat_room_id BIGINT NOT NULL
                    REFERENCES app_chatroom (id) DEFERRABLE INITIALLY DEFERRED,
                sender_id BIGINT NOT NULL
                    REFERENCES app_user (id) DEFERRABLE INITIALLY DEFERRED,
                is_system bool NOT NULL DEFAULT 0
            )
            """
        )
        c.execute(
            f"""
            INSERT INTO {MESSAGE_TABLE}_nn
                (id, body, created_at, chat_room_id, sender_id, is_system)
            SELECT id, body, created_at, chat_room_id, sender_id,
                   COALESCE(is_system, 0)
            FROM {MESSAGE_TABLE}
            WHERE sender_id IS NOT NULL
            """
        )
        c.execute(f"DROP TABLE {MESSAGE_TABLE}")
        c.execute(f"ALTER TABLE {MESSAGE_TABLE}_nn RENAME TO {MESSAGE_TABLE}")
        c.execute("PRAGMA foreign_keys=ON")


def _make_pending(*, prefix: str):
    seller = User.objects.create_user(email=f"{prefix}-s@ex.com", password="x")
    buyer = User.objects.create_user(email=f"{prefix}-b@ex.com", password="x")
    product = Product.objects.create(
        seller=seller,
        name="repro",
        price=100,
        description="",
        category="x",
        status=Product.Status.PENDING,
        buyer=buyer,
    )
    room = ChatRoom.objects.create(
        product=product,
        buyer=buyer,
        deal_status=ChatRoom.DealStatus.CONFIRMED,
    )
    return seller, buyer, product, room


class RealSqliteSenderNotNullHandoverTests(TransactionTestCase):
    def test_complete_handover_keeps_sold_when_system_message_fails(self):
        """Gap present: sale must commit even if system message cannot insert."""
        if connection.vendor != "sqlite":
            self.skipTest("SQLite-only")

        _force_sender_not_null()
        seller, _buyer, product, room = _make_pending(prefix="noensure")

        with self.assertRaises(Exception):
            post_system_message(room, "should fail")

        # Block schema repair so system message still fails after sold commit
        with patch(
            "app.product_trade_schema_services.ensure_message_system_schema",
            side_effect=lambda: None,
        ):
            result = complete_handover_by_seller(room, seller)

        product.refresh_from_db()
        self.assertEqual(result.status, Product.Status.SOLD)
        self.assertTrue(product.is_sold)

    def test_api_handover_with_sender_not_null_gap(self):
        """API path calls ensure first — should repair then succeed."""
        if connection.vendor != "sqlite":
            self.skipTest("SQLite-only")

        _force_sender_not_null()
        seller, _buyer, product, room = _make_pending(prefix="apigap")

        client = Client()
        client.force_login(seller)
        response = client.post(f"/api/v1/flea/chats/{room.pk}/handover-complete/")

        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(response.json().get("ok"))
        product.refresh_from_db()
        self.assertEqual(product.status, Product.Status.SOLD)
        self.assertEqual(response.json().get("product_status"), Product.Status.SOLD)
        self.assertTrue(response.json()["room"]["product"]["is_sold"])


class ApiHandoverWhenEnsureFailsTests(TransactionTestCase):
    def test_api_still_succeeds_if_schema_unrepaired(self):
        """Even if ensure cannot repair sender_id, sold must succeed (HTTP 200)."""
        if connection.vendor != "sqlite":
            self.skipTest("SQLite-only")

        _force_sender_not_null()
        seller, _buyer, product, room = _make_pending(prefix="ensurefail")

        client = Client()
        client.force_login(seller)
        with patch(
            "app.flea_api_views.ensure_product_trade_schema",
            side_effect=lambda: None,
        ), patch(
            "app.product_trade_schema_services.ensure_message_system_schema",
            side_effect=lambda: None,
        ):
            response = client.post(
                f"/api/v1/flea/chats/{room.pk}/handover-complete/"
            )

        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(response.json().get("ok"))
        product.refresh_from_db()
        self.assertTrue(product.is_sold)
        self.assertEqual(response.json().get("product_status"), Product.Status.SOLD)
