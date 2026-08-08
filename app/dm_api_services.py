"""DM / Group Chat JSON helpers — thin wrappers over existing services."""

from __future__ import annotations

from typing import Any

from django.contrib.auth.models import AbstractBaseUser
from django.utils import timezone

from .dm_services import (
    can_access_dm_room,
    dm_room_link,
    get_or_create_dm_room,
    list_dm_read_message_ids_for_sender,
    mark_dm_room_read,
)
from .group_chat_services import (
    assign_default_group_name,
    can_access_group_room,
    mark_group_room_read,
)
from .inbox_services import (
    build_inbox_conversations,
    filter_inbox_by_tab,
    normalize_inbox_tab,
)
from .models import (
    ChatMessage,
    ChatRoom,
    ChatRoomMembership,
    Notification,
    UserDirectMessage,
    UserDirectMessageRoom,
)
from .services import (
    get_following_user_ids,
    get_user_avatar_url,
    user_avatar_initial,
    user_display_name,
)
from .timeline_api_services import serialize_author
from .ugc_services import is_either_blocked, is_user_blocked


def serialize_dm_message(
    message: UserDirectMessage,
    current_user_id: int,
    *,
    anonymize_partner: bool = False,
) -> dict[str, Any]:
    created = timezone.localtime(message.created_at)
    is_mine = message.sender_id == current_user_id
    if anonymize_partner and not is_mine:
        return {
            "id": message.pk,
            "sender_id": message.sender_id,
            "sender_name": "不明なユーザー",
            "sender_initial": "?",
            "avatar_url": "",
            "body": message.body,
            "created_at": created.strftime("%m/%d %H:%M"),
            "is_mine": False,
            "is_read": message.is_read,
        }
    return {
        "id": message.pk,
        "sender_id": message.sender_id,
        "sender_name": user_display_name(message.sender),
        "sender_initial": user_avatar_initial(message.sender),
        "avatar_url": get_user_avatar_url(message.sender) or "",
        "body": message.body,
        "created_at": created.strftime("%m/%d %H:%M"),
        "is_mine": is_mine,
        "is_read": message.is_read,
    }


def serialize_group_message(
    message: ChatMessage, current_user_id: int
) -> dict[str, Any]:
    created = timezone.localtime(message.created_at)
    return {
        "id": message.pk,
        "sender_id": message.sender_id,
        "sender_name": user_display_name(message.sender)
        if message.sender_id
        else "システム",
        "sender_initial": user_avatar_initial(message.sender)
        if message.sender_id
        else "?",
        "avatar_url": get_user_avatar_url(message.sender) or ""
        if message.sender_id
        else "",
        "body": message.body,
        "created_at": created.strftime("%m/%d %H:%M"),
        "is_mine": message.sender_id == current_user_id,
    }


def serialize_inbox_item(item: dict) -> dict[str, Any]:
    room = item["room"]
    kind = item.get("kind") or "dm"
    latest = item.get("latest_message")
    partner = item.get("partner")
    product = item.get("product")
    updated = item.get("updated_at")
    return {
        "kind": kind,
        "room_id": room.pk,
        "display_name": item.get("display_name") or "",
        "subtitle": item.get("subtitle") or "",
        "status_label": item.get("status_label") or "",
        "thumbnail_url": item.get("thumbnail_url") or "",
        "unread_count": int(item.get("unread_count") or 0),
        "is_blocked": bool(item.get("is_blocked")),
        "updated_at": updated.isoformat() if updated is not None else "",
        "latest_body": (getattr(latest, "body", None) or "")[:80] if latest else "",
        "latest_sender_name": item.get("latest_sender_display_name") or "",
        "partner": serialize_author(partner) if partner is not None else None,
        "product_id": product.pk if product is not None else None,
        "spa_path": _spa_path_for_item(kind, room.pk),
    }


def _spa_path_for_item(kind: str, room_pk: int) -> str:
    if kind == "trade":
        return f"/flea/chats/{room_pk}"
    if kind == "group":
        return f"/dm/groups/{room_pk}"
    return f"/dm/{room_pk}"


def build_inbox_payload(user: AbstractBaseUser, tab: str | None) -> dict[str, Any]:
    active = normalize_inbox_tab(tab)
    all_items = build_inbox_conversations(user)
    filtered = filter_inbox_by_tab(all_items, active)
    tab_counts = {
        "all": len(all_items),
        "trade": sum(1 for i in all_items if i.get("kind") == "trade"),
        "dm": sum(1 for i in all_items if i.get("kind") in ("dm", "group")),
    }
    return {
        "ok": True,
        "tab": active,
        "tab_counts": tab_counts,
        "conversations": [serialize_inbox_item(i) for i in filtered],
    }


def build_dm_room_payload(
    room: UserDirectMessageRoom, viewer: AbstractBaseUser
) -> dict[str, Any]:
    partner = room.other_user(viewer)
    is_blocked = is_user_blocked(viewer, partner) if partner else False
    messaging_blocked = (
        is_either_blocked(viewer, partner) if partner else False
    )
    latest_id = mark_dm_room_read(room, viewer)
    messages = list(room.messages.select_related("sender", "sender__profile").order_by("created_at"))
    return {
        "ok": True,
        "room": {
            "id": room.pk,
            "kind": "dm",
            "partner": serialize_author(partner) if partner else None,
            "is_blocked": is_blocked,
            "can_send": not messaging_blocked,
            "latest_id": latest_id or 0,
        },
        "messages": [
            serialize_dm_message(
                m, viewer.id, anonymize_partner=is_blocked
            )
            for m in messages
        ],
    }


