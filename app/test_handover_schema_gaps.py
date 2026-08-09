"""Reproduce / guard complete_product_handover under SQLite schema gaps."""
from django.contrib.auth import get_user_model
from django.db import connection
from django.db.utils import OperationalError
from django.test import TransactionTestCase
from django.urls import reverse

from app.models import ChatRoom, Message, Product
from app.product_trade_schema_services import (
    MESSAGE_TABLE,
    ensure_message_system_schema,
)
from app.trade_chat_services import post_system_message


User = get_user_model()


def _pragma_cols():
    with connection.cursor() as c:
        c.execute(f"PRAGMA table_info({MESSAGE_TABLE})")
        return {r[1]: {"notnull": r[3], "type": r[2]} for r in c.fetchall()}


def _make_pending_trade(*, email_prefix: str):
    seller = User.objects.create_user(
        email=f"{email_prefix}-seller@ex.com", password="x"
    )
    buyer = User.objects.create_user(
        email=f"{email_prefix}-buyer@ex.com", password="x"
    )
    product = Product.objects.create(
        seller=seller,
        name="gap",
        price=100,
        description="",
        category="x",
        faculty="商学部",
        status=Product.Status.PENDING,
        buyer=buyer,
    )
    room = ChatRoom.objects.create(
        product=product,
        buyer=buyer,
        deal_status=ChatRoom.DealStatus.CONFIRMED,
    )
    return seller, buyer, product, room


class HandoverSchemaGapTests(TransactionTestCase):
    """Simulate production SQLite gaps that migrations sometimes miss."""

    def test_healthy_handover_ok(self):
        seller, _buyer, product, room = _make_pending_trade(email_prefix="healthy")
        self.client.force_login(seller)
        response = self.client.post(
            reverse("complete_product_handover", args=[room.pk])
        )
        product.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(product.status, Product.Status.SOLD)
        self.assertTrue(
            Message.objects.filter(
                chat_room=room, is_system=True, sender__isnull=True
            ).exists()
        )

    def test_missing_is_system_is_repaired(self):
        if connection.vendor != "sqlite":
            self.skipTest("SQLite-only gap simulation")

        with connection.cursor() as c:
            c.execute("PRAGMA foreign_keys=OFF")
            c.execute(
                f"""
                CREATE TABLE {MESSAGE_TABLE}_no_sys (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    body TEXT NOT NULL,
                    created_at DATETIME NOT NULL,
                    chat_room_id BIGINT NOT NULL
                        REFERENCES app_chatroom (id) DEFERRABLE INITIALLY DEFERRED,
                    sender_id BIGINT NULL
                        REFERENCES app_user (id) DEFERRABLE INITIALLY DEFERRED
                )
                """
            )
            c.execute(
                f"""
                INSERT INTO {MESSAGE_TABLE}_no_sys
                    (id, body, created_at, chat_room_id, sender_id)
                SELECT id, body, created_at, chat_room_id, sender_id
                FROM {MESSAGE_TABLE}
                """
            )
            c.execute(f"DROP TABLE {MESSAGE_TABLE}")
            c.execute(
                f"ALTER TABLE {MESSAGE_TABLE}_no_sys RENAME TO {MESSAGE_TABLE}"
            )
            c.execute("PRAGMA foreign_keys=ON")

        self.assertNotIn("is_system", _pragma_cols())
        seller, _buyer, product, room = _make_pending_trade(email_prefix="nosys")
        with self.assertRaises(OperationalError):
            post_system_message(room, "should fail without is_system")

        ensure_message_system_schema()
        self.assertIn("is_system", _pragma_cols())

        self.client.force_login(seller)
        response = self.client.post(
            reverse("complete_product_handover", args=[room.pk])
        )
        product.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(product.status, Product.Status.SOLD)

    def test_sender_not_null_is_repaired_on_sqlite(self):
        """Root cause fix: rebuild app_message so sender_id allows NULL."""
        if connection.vendor != "sqlite":
            self.skipTest("SQLite-only gap simulation")

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

        self.assertEqual(_pragma_cols()["sender_id"]["notnull"], 1)

        ensure_message_system_schema()
        self.assertEqual(
            _pragma_cols()["sender_id"]["notnull"],
            0,
            "ensure_message_system_schema should make sender_id nullable on SQLite",
        )

        seller, _buyer, product, room = _make_pending_trade(email_prefix="sendernn")
        self.client.force_login(seller)
        response = self.client.post(
            reverse("complete_product_handover", args=[room.pk])
        )
        product.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(product.status, Product.Status.SOLD)
        self.assertTrue(
            Message.objects.filter(
                chat_room=room, is_system=True, sender__isnull=True
            ).exists()
        )


class HandoverIdempotentAndResilienceTests(TransactionTestCase):
    def test_second_handover_same_buyer_is_ok(self):
        from app.trade_chat_services import complete_handover_by_seller

        seller, _buyer, product, room = _make_pending_trade(email_prefix="idem")
        complete_handover_by_seller(room, seller)
        product.refresh_from_db()
        self.assertEqual(product.status, Product.Status.SOLD)

        again = complete_handover_by_seller(room, seller)
        self.assertEqual(again.status, Product.Status.SOLD)

    def test_system_message_failure_keeps_sold(self):
        from django.db import IntegrityError
        from unittest.mock import patch

        from app.trade_chat_services import complete_handover_by_seller

        seller, _buyer, product, room = _make_pending_trade(email_prefix="sysfail")
        with patch(
            "app.trade_chat_services.post_system_message",
            side_effect=IntegrityError("sender_id NOT NULL"),
        ):
            result = complete_handover_by_seller(room, seller)
        product.refresh_from_db()
        self.assertEqual(result.status, Product.Status.SOLD)
        self.assertEqual(product.status, Product.Status.SOLD)
