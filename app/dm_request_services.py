"""フォロー外ユーザーからの DM をメッセージリクエストとして扱う。"""

from __future__ import annotations

import logging
from typing import Any

from django.contrib.auth.models import AbstractBaseUser
from django.db import connection
from django.db.utils import OperationalError, ProgrammingError
from django.utils import timezone

from .dm_services import dm_room_link
from .models import (
    Notification,
    UserDirectMessage,
    UserDirectMessageRequest,
    UserDirectMessageRoom,
)
from .services import is_following, user_display_name
from .ugc_services import is_user_blocked

logger = logging.getLogger(__name__)


def ensure_user_direct_message_request_table() -> None:
    """本番 DB にメッセージリクエスト表が無い場合に作成する（起動時セーフティネット）。"""
    table = UserDirectMessageRequest._meta.db_table
    try:
        with connection.cursor() as cursor:
            if table in connection.introspection.table_names(cursor):
                return
        with connection.schema_editor() as schema_editor:
            schema_editor.create_model(UserDirectMessageRequest)
        logger.warning("Created missing %s table on startup", table)
    except (OperationalError, ProgrammingError) as exc:
        message = str(exc).lower()
        if "already exists" in message or "duplicate" in message:
            return
        logger.warning("DM message request table repair failed: %s", exc)
    except Exception as exc:
        logger.warning("DM message request table repair failed: %s", exc)


def get_pending_dm_request_for_recipient(
    room: UserDirectMessageRoom, user: AbstractBaseUser
) -> UserDirectMessageRequest | None:
    if not getattr(user, "is_authenticated", False):
        return None
    try:
        return (
            UserDirectMessageRequest.objects.filter(
                room=room,
                to_user=user,
                status=UserDirectMessageRequest.Status.PENDING,
            )
            .select_related("from_user", "from_user__profile")
            .first()
        )
    except (OperationalError, ProgrammingError) as exc:
        logger.warning("DM request lookup failed: %s", exc)
        return None


def pending_dm_request_room_ids_for(user: AbstractBaseUser) -> set[int]:
    try:
        return set(
            UserDirectMessageRequest.objects.filter(
                to_user=user,
                status=UserDirectMessageRequest.Status.PENDING,
            ).values_list("room_id", flat=True)
        )
    except (OperationalError, ProgrammingError) as exc:
        logger.warning("DM pending room ids lookup failed: %s", exc)
        return set()


def count_pending_dm_requests(user: AbstractBaseUser) -> int:
    try:
        return UserDirectMessageRequest.objects.filter(
            to_user=user,
            status=UserDirectMessageRequest.Status.PENDING,
        ).count()
    except (OperationalError, ProgrammingError) as exc:
        logger.warning("DM pending request count failed: %s", exc)
        return 0


def ensure_message_request_after_send(
    room: UserDirectMessageRoom,
    sender: AbstractBaseUser,
    recipient: AbstractBaseUser,
    *,
    preview_body: str,
) -> UserDirectMessageRequest | None:
    """
    送信後に必要なら pending リクエストを作成／復活し、通知する。
    通常 DM の場合は None。
    """
    if not recipient or is_user_blocked(recipient, sender):
        return None

    try:
        ensure_user_direct_message_request_table()
        existing = UserDirectMessageRequest.objects.filter(
            room=room, to_user=recipient
        ).first()

        if existing and existing.status == UserDirectMessageRequest.Status.ACCEPTED:
            return None

        if is_following(recipient, sender):
            if existing and existing.status == UserDirectMessageRequest.Status.PENDING:
                # フォロー後の未処理リクエストは通常 DM へ自動昇格
                existing.status = UserDirectMessageRequest.Status.ACCEPTED
                existing.responded_at = timezone.now()
                existing.save(update_fields=["status", "responded_at", "updated_at"])
            return None

        # 既存ルームでリクエスト未作成かつ過去メッセージあり → 通常（grandfather）
        prior_count = UserDirectMessage.objects.filter(room=room).count()
        # 直前に作った 1 通を含む。2 通以上なら既存会話。
        if prior_count > 1 and existing is None:
            return None

        if existing and existing.status == UserDirectMessageRequest.Status.PENDING:
            existing.from_user = sender
            existing.save(update_fields=["from_user", "updated_at"])
            _notify_message_request(
                recipient=recipient,
                sender=sender,
                room=room,
                preview_body=preview_body,
                is_follow_up=True,
            )
            return existing

        if existing and existing.status == UserDirectMessageRequest.Status.DECLINED:
            existing.status = UserDirectMessageRequest.Status.PENDING
            existing.from_user = sender
            existing.responded_at = None
            existing.save(
                update_fields=["status", "from_user", "responded_at", "updated_at"]
            )
            _notify_message_request(
                recipient=recipient,
                sender=sender,
                room=room,
                preview_body=preview_body,
                is_follow_up=False,
            )
            return existing

        request = UserDirectMessageRequest.objects.create(
            room=room,
            from_user=sender,
            to_user=recipient,
            status=UserDirectMessageRequest.Status.PENDING,
        )
        _notify_message_request(
            recipient=recipient,
            sender=sender,
            room=room,
            preview_body=preview_body,
            is_follow_up=False,
        )
        return request
    except (OperationalError, ProgrammingError) as exc:
        logger.warning("ensure_message_request_after_send failed: %s", exc)
        return None