def build_dm_messages_payload(
    room: UserDirectMessageRoom,
    viewer: AbstractBaseUser,
    *,
    after: str = "",
) -> dict[str, Any]:
    qs = room.messages.select_related("sender", "sender__profile").order_by(
        "created_at"
    )
    if after.isdigit():
        qs = qs.filter(pk__gt=int(after))
    latest_id = (
        room.messages.order_by("-pk").values_list("pk", flat=True).first() or 0
    )
    partner = room.other_user(viewer)
    is_blocked = is_user_blocked(viewer, partner) if partner else False
    messaging_blocked = (
        is_either_blocked(viewer, partner) if partner else False
    )
    mark_dm_room_read(room, viewer)
    return {
        "messages": [
            serialize_dm_message(
                m, viewer.id, anonymize_partner=is_blocked
            )
            for m in qs
        ],
        "latest_id": latest_id,
        "read_message_ids": list_dm_read_message_ids_for_sender(room, viewer),
        "is_blocked": is_blocked,
        "can_send": not messaging_blocked,
    }


def send_dm_message(
    room: UserDirectMessageRoom, sender: AbstractBaseUser, body: str
) -> UserDirectMessage:
    body = (body or "").strip()
    if not body:
        raise ValueError("empty")
    if len(body) > 500:
        raise ValueError("too_long")
    if not can_access_dm_room(room, sender):
        raise ValueError("forbidden")
    partner = room.other_user(sender)
    if partner and is_either_blocked(sender, partner):
        raise ValueError("blocked")
    message = UserDirectMessage.objects.create(
        room=room, sender=sender, body=body
    )
    room.save(update_fields=["updated_at"])
    if partner and not is_user_blocked(partner, sender):
        Notification.objects.create(
            recipient=partner,
            message=f"{sender.username} さんから DM: {body[:40]}",
            link=dm_room_link(room),
        )
    return message


def start_dm(
    actor: AbstractBaseUser, partner: AbstractBaseUser
) -> tuple[UserDirectMessageRoom, bool]:
    if actor.pk == partner.pk:
        raise ValueError("own_user")
    if is_either_blocked(actor, partner):
        raise ValueError("blocked")
    return get_or_create_dm_room(actor, partner)


def build_group_room_payload(
    room: ChatRoom, viewer: AbstractBaseUser
) -> dict[str, Any]:
    latest_id = mark_group_room_read(room, viewer)
    members = [
        serialize_author(m.user)
        for m in room.memberships.select_related("user", "user__profile")
    ]
    messages = list(
        room.chat_messages.select_related("sender", "sender__profile").order_by(
            "created_at"
        )
    )
    return {
        "ok": True,
        "room": {
            "id": room.pk,
            "kind": "group",
            "name": room.name or f"グループ #{room.pk}",
            "members": members,
            "member_count": len(members),
            "can_send": True,
            "latest_id": latest_id or 0,
        },
        "messages": [
            serialize_group_message(m, viewer.id) for m in messages
        ],
    }


def build_group_messages_payload(
    room: ChatRoom, viewer: AbstractBaseUser, *, after: str = ""
) -> dict[str, Any]:
    qs = room.chat_messages.select_related("sender", "sender__profile").order_by(
        "created_at"
    )
    if after.isdigit():
        qs = qs.filter(pk__gt=int(after))
    latest_id = (
        room.chat_messages.order_by("-pk").values_list("pk", flat=True).first()
        or 0
    )
    mark_group_room_read(room, viewer)
    return {
        "messages": [serialize_group_message(m, viewer.id) for m in qs],
        "latest_id": latest_id,
    }


def send_group_chat_message(
    room: ChatRoom, sender: AbstractBaseUser, body: str
) -> ChatMessage:
    body = (body or "").strip()
    if not body:
        raise ValueError("empty")
    if len(body) > 500:
        raise ValueError("too_long")
    if not can_access_group_room(room, sender):
        raise ValueError("forbidden")
    message = ChatMessage.objects.create(
        room=room, sender=sender, body=body
    )
    room.save(update_fields=["updated_at"])
    return message


def create_group_chat(
    creator: AbstractBaseUser,
    *,
    name: str,
    member_ids: list[int],
) -> ChatRoom:
    from django.db import transaction
    from django.db import IntegrityError

    following_ids = set(get_following_user_ids(creator))
    following_ids.discard(creator.id)
    selected = {int(x) for x in member_ids if int(x) != creator.id}
    if not selected:
        raise ValueError("no_members")
    if not selected.issubset(following_ids):
        raise ValueError("invalid_members")
    group_name = (name or "").strip()[:120]
    try:
        with transaction.atomic():
            room = ChatRoom.objects.create(
                kind=ChatRoom.Kind.GROUP,
                created_by=creator,
                name=group_name,
            )
            memberships = [
                ChatRoomMembership(
                    room=room,
                    user=creator,
                    role=ChatRoomMembership.Role.OWNER,
                )
            ]
            for user_id in selected:
                memberships.append(
                    ChatRoomMembership(
                        room=room,
                        user_id=user_id,
                        role=ChatRoomMembership.Role.MEMBER,
                    )
                )
            ChatRoomMembership.objects.bulk_create(memberships)
            if not group_name:
                assign_default_group_name(room)
    except IntegrityError as exc:
        raise ValueError("create_failed") from exc
    return room


def list_following_for_group(creator: AbstractBaseUser) -> list[dict[str, Any]]:
    following_ids = set(get_following_user_ids(creator))
    following_ids.discard(creator.id)
    from django.contrib.auth import get_user_model

    User = get_user_model()
    users = User.objects.filter(id__in=following_ids).select_related("profile")
    return [serialize_author(u) for u in users]
