"""ユーザー間 DM（UserDirectMessageRoom）のヘルパー。"""

from __future__ import annotations

import logging

from django.contrib.auth.models import AbstractBaseUser
from django.db import connection
from django.db.models import Prefetch, Q
from django.db.utils import OperationalError, ProgrammingError
from django.urls import reverse

from .models import UserDirectMessage, UserDirectMessageReadState, UserDirectMessageRoom

logger = logging.getLogger(__name__)


def ordered_user_pair(
    user1: AbstractBaseUser, user2: AbstractBaseUser
) -> tuple[AbstractBaseUser, AbstractBaseUser]:
    if user1.pk == user2.pk:
        raise ValueError("自分自身との DM ルームは作成できません。")
    if user1.pk < user2.pk:
        return user1, user2
    return user2, user1


def get_or_create_dm_room(
    user1: AbstractBaseUser, user2: AbstractBaseUser
) -> tuple[UserDirectMessageRoom, bool]:
    user_a, user_b = ordered_user_pair(user1, user2)
    return UserDirectMessageRoom.objects.get_or_create(user_a=user_a, user_b=user_b)


def find_dm_room(
    user1: AbstractBaseUser, user2: AbstractBaseUser
) -> UserDirectMessageRoom | None:
    try:
        user_a, user_b = ordered_user_pair(user1, user2)
    except ValueError:
        return None
    return UserDirectMessageRoom.objects.filter(user_a=user_a, user_b=user_b).first()


def can_access_dm_room(room: UserDirectMessageRoom, user: AbstractBaseUser) -> bool:
    if not user.is_authenticated:
        return False
    return room.involves_user(user)


def dm_room_link(room: UserDirectMessageRoom) -> str:
    from .spa_canonical import dm_room_url

    return dm_room_url(room.pk)


def ensure_dm_message_is_read_column() -> None:
    """本番 DB に DM メッセージの is_read 列が無い場合に追加する。"""
    table = UserDirectMessage._meta.db_table
    column = "is_read"
    try:
        with connection.cursor() as cursor:
            description = connection.introspection.get_table_description(cursor, table)
            if any(col.name == column for col in description):
                return
        field = UserDirectMessage._meta.get_field(column)
        with connection.schema_editor() as schema_editor:
            schema_editor.add_field(UserDirectMessage, field)
        logger.warning("Added missing %s.%s column on startup", table, column)
    except (OperationalError, ProgrammingError) as exc:
        message = str(exc).lower()
        if "already exists" in message or "duplicate" in message:
            return
        logger.warning("DM message is_read column repair failed: %s", exc)
    except Exception as exc:
        logger.warning("DM message is_read column repair failed: %s", exc)


def mark_dm_incoming_messages_read(
    room: UserDirectMessageRoom, reader: AbstractBaseUser
) -> int:
    """1対1 DM: 閲覧者が受け取った未読メッセージに既読を付ける。

    グループ拡張時はメッセージ単位の ReadReceipt モデルへ置き換え可能。
    """
    try:
        return (
            UserDirectMessage.objects.filter(room=room, is_read=False)
            .exclude(sender_id=reader.pk)
            .update(is_read=True)
        )
    except (OperationalError, ProgrammingError) as exc:
        logger.warning("DM incoming read update failed: %s", exc)
        return 0


def list_dm_read_message_ids_for_sender(
    room: UserDirectMessageRoom, sender: AbstractBaseUser
) -> list[int]:
    """送信者のメッセージのうち相手が既読にした ID 一覧（ポーリング用）。"""
    try:
        return list(
            UserDirectMessage.objects.filter(
                room=room,
                sender=sender,
                is_read=True,
            ).values_list("pk", flat=True)
        )
    except (OperationalError, ProgrammingError) as exc:
        logger.warning("DM read receipt lookup failed: %s", exc)
        return []


