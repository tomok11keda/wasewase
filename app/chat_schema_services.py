"""本番 DB でマイグレーション 0026 が未適用のときの ChatRoom 系スキーマ修復。"""

from __future__ import annotations

import logging

from django.contrib.auth import get_user_model
from django.db import connection
from django.db.utils import OperationalError, ProgrammingError

logger = logging.getLogger(__name__)

CHATROOM_TABLE = "app_chatroom"


def _chatroom_column_names(cursor) -> set[str]:
    return {
        column.name
        for column in connection.introspection.get_table_description(cursor, CHATROOM_TABLE)
    }


def _column_allows_null(cursor, column_name: str) -> bool | None:
    for column in connection.introspection.get_table_description(cursor, CHATROOM_TABLE):
        if column.name == column_name:
            return column.null_ok
    return None


def _add_created_by_fk_postgresql(cursor, user_table: str) -> None:
    cursor.execute(
        f"""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'app_chatroom_created_by_id_fk'
            ) THEN
                ALTER TABLE app_chatroom
                ADD CONSTRAINT app_chatroom_created_by_id_fk
                FOREIGN KEY (created_by_id)
                REFERENCES {user_table}(id)
                ON DELETE SET NULL
                DEFERRABLE INITIALLY DEFERRED;
            END IF;
        END $$;
        """
    )


def ensure_chatroom_group_chat_schema() -> None:
    """app_chatroom に 0026 で追加された列が無い本番 DB を修復する。"""
    try:
        with connection.cursor() as cursor:
            if CHATROOM_TABLE not in connection.introspection.table_names(cursor):
                logger.warning("ChatRoom schema repair skipped: %s does not exist", CHATROOM_TABLE)
                return

            columns = _chatroom_column_names(cursor)
            user_table = get_user_model()._meta.db_table

            if connection.vendor == "postgresql":
                if "kind" not in columns:
                    cursor.execute(
                        "ALTER TABLE app_chatroom "
                        "ADD COLUMN IF NOT EXISTS kind varchar(20) NOT NULL DEFAULT 'product'"
                    )
                    logger.warning("Added missing app_chatroom.kind column")
                if "name" not in columns:
                    cursor.execute(
                        "ALTER TABLE app_chatroom "
                        "ADD COLUMN IF NOT EXISTS name varchar(120) NOT NULL DEFAULT ''"
                    )
                    logger.warning("Added missing app_chatroom.name column")
                if "created_by_id" not in columns:
                    cursor.execute(
                        "ALTER TABLE app_chatroom "
                        "ADD COLUMN IF NOT EXISTS created_by_id bigint NULL"
                    )
                    _add_created_by_fk_postgresql(cursor, user_table)
                    logger.warning("Added missing app_chatroom.created_by_id column")

                if _column_allows_null(cursor, "buyer_id") is False:
                    cursor.execute(
                        "ALTER TABLE app_chatroom ALTER COLUMN buyer_id DROP NOT NULL"
                    )
                    logger.warning("Made app_chatroom.buyer_id nullable")
                if _column_allows_null(cursor, "product_id") is False:
                    cursor.execute(
                        "ALTER TABLE app_chatroom ALTER COLUMN product_id DROP NOT NULL"
                    )
                    logger.warning("Made app_chatroom.product_id nullable")

                cursor.execute(
                    "CREATE INDEX IF NOT EXISTS app_chatroom_kind_idx ON app_chatroom (kind)"
                )
                return

            if "kind" not in columns:
                cursor.execute(
                    "ALTER TABLE app_chatroom "
                    "ADD COLUMN kind varchar(20) NOT NULL DEFAULT 'product'"
                )
            if "name" not in columns:
                cursor.execute(
                    "ALTER TABLE app_chatroom "
                    "ADD COLUMN name varchar(120) NOT NULL DEFAULT ''"
                )
            if "created_by_id" not in columns:
                cursor.execute("ALTER TABLE app_chatroom ADD COLUMN created_by_id bigint NULL")

    except (OperationalError, ProgrammingError) as exc:
        message = str(exc).lower()
        if "duplicate column" in message or "already exists" in message:
            return
        logger.warning("ChatRoom schema repair failed: %s", exc)
    except Exception as exc:
        logger.warning("ChatRoom schema repair failed: %s", exc)


def ensure_chatroom_invitation_table() -> None:
    """ChatRoomInvitation テーブルが無い本番 DB を修復する。"""
    table = "app_chatroominvitation"
    try:
        with connection.cursor() as cursor:
            tables = connection.introspection.table_names(cursor)
            if table in tables:
                return
            user_table = get_user_model()._meta.db_table
            if connection.vendor == "postgresql":
                cursor.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS {table} (
                        id bigserial PRIMARY KEY,
                        status varchar(16) NOT NULL DEFAULT 'pending',
                        created_at timestamptz NOT NULL DEFAULT NOW(),
                        responded_at timestamptz NULL,
                        updated_at timestamptz NOT NULL DEFAULT NOW(),
                        invitee_id bigint NOT NULL REFERENCES {user_table}(id) ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED,
                        inviter_id bigint NOT NULL REFERENCES {user_table}(id) ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED,
                        room_id bigint NOT NULL REFERENCES app_chatroom(id) ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED,
                        CONSTRAINT unique_chat_room_invitation_per_invitee UNIQUE (room_id, invitee_id),
                        CONSTRAINT chat_room_invitation_no_self CHECK (inviter_id <> invitee_id)
                    )
                    """
                )
                cursor.execute(
                    f"CREATE INDEX IF NOT EXISTS {table}_status_idx ON {table} (status)"
                )
            else:
                cursor.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS {table} (
                        id integer PRIMARY KEY AUTOINCREMENT,
                        status varchar(16) NOT NULL DEFAULT 'pending',
                        created_at datetime NOT NULL,
                        responded_at datetime NULL,
                        updated_at datetime NOT NULL,
                        invitee_id integer NOT NULL REFERENCES {user_table}(id) ON DELETE CASCADE,
                        inviter_id integer NOT NULL REFERENCES {user_table}(id) ON DELETE CASCADE,
                        room_id integer NOT NULL REFERENCES app_chatroom(id) ON DELETE CASCADE,
                        UNIQUE (room_id, invitee_id),
                        CHECK (inviter_id <> invitee_id)
                    )
                    """
                )
            logger.warning("Created missing %s table", table)
    except (OperationalError, ProgrammingError) as exc:
        message = str(exc).lower()
        if "already exists" in message:
            return
        logger.warning("ChatRoomInvitation schema repair failed: %s", exc)
    except Exception as exc:
        logger.warning("ChatRoomInvitation schema repair failed: %s", exc)
