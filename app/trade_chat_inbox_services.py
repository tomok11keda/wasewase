"""フリマ取引チャットをメッセージ一覧（DMインボックス）に載せるための集約。"""

from __future__ import annotations

import logging

from django.contrib.auth.models import AbstractBaseUser
from django.db.models import Prefetch, Q
from django.db.utils import OperationalError, ProgrammingError

from .group_chat_services import get_group_read_state_map
from .models import ChatReadState, ChatRoom, Message, Product

logger = logging.getLogger(__name__)


def product_thumbnail_url(product: Product | None) -> str:
    if product is None:
        return ""
    image = getattr(product, "image", None)
    if image:
        try:
            url = image.url
            if url:
                return url
        except Exception:
            pass
    return (getattr(product, "image_url", None) or "").strip()


def trade_status_label(room: ChatRoom, product: Product | None) -> str:
    if product is None:
        return "取引チャット"
    if product.is_sold:
        return "売り切れ"
    if room.is_closed:
        return "交渉終了"
    if room.is_confirmed or product.is_pending:
        return "取引中"
    return "交渉中"


def list_product_chat_rooms_for_user(user: AbstractBaseUser):
    latest_message = Prefetch(
        "messages",
        queryset=Message.objects.select_related("sender").order_by("-pk")[:1],
        to_attr="latest_messages",
    )
    return (
        ChatRoom.objects.filter(kind=ChatRoom.Kind.PRODUCT)
        .filter(Q(buyer=user) | Q(product__seller=user))
        .exclude(product__isnull=True)
        .select_related(
            "product",
            "product__seller",
            "product__seller__profile",
            "buyer",
            "buyer__profile",
        )
        .prefetch_related(latest_message)
        .order_by("-updated_at")
    )


def count_unread_product_messages(
    room: ChatRoom,
    user: AbstractBaseUser,
    last_read_message_id: int = 0,
) -> int:
    return (
        Message.objects.filter(chat_room=room, pk__gt=last_read_message_id)
        .exclude(sender_id=user.pk)
        .count()
    )


def mark_product_chat_room_read(room: ChatRoom, user: AbstractBaseUser) -> int:
    latest_id = (
        Message.objects.filter(chat_room=room)
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
        logger.warning("Product chat read state update failed: %s", exc)
    return latest_id


def build_trade_chat_conversations(user: AbstractBaseUser) -> list[dict]:
    rooms = list(list_product_chat_rooms_for_user(user))
    room_ids = [room.pk for room in rooms]
    read_map = get_group_read_state_map(user, room_ids)
    conversations: list[dict] = []

    for room in rooms:
        product = room.product
        if product is None:
            continue
        if room.buyer_id == user.id:
            partner = product.seller
        else:
            partner = room.buyer
        latest = room.latest_messages[0] if getattr(room, "latest_messages", None) else None
        status_label = trade_status_label(room, product)
        conversations.append(
            {
                "kind": "trade",
                "room": room,
                "product": product,
                "partner": partner,
                "display_name": product.name,
                "subtitle": status_label,
                "status_label": status_label,
                "thumbnail_url": product_thumbnail_url(product),
                "latest_message": latest,
                "unread_count": count_unread_product_messages(
                    room,
                    user,
                    read_map.get(room.pk, 0),
                ),
                "updated_at": latest.created_at if latest else room.updated_at,
            }
        )
    return conversations


def build_trade_chat_unread_summary(user: AbstractBaseUser) -> dict:
    conversations = build_trade_chat_conversations(user)
    rooms = [
        {
            "kind": "trade",
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
