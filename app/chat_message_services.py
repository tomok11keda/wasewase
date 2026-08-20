"""グループ／授業トーク共通の ChatMessage ヘルパー（返信・削除・シリアライズ）。"""

from __future__ import annotations

from typing import Any

from django.contrib.auth.base_user import AbstractBaseUser
from django.db import transaction
from django.utils import timezone

from .models import ChatMessage, ChatRoom
from .services import get_user_avatar_url, user_avatar_initial, user_display_name

REPLY_PREVIEW_MAX = 80
DELETED_PREVIEW = "削除されたメッセージ"
HIDDEN_PREVIEW = "削除されたメッセージ"


def resolve_reply_target(
    room: ChatRoom, reply_to_id: int | None
) -> ChatMessage | None:
    """reply_to_id を検証して同 Room のメッセージを返す。無効なら ValueError。"""
    if reply_to_id is None or reply_to_id == "":
        return None
    try:
        reply_id = int(reply_to_id)
    except (TypeError, ValueError) as exc:
        raise ValueError("invalid_reply_to") from exc
    if reply_id <= 0:
        raise ValueError("invalid_reply_to")
    try:
        target = ChatMessage.objects.select_related("sender").get(pk=reply_id)
    except ChatMessage.DoesNotExist as exc:
        raise ValueError("reply_not_found") from exc
    if target.room_id != room.pk:
        raise ValueError("reply_wrong_room")
    # hidden / deleted への返信は許可（会話継続のため）。表示は unavailable。
    return target


def create_chat_message(
    room: ChatRoom,
    sender: AbstractBaseUser,
    body: str,
    *,
    reply_to_id: int | None = None,
) -> ChatMessage:
    body = (body or "").strip()
    if not body:
        raise ValueError("empty")
    if len(body) > 500:
        raise ValueError("too_long")
    reply_to = resolve_reply_target(room, reply_to_id)
    message = ChatMessage.objects.create(
        room=room,
        sender=sender,
        body=body,
        reply_to=reply_to,
    )
    room.save(update_fields=["updated_at"])
    return (
        ChatMessage.objects.select_related(
            "sender",
            "sender__profile",
            "reply_to",
            "reply_to__sender",
            "reply_to__sender__profile",
        ).get(pk=message.pk)
    )


@transaction.atomic
def soft_delete_own_chat_message(
    message: ChatMessage, user: AbstractBaseUser
) -> ChatMessage:
    if message.sender_id != user.pk:
        raise ValueError("forbidden")
    if message.is_hidden:
        raise ValueError("already_removed")
    if message.deleted_at is not None:
        return message
    message.deleted_at = timezone.now()
    # body は DB に残すが API では出さない（モデレーション調査用）
    message.save(update_fields=["deleted_at"])
    return message


def serialize_reply_preview(target: ChatMessage | None) -> dict[str, Any] | None:
    if target is None:
        return None
    unavailable = bool(target.is_hidden or target.deleted_at)
    if unavailable:
        preview = DELETED_PREVIEW if target.deleted_at else HIDDEN_PREVIEW
        sender_name = ""
    else:
        preview = (target.body or "")[:REPLY_PREVIEW_MAX]
        sender_name = (
            user_display_name(target.sender) if target.sender_id else "ユーザー"
        )
    return {
        "id": target.pk,
        "sender_name": sender_name,
        "text_preview": preview,
        "is_unavailable": unavailable,
    }


def serialize_chat_message(
    message: ChatMessage,
    current_user_id: int,
    *,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    created = timezone.localtime(message.created_at)
    is_deleted = bool(message.deleted_at)
    payload: dict[str, Any] = {
        "id": message.pk,
        "sender_id": message.sender_id,
        "sender_name": user_display_name(message.sender)
        if message.sender_id
        else "システム",
        "sender_initial": user_avatar_initial(message.sender)
        if message.sender_id
        else "?",
        "avatar_url": (get_user_avatar_url(message.sender) or "")
        if message.sender_id
        else "",
        "body": "" if is_deleted else message.body,
        "created_at": created.strftime("%m/%d %H:%M"),
        "is_mine": message.sender_id == current_user_id,
        "is_deleted": is_deleted,
        "reply_to": serialize_reply_preview(
            getattr(message, "reply_to", None)
            if message.reply_to_id
            else None
        ),
    }
    if extra:
        payload.update(extra)
    return payload


def visible_chat_messages_qs(room: ChatRoom):
    """モデレーション非表示を除外。ユーザー削除は tombstone として残す。"""
    return room.chat_messages.filter(is_hidden=False).select_related(
        "sender",
        "sender__profile",
        "reply_to",
        "reply_to__sender",
        "reply_to__sender__profile",
    )
