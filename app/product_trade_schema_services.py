"""本番 DB で Product / ChatRoom / Message の取引関連スキーマを修復する。"""

from __future__ import annotations

import logging

from django.db import connection
from django.db.utils import OperationalError, ProgrammingError

logger = logging.getLogger(__name__)

PRODUCT_TABLE = "app_product"
CHATROOM_TABLE = "app_chatroom"
MESSAGE_TABLE = "app_message"


def _table_columns(cursor, table: str) -> set[str]:
    if table not in connection.introspection.table_names(cursor):
        return set()
    return {
        column.name
        for column in connection.introspection.get_table_description(cursor, table)
    }


def ensure_product_handover_campus_column() -> None:
    """0035 の handover_campus が無い本番 DB を修復する。"""
    try:
        with connection.cursor() as cursor:
            columns = _table_columns(cursor, PRODUCT_TABLE)
            if not columns:
                logger.warning("Product schema repair skipped: %s missing", PRODUCT_TABLE)
                return
            if "handover_campus" in columns:
                return
            if connection.vendor == "postgresql":
                cursor.execute(
                    f"ALTER TABLE {PRODUCT_TABLE} "
                    "ADD COLUMN IF NOT EXISTS handover_campus varchar(32) NOT NULL DEFAULT ''"
                )
            else:
                cursor.execute(
                    f"ALTER TABLE {PRODUCT_TABLE} "
                    "ADD COLUMN handover_campus varchar(32) NOT NULL DEFAULT ''"
                )
            logger.warning("Added missing %s.handover_campus column", PRODUCT_TABLE)
    except (OperationalError, ProgrammingError) as exc:
        logger.warning("ensure_product_handover_campus_column failed: %s", exc)


def ensure_product_status_pending_sold() -> None:
    """旧 trading / sold_out を pending / sold に揃える。"""
    try:
        with connection.cursor() as cursor:
            columns = _table_columns(cursor, PRODUCT_TABLE)
            if "status" not in columns:
                return
            cursor.execute(
                f"UPDATE {PRODUCT_TABLE} SET status = 'pending' WHERE status = 'trading'"
            )
            cursor.execute(
                f"UPDATE {PRODUCT_TABLE} SET status = 'sold' WHERE status = 'sold_out'"
            )
    except (OperationalError, ProgrammingError) as exc:
        logger.warning("ensure_product_status_pending_sold failed: %s", exc)


def ensure_chatroom_deal_status_column() -> None:
    """0036 の deal_status が無い本番 DB を修復する。"""
    try:
        with connection.cursor() as cursor:
            columns = _table_columns(cursor, CHATROOM_TABLE)
            if not columns:
                return
            if "deal_status" in columns:
                return
            if connection.vendor == "postgresql":
                cursor.execute(
                    f"ALTER TABLE {CHATROOM_TABLE} "
                    "ADD COLUMN IF NOT EXISTS deal_status varchar(20) "
                    "NOT NULL DEFAULT 'negotiating'"
                )
            else:
                cursor.execute(
                    f"ALTER TABLE {CHATROOM_TABLE} "
                    "ADD COLUMN deal_status varchar(20) "
                    "NOT NULL DEFAULT 'negotiating'"
                )
            logger.warning("Added missing %s.deal_status column", CHATROOM_TABLE)
    except (OperationalError, ProgrammingError) as exc:
        logger.warning("ensure_chatroom_deal_status_column failed: %s", exc)


def ensure_message_system_schema() -> None:
    """0036 の is_system / sender NULL を修復する。"""
    try:
        with connection.cursor() as cursor:
            columns = _table_columns(cursor, MESSAGE_TABLE)
            if not columns:
                return
            if "is_system" not in columns:
                if connection.vendor == "postgresql":
                    cursor.execute(
                        f"ALTER TABLE {MESSAGE_TABLE} "
                        "ADD COLUMN IF NOT EXISTS is_system boolean NOT NULL DEFAULT false"
                    )
                else:
                    cursor.execute(
                        f"ALTER TABLE {MESSAGE_TABLE} "
                        "ADD COLUMN is_system bool NOT NULL DEFAULT 0"
                    )
                logger.warning("Added missing %s.is_system column", MESSAGE_TABLE)

            # sender_id を NULL 許可（PostgreSQL）
            if connection.vendor == "postgresql" and "sender_id" in columns:
                cursor.execute(
                    f"""
                    DO $$
                    BEGIN
                        BEGIN
                            ALTER TABLE {MESSAGE_TABLE}
                            ALTER COLUMN sender_id DROP NOT NULL;
                        EXCEPTION
                            WHEN others THEN NULL;
                        END;
                    END $$;
                    """
                )
    except (OperationalError, ProgrammingError) as exc:
        logger.warning("ensure_message_system_schema failed: %s", exc)


def ensure_product_trade_schema() -> None:
    """フリマ取引まわりの不足スキーマをまとめて修復する。"""
    ensure_product_handover_campus_column()
    ensure_product_status_pending_sold()
    ensure_chatroom_deal_status_column()
    ensure_message_system_schema()
