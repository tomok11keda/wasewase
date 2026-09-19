"""Structured 1-to-1 DM sharing: live ACL cards, no UGC snapshots."""

from __future__ import annotations

from typing import Any, Iterable

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AbstractBaseUser

from .dm_request_services import (
    can_access_dm_room_for_viewer,
    ensure_message_request_after_send,
    recipient_can_send_in_dm,
)
from .dm_services import (
    dm_room_link,
    find_dm_room,
    list_dm_rooms_for_user,
)
from .flea_api_services import serialize_product_card
from .models import Product, TimelinePost, UserDirectMessage, UserDirectMessageRoom
from .notification_services import create_notification, notification_actor_label
from .timeline_api_services import serialize_author
from .ugc_services import (
    filter_visible_products,
    filter_visible_timeline_posts,
    is_either_blocked,
    is_user_blocked,
)

User = get_user_model()

SHARE_KIND_TEXT = UserDirectMessage.MessageKind.TEXT
SHARE_KIND_SHARE = UserDirectMessage.MessageKind.SHARE
SHARE_TYPE_TIMELINE = UserDirectMessage.ShareTargetType.TIMELINE
SHARE_TYPE_FLEA = UserDirectMessage.ShareTargetType.FLEA
SHARE_TYPES = frozenset({SHARE_TYPE_TIMELINE, SHARE_TYPE_FLEA})

SHARE_PREVIEW_TIMELINE = "投稿をシェアしました"
SHARE_PREVIEW_FLEA = "商品をシェアしました"
BODY_PREVIEW_LIMIT = 120
RECIPIENT_PREVIEW_LIMIT = 5
RECIPIENT_MAX = 50


def share_preview_body(target_type: str) -> str:
    if target_type == SHARE_TYPE_FLEA:
        return SHARE_PREVIEW_FLEA
    return SHARE_PREVIEW_TIMELINE


def share_notification_text(sender: AbstractBaseUser, target_type: str) -> str:
    name = notification_actor_label(sender)
    if target_type == SHARE_TYPE_FLEA:
        return f"{name}さんから商品がシェアされました"
    return f"{name}さんから投稿がシェアされました"


def _timeline_visible_qs(viewer: AbstractBaseUser | None, ids: Iterable[int]):
    id_list = [int(pk) for pk in ids]
    if not id_list:
        return TimelinePost.objects.none()
    return filter_visible_timeline_posts(
        TimelinePost.objects.filter(pk__in=id_list).select_related(
            "author", "author__profile"
        ),
        viewer,
    )


def _product_visible_qs(viewer: AbstractBaseUser | None, ids: Iterable[int]):
    id_list = [int(pk) for pk in ids]
    if not id_list:
        return Product.objects.none()
    return filter_visible_products(
        Product.objects.filter(pk__in=id_list).select_related(
            "seller", "seller__profile"
        ),
        viewer,
    )


def require_shareable_target(
    viewer: AbstractBaseUser,
    target_type: str,
    target_id: int,
) -> TimelinePost | Product:
    kind = (target_type or "").strip()
    if kind not in SHARE_TYPES:
        raise ValueError("invalid_target_type")
    try:
        pk = int(target_id)
    except (TypeError, ValueError):
        raise ValueError("invalid_target") from None
    if pk <= 0:
        raise ValueError("invalid_target")
    if kind == SHARE_TYPE_TIMELINE:
        post = _timeline_visible_qs(viewer, [pk]).first()
        if post is None:
            exists = TimelinePost.objects.filter(pk=pk).exists()
            raise ValueError("unavailable" if exists else "invalid_target")
        return post
    product = _product_visible_qs(viewer, [pk]).first()
    if product is None:
        exists = Product.objects.filter(pk=pk).exists()
        raise ValueError("unavailable" if exists else "invalid_target")
    return product


def serialize_timeline_share_content(post: TimelinePost) -> dict[str, Any]:
    image_url = None
    if post.image:
        try:
            image_url = post.image.url
        except ValueError:
            image_url = None
    body = post.body or ""
    return {
        "id": post.pk,
        "body_preview": body[:BODY_PREVIEW_LIMIT],
        "image_url": image_url,
        "author": serialize_author(post.author),
    }


def serialize_flea_share_content(product: Product) -> dict[str, Any]:
    card = serialize_product_card(product)
    return {
        "id": card["id"],
        "name": card["name"],
        "price": card["price"],
        "image_url": card["image_url"] or "",
        "seller": card["seller"],
    }


def _unavailable_share(target_type: str, target_id: int | None) -> dict[str, Any]:
    return {
        "type": target_type,
        "id": target_id,
        "available": False,
    }


