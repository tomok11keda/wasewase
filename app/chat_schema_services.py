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


def ensure_course_talk_schema() -> None:
    """0047/0048 の授業トーク列が欠けている本番 SQLite/Postgres を修復する。

    start.sh の migrate が遅れている／失敗した／django_migrations と実スキーマが
    ずれた場合でも、Course Talk の open が OperationalError で落ちないようにする。
    """
    try:
        with connection.cursor() as cursor:
            tables = set(connection.introspection.table_names(cursor))
            if "app_courseoffering" not in tables or "app_chatmessage" not in tables:
                return

            offering_cols = {
                column.name
                for column in connection.introspection.get_table_description(
                    cursor, "app_courseoffering"
                )
            }
            message_cols = {
                column.name
                for column in connection.introspection.get_table_description(
                    cursor, "app_chatmessage"
                )
            }

            if "chat_room_id" not in offering_cols:
                if connection.vendor == "postgresql":
                    cursor.execute(
                        "ALTER TABLE app_courseoffering "
                        "ADD COLUMN IF NOT EXISTS chat_room_id bigint NULL "
                        "UNIQUE REFERENCES app_chatroom(id) ON DELETE SET NULL"
                    )
                else:
                    cursor.execute(
                        "ALTER TABLE app_courseoffering "
                        "ADD COLUMN chat_room_id bigint NULL "
                        "REFERENCES app_chatroom(id)"
                    )
                    try:
                        cursor.execute(
                            "CREATE UNIQUE INDEX IF NOT EXISTS "
                            "app_courseoffering_chat_room_id_uniq "
                            "ON app_courseoffering (chat_room_id)"
                        )
                    except (OperationalError, ProgrammingError):
                        pass
                logger.warning("Added missing app_courseoffering.chat_room_id")

            if "is_hidden" not in message_cols:
                if connection.vendor == "postgresql":
                    cursor.execute(
                        "ALTER TABLE app_chatmessage "
                        "ADD COLUMN IF NOT EXISTS is_hidden boolean NOT NULL DEFAULT FALSE"
                    )
                else:
                    cursor.execute(
                        "ALTER TABLE app_chatmessage "
                        "ADD COLUMN is_hidden bool NOT NULL DEFAULT 0"
                    )
                logger.warning("Added missing app_chatmessage.is_hidden")

            if "deleted_at" not in message_cols:
                if connection.vendor == "postgresql":
                    cursor.execute(
                        "ALTER TABLE app_chatmessage "
                        "ADD COLUMN IF NOT EXISTS deleted_at timestamptz NULL"
                    )
                else:
                    cursor.execute(
                        "ALTER TABLE app_chatmessage "
                        "ADD COLUMN deleted_at datetime NULL"
                    )
                logger.warning("Added missing app_chatmessage.deleted_at")

            if "reply_to_id" not in message_cols:
                if connection.vendor == "postgresql":
                    cursor.execute(
                        "ALTER TABLE app_chatmessage "
                        "ADD COLUMN IF NOT EXISTS reply_to_id bigint NULL "
                        "REFERENCES app_chatmessage(id) ON DELETE SET NULL "
                        "DEFERRABLE INITIALLY DEFERRED"
                    )
                else:
                    cursor.execute(
                        "ALTER TABLE app_chatmessage "
                        "ADD COLUMN reply_to_id bigint NULL "
                        "REFERENCES app_chatmessage(id)"
                    )
                logger.warning("Added missing app_chatmessage.reply_to_id")

            # Indexes (IF NOT EXISTS) — ignore duplicates
            for ddl in (
                "CREATE INDEX IF NOT EXISTS app_chatmessage_is_hidden_idx "
                "ON app_chatmessage (is_hidden)",
                "CREATE INDEX IF NOT EXISTS app_chatmessage_deleted_at_idx "
                "ON app_chatmessage (deleted_at)",
                "CREATE INDEX IF NOT EXISTS app_chatmessage_reply_to_id_idx "
                "ON app_chatmessage (reply_to_id)",
            ):
                try:
                    cursor.execute(ddl)
                except (OperationalError, ProgrammingError):
                    pass

            # 孤児 FK: chat_room_id が存在するが app_chatroom 行が無い
            offering_cols = {
                column.name
                for column in connection.introspection.get_table_description(
                    cursor, "app_courseoffering"
                )
            }
            if "chat_room_id" in offering_cols and "app_chatroom" in tables:
                try:
                    cursor.execute(
                        """
                        UPDATE app_courseoffering
                        SET chat_room_id = NULL
                        WHERE chat_room_id IS NOT NULL
                          AND NOT EXISTS (
                            SELECT 1 FROM app_chatroom
                            WHERE app_chatroom.id = app_courseoffering.chat_room_id
                          )
                        """
                    )
                    cleared = cursor.rowcount
                    if cleared:
                        logger.warning(
                            "Cleared %s dangling CourseOffering.chat_room_id rows",
                            cleared,
                        )
                except (OperationalError, ProgrammingError) as exc:
                    logger.warning(
                        "Dangling course talk FK cleanup skipped: %s", exc
                    )
    except (OperationalError, ProgrammingError) as exc:
        message = str(exc).lower()
        if "duplicate column" not in message and "already exists" not in message:
            logger.exception("Course talk schema repair failed: %s", exc)
    except Exception as exc:
        logger.exception("Course talk schema repair failed: %s", exc)
    ensure_chat_message_moderation_schema()