def ensure_dm_read_state_table() -> None:
    """本番 DB に DM 既読テーブルが無い場合に作成する（起動時のセーフティネット）。"""
    table = UserDirectMessageReadState._meta.db_table
    try:
        with connection.cursor() as cursor:
            if table in connection.introspection.table_names(cursor):
                return
        with connection.schema_editor() as schema_editor:
            schema_editor.create_model(UserDirectMessageReadState)
        logger.warning("Created missing %s table on startup", table)
    except (OperationalError, ProgrammingError) as exc:
        message = str(exc).lower()
        if "already exists" in message or "duplicate" in message:
            return
        logger.warning("DM read state table repair failed: %s", exc)
    except Exception as exc:
        logger.warning("DM read state table repair failed: %s", exc)


def get_dm_read_state_map(
    user: AbstractBaseUser, room_ids: list[int]
) -> dict[int, int]:
    if not room_ids:
        return {}
    try:
        return {
            room_id: last_read_id
            for room_id, last_read_id in UserDirectMessageReadState.objects.filter(
                user=user,
                room_id__in=room_ids,
            ).values_list("room_id", "last_read_message_id")
        }
    except (OperationalError, ProgrammingError) as exc:
        logger.warning("DM read state lookup failed; treating as unread=0: %s", exc)
        return {}


def count_unread_dm_messages(
    room: UserDirectMessageRoom,
    user: AbstractBaseUser,
    last_read_message_id: int = 0,
) -> int:
    return (
        UserDirectMessage.objects.filter(room=room, pk__gt=last_read_message_id)
        .exclude(sender_id=user.pk)
        .count()
    )


def get_unread_dm_counts_for_rooms(
    user: AbstractBaseUser, rooms: list[UserDirectMessageRoom]
) -> dict[int, int]:
    room_ids = [room.pk for room in rooms]
    read_map = get_dm_read_state_map(user, room_ids)
    return {
        room.pk: count_unread_dm_messages(
            room,
            user,
            read_map.get(room.pk, 0),
        )
        for room in rooms
    }


def mark_dm_room_read(
    room: UserDirectMessageRoom, user: AbstractBaseUser
) -> int:
    mark_dm_incoming_messages_read(room, user)
    latest_id = (
        UserDirectMessage.objects.filter(room=room)
        .order_by("-pk")
        .values_list("pk", flat=True)
        .first()
        or 0
    )
    try:
        UserDirectMessageReadState.objects.update_or_create(
            room=room,
            user=user,
            defaults={"last_read_message_id": latest_id},
        )
    except (OperationalError, ProgrammingError) as exc:
        logger.warning("DM read state update failed: %s", exc)
    return latest_id


def list_dm_rooms_for_user(user: AbstractBaseUser):
    """ログインユーザーが参加する DM ルームを最新順で返す。"""
    latest_message = Prefetch(
        "messages",
        queryset=UserDirectMessage.objects.select_related("sender").order_by("-pk")[:1],
        to_attr="latest_messages",
    )
    return (
        UserDirectMessageRoom.objects.filter(Q(user_a=user) | Q(user_b=user))
        .select_related("user_a", "user_b", "user_a__profile", "user_b__profile")
        .prefetch_related(latest_message)
        .order_by("-updated_at")
    )


def build_dm_conversations(user: AbstractBaseUser) -> list[dict]:
    """インボックス表示用にルーム・相手・最新メッセージ・未読件数をまとめる。"""
    rooms = list(list_dm_rooms_for_user(user))
    unread_map = get_unread_dm_counts_for_rooms(user, rooms)
    conversations = []
    for room in rooms:
        partner = room.other_user(user)
        latest = room.latest_messages[0] if room.latest_messages else None
        conversations.append(
            {
                "room": room,
                "partner": partner,
                "latest_message": latest,
                "unread_count": unread_map.get(room.pk, 0),
            }
        )
    return conversations


def build_dm_unread_summary(user: AbstractBaseUser) -> dict:
    conversations = build_dm_conversations(user)
    rooms = [
        {"room_pk": item["room"].pk, "unread_count": item["unread_count"]}
        for item in conversations
        if item["unread_count"] > 0
    ]
    return {
        "total_unread": sum(item["unread_count"] for item in rooms),
        "rooms": rooms,
    }
