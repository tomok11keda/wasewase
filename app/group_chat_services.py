"""グループチャット（ChatRoom kind=group）のヘルパー。1対1 DM とは独立。"""

from __future__ import annotations

import logging

from django.contrib.auth.models import AbstractBaseUser
from django.db.models import Prefetch, Q
from django.db.utils import OperationalError, ProgrammingError
from django.urls import reverse

from .models import ChatMessage, ChatReadState, ChatRoom, ChatRoomMembership
from .services import user_display_name

logger = logging.getLogger(__name__)


def group_room_link(room: ChatRoom) -> str:
    from .spa_canonical import group_room_url

    return group_room_url(room.pk)


def is_group_member(room: ChatRoom, user: AbstractBaseUser) -> bool:
    if not getattr(user, "is_authenticated", False) or room.kind != ChatRoom.Kind.GROUP:
        return False
    return ChatRoomMembership.objects.filter(room=room, user=user).exists()


def can_access_group_room(room: ChatRoom, user: AbstractBaseUser) -> bool:
    """正式メンバーのみ（メッセージ送信・メンバー操作）。閲覧は can_view_group_room。"""
    return is_group_member(room, user)


def assign_default_group_name(room: ChatRoom) -> str:
    """メンバー表示名からグループ名を自動生成して保存する。"""
    members = list(
        room.memberships.select_related("user", "user__profile").order_by("joined_at")
    )
    labels = [user_display_name(membership.user) for membership in members[:3]]
    if len(members) > 3:
        name = f"{', '.join(labels)} 他{len(members) - 3}人"
    elif labels:
        name = ", ".join(labels)
    else:
        name = f"グループ #{room.pk}"
    room.name = name
    room.save(update_fields=["name"])
    return name


def get_group_read_state_map(
    user: AbstractBaseUser, room_ids: list[int]
) -> dict[int, int]:
    if not room_ids:
        return {}
    try:
        return {
            room_id: last_read_id
            for room_id, last_read_id in ChatReadState.objects.filter(
                user=user,
                room_id__in=room_ids,
            ).values_list("room_id", "last_read_message_id")
        }
    except (OperationalError, ProgrammingError) as exc:
        logger.warning("Group read state lookup failed: %s", exc)
        return {}


def count_unread_group_messages(
    room: ChatRoom,
    user: AbstractBaseUser,
    last_read_message_id: int = 0,
) -> int:
    return (
        ChatMessage.objects.filter(
            room=room, pk__gt=last_read_message_id, is_hidden=False
        )
        .exclude(sender_id=user.pk)
        .count()
    )


def mark_group_room_read(room: ChatRoom, user: AbstractBaseUser) -> int:
    latest_id = (
        ChatMessage.objects.filter(room=room)
        .order_by("-pk")
        .values_list("pk", flat=True)
        .first()
        or 0
    )
    try:
        ChatReadState.objects.update_or_create(
            room=room,
            user=user,
            defaults={"last_read_message_id": latest_id},
        )
    except (OperationalError, ProgrammingError) as exc:
        logger.warning("Group read state update failed: %s", exc)
    return latest_id


def list_group_rooms_for_user(user: AbstractBaseUser):
    latest_message = Prefetch(
        "chat_messages",
        queryset=ChatMessage.objects.select_related("sender").order_by("-pk")[:1],
        to_attr="latest_messages",
    )
    member_count = Prefetch(
        "memberships",
        queryset=ChatRoomMembership.objects.select_related("user", "user__profile"),
        to_attr="member_list",
    )
    return (
        ChatRoom.objects.filter(
            kind=ChatRoom.Kind.GROUP,
            memberships__user=user,
        )
        .prefetch_related(latest_message, member_count)
        .distinct()
        .order_by("-updated_at")
    )


def build_group_conversations(user: AbstractBaseUser) -> list[dict]:
    rooms = list(list_group_rooms_for_user(user))
    room_ids = [room.pk for room in rooms]
    read_map = get_group_read_state_map(user, room_ids)
    conversations = []
    for room in rooms:
        latest = room.latest_messages[0] if room.latest_messages else None
        member_count = len(room.member_list) if hasattr(room, "member_list") else 0
        conversations.append(
            {
                "kind": "group",
                "room": room,
                "display_name": room.name or f"グループ #{room.pk}",
                "member_count": member_count,
                "latest_message": latest,
                "unread_count": count_unread_group_messages(
                    room,
                    user,
                    read_map.get(room.pk, 0),
                ),
                "updated_at": latest.created_at if latest else room.updated_at,
            }
        )
    return conversations


def build_group_unread_summary(user: AbstractBaseUser) -> dict:
    conversations = build_group_conversations(user)
    rooms = [
        {
            "kind": "group",
            "room_pk": item["room"].pk,
            "unread_count": item["unread_count"],
        }
        for item in conversations
        if item["unread_count"] > 0
    ]
    return {
        "total_unread": sum(item["unread_count"] for item in rooms),
        "rooms": rooms,
    }