def _add_nullable_column(cursor, table: str, column: str, pg_ddl: str, sqlite_ddl: str) -> None:
    cols = {
        item.name
        for item in connection.introspection.get_table_description(cursor, table)
    }
    if column in cols:
        return
    if connection.vendor == "postgresql":
        cursor.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {pg_ddl}")
    else:
        cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {sqlite_ddl}")
    logger.warning("Added missing %s.%s", table, column)


def ensure_chat_message_moderation_schema() -> None:
    """運営削除列・異議申し立てテーブルが欠けている本番 DB を修復する。"""
    user_table = get_user_model()._meta.db_table
    try:
        with connection.cursor() as cursor:
            tables = set(connection.introspection.table_names(cursor))
            if "app_chatmessage" in tables:
                _add_nullable_column(
                    cursor,
                    "app_chatmessage",
                    "removed_at",
                    "timestamptz NULL",
                    "datetime NULL",
                )
                _add_nullable_column(
                    cursor,
                    "app_chatmessage",
                    "removed_by_id",
                    f"bigint NULL REFERENCES {user_table}(id) ON DELETE SET NULL",
                    f"integer NULL REFERENCES {user_table}(id)",
                )
                _add_nullable_column(
                    cursor,
                    "app_chatmessage",
                    "removal_reason",
                    "varchar(200) NOT NULL DEFAULT ''",
                    "varchar(200) NOT NULL DEFAULT ''",
                )
                for ddl in (
                    "CREATE INDEX IF NOT EXISTS app_chatmessage_removed_at_idx "
                    "ON app_chatmessage (removed_at)",
                    "CREATE INDEX IF NOT EXISTS app_chatmessage_removed_by_id_idx "
                    "ON app_chatmessage (removed_by_id)",
                ):
                    try:
                        cursor.execute(ddl)
                    except (OperationalError, ProgrammingError):
                        pass

            if "app_contentreport" in tables:
                _add_nullable_column(
                    cursor,
                    "app_contentreport",
                    "handled_at",
                    "timestamptz NULL",
                    "datetime NULL",
                )
                _add_nullable_column(
                    cursor,
                    "app_contentreport",
                    "handled_by_id",
                    f"bigint NULL REFERENCES {user_table}(id) ON DELETE SET NULL",
                    f"integer NULL REFERENCES {user_table}(id)",
                )
                try:
                    cursor.execute(
                        "CREATE INDEX IF NOT EXISTS app_contentreport_handled_at_idx "
                        "ON app_contentreport (handled_at)"
                    )
                except (OperationalError, ProgrammingError):
                    pass

            appeal_table = "app_chatmessagemoderationappeal"
            if appeal_table not in tables:
                if connection.vendor == "postgresql":
                    cursor.execute(
                        f"""
                        CREATE TABLE IF NOT EXISTS {appeal_table} (
                            id bigserial PRIMARY KEY,
                            explanation text NOT NULL,
                            status varchar(16) NOT NULL DEFAULT 'pending',
                            created_at timestamptz NOT NULL DEFAULT NOW(),
                            reviewed_at timestamptz NULL,
                            review_note text NOT NULL DEFAULT '',
                            appellant_id bigint NOT NULL REFERENCES {user_table}(id) ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED,
                            message_id bigint NOT NULL REFERENCES app_chatmessage(id) ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED,
                            reviewer_id bigint NULL REFERENCES {user_table}(id) ON DELETE SET NULL DEFERRABLE INITIALLY DEFERRED
                        )
                        """
                    )
                else:
                    cursor.execute(
                        f"""
                        CREATE TABLE IF NOT EXISTS {appeal_table} (
                            id integer PRIMARY KEY AUTOINCREMENT,
                            explanation text NOT NULL,
                            status varchar(16) NOT NULL DEFAULT 'pending',
                            created_at datetime NOT NULL,
                            reviewed_at datetime NULL,
                            review_note text NOT NULL DEFAULT '',
                            appellant_id integer NOT NULL REFERENCES {user_table}(id) ON DELETE CASCADE,
                            message_id integer NOT NULL REFERENCES app_chatmessage(id) ON DELETE CASCADE,
                            reviewer_id integer NULL REFERENCES {user_table}(id) ON DELETE SET NULL
                        )
                        """
                    )
                logger.warning("Created missing %s table", appeal_table)
            try:
                cursor.execute(
                    f"CREATE INDEX IF NOT EXISTS {appeal_table}_status_idx "
                    f"ON {appeal_table} (status)"
                )
                cursor.execute(
                    f"CREATE UNIQUE INDEX IF NOT EXISTS "
                    f"uniq_pending_chatmsg_moderation_appeal "
                    f"ON {appeal_table} (message_id, appellant_id) "
                    f"WHERE status = 'pending'"
                )
            except (OperationalError, ProgrammingError):
                pass
    except (OperationalError, ProgrammingError) as exc:
        message = str(exc).lower()
        if "already exists" in message or "duplicate column" in message:
            return
        logger.warning("Chat message moderation schema repair failed: %s", exc)
    except Exception as exc:
        logger.warning("Chat message moderation schema repair failed: %s", exc)


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