def resolve_share_payloads(
    messages: Iterable[UserDirectMessage],
    viewer: AbstractBaseUser | None,
    *,
    hide_partner_shares: bool = False,
    viewer_id: int | None = None,
) -> dict[int, dict[str, Any]]:
    """Live-ACL share cards for a page of DM messages. Batched by target type."""
    share_messages = [
        m
        for m in messages
        if getattr(m, "message_kind", SHARE_KIND_TEXT) == SHARE_KIND_SHARE
    ]
    if not share_messages:
        return {}

    timeline_ids: set[int] = set()
    flea_ids: set[int] = set()
    for message in share_messages:
        target_id = message.share_target_id
        if not target_id:
            continue
        if message.share_target_type == SHARE_TYPE_TIMELINE:
            timeline_ids.add(int(target_id))
        elif message.share_target_type == SHARE_TYPE_FLEA:
            flea_ids.add(int(target_id))

    visible_posts = {
        post.pk: post for post in _timeline_visible_qs(viewer, timeline_ids)
    }
    visible_products = {
        product.pk: product for product in _product_visible_qs(viewer, flea_ids)
    }

    payloads: dict[int, dict[str, Any]] = {}
    for message in share_messages:
        target_type = message.share_target_type or ""
        target_id = message.share_target_id
        is_mine = viewer_id is not None and message.sender_id == viewer_id
        if hide_partner_shares and not is_mine:
            payloads[message.pk] = _unavailable_share(target_type, target_id)
            continue
        if target_type == SHARE_TYPE_TIMELINE and target_id in visible_posts:
            post = visible_posts[target_id]
            payloads[message.pk] = {
                "type": SHARE_TYPE_TIMELINE,
                "id": target_id,
                "available": True,
                "content": serialize_timeline_share_content(post),
            }
            continue
        if target_type == SHARE_TYPE_FLEA and target_id in visible_products:
            product = visible_products[target_id]
            payloads[message.pk] = {
                "type": SHARE_TYPE_FLEA,
                "id": target_id,
                "available": True,
                "content": serialize_flea_share_content(product),
            }
            continue
        payloads[message.pk] = _unavailable_share(target_type, target_id)
    return payloads


def _serialize_recipient(partner, room: UserDirectMessageRoom) -> dict[str, Any]:
    author = serialize_author(partner) or {
        "id": partner.pk,
        "username": "",
        "display_name": "",
        "avatar_url": "",
        "initial": "?",
    }
    return {
        "user_id": partner.pk,
        "room_id": room.pk,
        "username": author.get("username") or "",
        "display_name": author.get("display_name") or "",
        "avatar_url": author.get("avatar_url") or "",
        "initial": author.get("initial") or "?",
    }


def list_share_recipients(user: AbstractBaseUser) -> dict[str, Any]:
    """Eligible existing 1-to-1 DM partners, newest conversation first."""
    from .dm_request_services import pending_dm_request_room_ids_for

    rooms = list(list_dm_rooms_for_user(user))
    pending_ids = pending_dm_request_room_ids_for(user)
    recipients: list[dict[str, Any]] = []
    for room in rooms:
        if room.pk in pending_ids:
            continue
        partner = room.other_user(user)
        if partner is None or partner.pk == user.pk:
            continue
        if is_either_blocked(user, partner):
            continue
        if not can_access_dm_room_for_viewer(room, user):
            continue
        if not recipient_can_send_in_dm(room, user):
            continue
        recipients.append(_serialize_recipient(partner, room))
        if len(recipients) >= RECIPIENT_MAX:
            break
    return {
        "ok": True,
        "recipients": recipients[:RECIPIENT_PREVIEW_LIMIT],
        "all_recipients": recipients,
        "has_more": len(recipients) > RECIPIENT_PREVIEW_LIMIT,
        "total": len(recipients),
    }


def _assert_can_send_in_room(
    room: UserDirectMessageRoom, sender: AbstractBaseUser
) -> AbstractBaseUser:
    if not can_access_dm_room_for_viewer(room, sender):
        raise ValueError("forbidden")
    if not recipient_can_send_in_dm(room, sender):
        raise ValueError("request_pending")
    partner = room.other_user(sender)
    if partner is None:
        raise ValueError("forbidden")
    if is_either_blocked(sender, partner):
        raise ValueError("blocked")
    return partner


def send_share_dm(
    sender: AbstractBaseUser,
    *,
    partner_id: int,
    target_type: str,
    target_id: int,
) -> UserDirectMessage:
    if not getattr(sender, "is_authenticated", False):
        raise ValueError("forbidden")
    try:
        partner_pk = int(partner_id)
    except (TypeError, ValueError):
        raise ValueError("invalid_user") from None
    if partner_pk == sender.pk:
        raise ValueError("own_user")
    partner = User.objects.filter(pk=partner_pk, is_active=True).first()
    if partner is None:
        raise ValueError("invalid_user")

    require_shareable_target(sender, target_type, target_id)
    room = find_dm_room(sender, partner)
    if room is None:
        raise ValueError("not_a_partner")
    partner = _assert_can_send_in_room(room, sender)

    kind = (target_type or "").strip()
    body = share_preview_body(kind)
    message = UserDirectMessage.objects.create(
        room=room,
        sender=sender,
        body=body,
        message_kind=SHARE_KIND_SHARE,
        share_target_type=kind,
        share_target_id=int(target_id),
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
            create_notification(
                recipient=partner,
                message=share_notification_text(sender, kind),
                link=dm_room_link(room),
                actor=sender,
                push_kind="share_flea" if kind == SHARE_TYPE_FLEA else "share_timeline",
            )
    return message
