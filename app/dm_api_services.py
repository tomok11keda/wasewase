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
    from .chat_message_services import serialize_chat_message

    return serialize_chat_message(message, current_user_id)


def serialize_inbox_item(item: dict) -> dict[str, Any]:
    room = item["room"]
    kind = item.get("kind") or "dm"
    latest = item.get("latest_message")
    partner = item.get("partner")
    product = item.get("product")
    updated = item.get("updated_at")
    offering_id = item.get("offering_id")
    if offering_id is None and item.get("offering") is not None:
        offering_id = getattr(item["offering"], "pk", None)
    spa_path = _spa_path_for_item(kind, room.pk, offering_id=offering_id)
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
        "offering_id": offering_id,
        "spa_path": spa_path,
    }


def _spa_path_for_item(
    kind: str, room_pk: int, *, offering_id: int | None = None
) -> str:
    if kind == "trade":
        return f"/flea/chats/{room_pk}"
    if kind in ("group", "group_invite"):
        return f"/dm/groups/{room_pk}"
    if kind == "course":
        if offering_id:
            return f"/courses/{offering_id}/talk?from=inbox"
        return f"/dm?tab=course"
    return f"/dm/{room_pk}"


def build_inbox_payload(user: AbstractBaseUser, tab: str | None) -> dict[str, Any]:
    from .dm_request_services import count_pending_dm_requests

    active = normalize_inbox_tab(tab)
    all_items = build_inbox_conversations(user)
    filtered = filter_inbox_by_tab(all_items, active)
    tab_counts = {
        "all": len(all_items),
        "trade": sum(1 for i in all_items if i.get("kind") == "trade"),
        "dm": sum(
            1
            for i in all_items
            if i.get("kind") in ("dm", "group", "group_invite")
        ),
        "course": sum(1 for i in all_items if i.get("kind") == "course"),
    }
    try:
        message_request_count = count_pending_dm_requests(user)
    except Exception:
        # count_pending already soft-fails DB errors; keep inbox resilient.
        message_request_count = 0
    return {
        "ok": True,
        "tab": active,
        "tab_counts": tab_counts,
        "message_request_count": message_request_count,
        "conversations": [serialize_inbox_item(i) for i in filtered],
    }