def _notify_message_request(
    *,
    recipient: AbstractBaseUser,
    sender: AbstractBaseUser,
    room: UserDirectMessageRoom,
    preview_body: str,
    is_follow_up: bool,
) -> None:
    name = user_display_name(sender)
    if is_follow_up:
        message = f"{name}さんからメッセージリクエストに新しいメッセージがあります"
    else:
        message = f"{name}さんからメッセージリクエストが届きました"
    Notification.objects.create(
        recipient=recipient,
        message=message,
        link=dm_room_link(room),
    )


def resolve_dm_request_notifications(
    recipient: AbstractBaseUser,
    room: UserDirectMessageRoom,
    *,
    accepted: bool,
) -> None:
    new_message = (
        "メッセージリクエストを承認し、チャットを開始しました"
        if accepted
        else "メッセージリクエストを拒否しました"
    )
    notes = Notification.objects.filter(recipient=recipient)
    for note in notes:
        if "メッセージリクエスト" not in (note.message or ""):
            continue
        if not _notification_link_matches_dm_room(note.link or "", room.pk):
            continue
        note.message = new_message
        note.is_read = True
        note.save(update_fields=["message", "is_read"])


def _notification_link_matches_dm_room(link: str, room_pk: int) -> bool:
    """/dm/{pk} と /dm/{pk}0 のような prefix 衝突を避ける。"""
    path = (link or "").split("?", 1)[0].rstrip("/")
    if "/dm/groups/" in path:
        return False
    return path.endswith(f"/dm/{room_pk}")


def accept_dm_request(
    room: UserDirectMessageRoom, user: AbstractBaseUser
) -> UserDirectMessageRequest:
    request = get_pending_dm_request_for_recipient(room, user)
    if request is None:
        raise ValueError("no_request")
    request.status = UserDirectMessageRequest.Status.ACCEPTED
    request.responded_at = timezone.now()
    request.save(update_fields=["status", "responded_at", "updated_at"])
    resolve_dm_request_notifications(user, room, accepted=True)
    room.save(update_fields=["updated_at"])
    return request


def decline_dm_request(
    room: UserDirectMessageRoom, user: AbstractBaseUser
) -> UserDirectMessageRequest:
    request = get_pending_dm_request_for_recipient(room, user)
    if request is None:
        raise ValueError("no_request")
    request.status = UserDirectMessageRequest.Status.DECLINED
    request.responded_at = timezone.now()
    request.save(update_fields=["status", "responded_at", "updated_at"])
    resolve_dm_request_notifications(user, room, accepted=False)
    return request


def can_access_dm_room_for_viewer(
    room: UserDirectMessageRoom, user: AbstractBaseUser
) -> bool:
    """拒否済みリクエストの受信者はルームを開けない。"""
    from .dm_services import can_access_dm_room

    if not can_access_dm_room(room, user):
        return False
    try:
        declined = UserDirectMessageRequest.objects.filter(
            room=room,
            to_user=user,
            status=UserDirectMessageRequest.Status.DECLINED,
        ).exists()
        return not declined
    except (OperationalError, ProgrammingError) as exc:
        logger.warning("DM request access check failed: %s", exc)
        return True


def recipient_can_send_in_dm(
    room: UserDirectMessageRoom, user: AbstractBaseUser
) -> bool:
    """pending リクエスト受信中は送信不可。"""
    return get_pending_dm_request_for_recipient(room, user) is None


def serialize_dm_request_item(
    request: UserDirectMessageRequest,
) -> dict[str, Any]:
    from .timeline_api_services import serialize_author

    sender = request.from_user
    profile = getattr(sender, "profile", None)
    latest = (
        UserDirectMessage.objects.filter(room=request.room)
        .order_by("-pk")
        .first()
    )
    author = serialize_author(sender) or {}
    return {
        "id": request.pk,
        "room_id": request.room_id,
        "status": request.status,
        "from_user": {
            **author,
            "department": (getattr(profile, "department", None) or ""),
            "grade": (getattr(profile, "grade", None) or ""),
        },
        "preview": (latest.body if latest else "")[:120],
        "updated_at": (
            (request.updated_at or request.created_at).isoformat()
            if (request.updated_at or request.created_at)
            else ""
        ),
        "spa_path": f"/dm/{request.room_id}",
    }


def list_pending_dm_requests_payload(
    user: AbstractBaseUser,
) -> dict[str, Any]:
    try:
        rows = (
            UserDirectMessageRequest.objects.filter(
                to_user=user,
                status=UserDirectMessageRequest.Status.PENDING,
            )
            .select_related(
                "from_user",
                "from_user__profile",
                "room",
            )
            .order_by("-updated_at")
        )
        items = [serialize_dm_request_item(row) for row in rows]
    except (OperationalError, ProgrammingError) as exc:
        logger.warning("list_pending_dm_requests failed: %s", exc)
        items = []
    return {
        "ok": True,
        "count": len(items),
        "requests": items,
    }