def build_dm_room_payload(
    room: UserDirectMessageRoom, viewer: AbstractBaseUser
) -> dict[str, Any]:
    from .dm_request_services import (
        get_pending_dm_request_for_recipient,
        recipient_can_send_in_dm,
    )

    partner = room.other_user(viewer)
    is_blocked = is_user_blocked(viewer, partner) if partner else False
    messaging_blocked = (
        is_either_blocked(viewer, partner) if partner else False
    )
    pending = get_pending_dm_request_for_recipient(room, viewer)
    can_send = (
        (not messaging_blocked)
        and recipient_can_send_in_dm(room, viewer)
    )
    latest_id = mark_dm_room_read(room, viewer)
    messages = list(
        room.messages.select_related("sender", "sender__profile").order_by(
            "created_at"
        )
    )
    request_payload = None
    if pending is not None:
        request_payload = {
            "id": pending.pk,
            "status": pending.status,
            "from_user": serialize_author(pending.from_user),
        }
    return {
        "ok": True,
        "room": {
            "id": room.pk,
            "kind": "dm",
            "partner": serialize_author(partner) if partner else None,
            "is_blocked": is_blocked,
            "can_send": can_send,
            "request_status": "pending_request" if pending else "active",
            "message_request": request_payload,
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
    from .dm_request_services import (
        get_pending_dm_request_for_recipient,
        recipient_can_send_in_dm,
    )

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
    pending = get_pending_dm_request_for_recipient(room, viewer)
    can_send = (not messaging_blocked) and recipient_can_send_in_dm(room, viewer)
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
        "can_send": can_send,
        "request_status": "pending_request" if pending else "active",
    }


def send_dm_message(
    room: UserDirectMessageRoom, sender: AbstractBaseUser, body: str
) -> UserDirectMessage:
    from .dm_request_services import (
        ensure_message_request_after_send,
        recipient_can_send_in_dm,
    )

    body = (body or "").strip()
    if not body:
        raise ValueError("empty")
    if len(body) > 500:
        raise ValueError("too_long")
    if not can_access_dm_room(room, sender):
        raise ValueError("forbidden")
    if not recipient_can_send_in_dm(room, sender):
        raise ValueError("request_pending")
    partner = room.other_user(sender)
    if partner and is_either_blocked(sender, partner):
        raise ValueError("blocked")
    message = UserDirectMessage.objects.create(
        room=room, sender=sender, body=body
    )
    room.save(update_fields=["updated_at"])
    if partner and not is_user_blocked(partner, sender):
        request = ensure_message_request_after_send(
            room,
            sender,
            partner,
            preview_body=body,
        )
        if request is None:
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


def create_group_chat(
    creator: AbstractBaseUser,
    *,
    name: str,
    member_ids: list[int],
) -> ChatRoom:
    """
    グループを作成し、選択ユーザーには membership ではなく招待を送る。
    作成者のみが最初の正式メンバー（OWNER）。
    """
    from django.db import IntegrityError, transaction

    from .group_invite_services import create_or_refresh_invitations

    selected = {int(x) for x in member_ids if int(x) != creator.id}
    if not selected:
        raise ValueError("no_members")
    group_name = (name or "").strip()[:120]
    try:
        with transaction.atomic():
            room = ChatRoom.objects.create(
                kind=ChatRoom.Kind.GROUP,
                created_by=creator,
                name=group_name,
            )
            ChatRoomMembership.objects.create(
                room=room,
                user=creator,
                role=ChatRoomMembership.Role.OWNER,
            )
            if not group_name:
                assign_default_group_name(room)
            invitations = create_or_refresh_invitations(
                room, creator, list(selected)
            )
            if not invitations:
                raise ValueError("no_invitees")
    except IntegrityError as exc:
        raise ValueError("create_failed") from exc
    except ValueError:
        raise
    return room


def list_following_for_group(creator: AbstractBaseUser) -> list[dict[str, Any]]:
    from .group_invite_services import list_invite_candidates

    return list_invite_candidates(creator, query="")


def build_group_room_payload(
    room: ChatRoom, viewer: AbstractBaseUser
) -> dict[str, Any]:
    from .chat_message_services import visible_chat_messages_qs
    from .group_invite_services import (
        get_pending_invitation,
        list_pending_invites_for_room,
        serialize_invitation,
    )

    is_member = can_access_group_room(room, viewer)
    pending = None if is_member else get_pending_invitation(room, viewer)
    if is_member:
        latest_id = mark_group_room_read(room, viewer)
    else:
        latest_id = (
            visible_chat_messages_qs(room)
            .order_by("-pk")
            .values_list("pk", flat=True)
            .first()
            or 0
        )

    members = [
        serialize_author(m.user)
        for m in room.memberships.select_related("user", "user__profile").order_by(
            "joined_at"
        )
    ]
    messages = list(visible_chat_messages_qs(room).order_by("created_at"))
    pending_invites = list_pending_invites_for_room(room) if is_member else []
    membership_status = (
        "member" if is_member else ("pending_invite" if pending else "none")
    )
    return {
        "ok": True,
        "room": {
            "id": room.pk,
            "kind": "group",
            "name": room.name or f"グループ #{room.pk}",
            "members": members,
            "member_count": len(members),
            "can_send": is_member,
            "membership_status": membership_status,
            "invitation": serialize_invitation(pending) if pending else None,
            "pending_invites": pending_invites,
            "latest_id": latest_id or 0,
        },
        "messages": [serialize_group_message(m, viewer.id) for m in messages],
    }


def build_group_messages_payload(
    room: ChatRoom, viewer: AbstractBaseUser, *, after: str = ""
) -> dict[str, Any]:
    from .chat_message_services import visible_chat_messages_qs

    qs = visible_chat_messages_qs(room).order_by("created_at")
    if after.isdigit():
        qs = qs.filter(pk__gt=int(after))
    latest_id = (
        visible_chat_messages_qs(room)
        .order_by("-pk")
        .values_list("pk", flat=True)
        .first()
        or 0
    )
    if can_access_group_room(room, viewer):
        mark_group_room_read(room, viewer)
    return {
        "messages": [serialize_group_message(m, viewer.id) for m in qs],
        "latest_id": latest_id,
        "can_send": can_access_group_room(room, viewer),
    }


def send_group_chat_message(
    room: ChatRoom,
    sender: AbstractBaseUser,
    body: str,
    *,
    reply_to_id: int | None = None,
) -> ChatMessage:
    from .chat_message_services import create_chat_message

    if not can_access_group_room(room, sender):
        raise ValueError("forbidden")
    return create_chat_message(room, sender, body, reply_to_id=reply_to_id)
