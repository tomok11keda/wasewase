"""授業トーク（ChatRoom kind=course × CourseOffering）。

Group Chat の ChatMessage / ChatRoomMembership / ChatReadState を再利用。
Push 通知は送らない（初期仕様）。
"""

from __future__ import annotations

import logging
from typing import Any

from django.contrib.auth.base_user import AbstractBaseUser
from django.db import IntegrityError, transaction
from django.db.models import Prefetch
from django.utils import timezone

from .course_services import (
    day_label,
    period_label,
    resolve_canonical_offering,
    serialize_offering,
)
from .group_chat_services import (
    count_unread_group_messages,
    get_group_read_state_map,
    mark_group_room_read,
)
from .models import (
    ChatMessage,
    ChatReadState,
    ChatRoom,
    ChatRoomMembership,
    CourseEnrollment,
    CourseOffering,
)
from .services import get_user_avatar_url, user_avatar_initial, user_display_name

logger = logging.getLogger(__name__)


def _course_room_name(offering: CourseOffering) -> str:
    schedule = f"{day_label(offering.day_of_week)}{period_label(offering.period_kind, offering.period)}"
    instructor = (offering.instructor or "").strip()
    if instructor:
        return f"{offering.title}｜{instructor}｜{schedule}"[:120]
    return f"{offering.title}｜{schedule}"[:120]


def enrollment_role_for(
    user: AbstractBaseUser, offering: CourseOffering
) -> str | None:
    """current / past / None（未履修）。Frontend 自己申告禁止・Backend 判定。"""
    if not getattr(user, "is_authenticated", False):
        return None
    role = (
        CourseEnrollment.objects.filter(user=user, offering=offering)
        .values_list("role", flat=True)
        .first()
    )
    return role


def enrollment_roles_map(
    user_ids: list[int], offering: CourseOffering
) -> dict[int, str]:
    if not user_ids:
        return {}
    rows = CourseEnrollment.objects.filter(
        offering=offering, user_id__in=user_ids
    ).values_list("user_id", "role")
    return {uid: role for uid, role in rows}


def is_course_talk_member(room: ChatRoom, user: AbstractBaseUser) -> bool:
    if not getattr(user, "is_authenticated", False):
        return False
    if room.kind != ChatRoom.Kind.COURSE:
        return False
    return ChatRoomMembership.objects.filter(room=room, user=user).exists()


def get_visible_offering_for_talk(offering_pk: int) -> CourseOffering:
    offering = CourseOffering.objects.select_related(
        "course", "chat_room"
    ).get(pk=offering_pk)
    if offering.status == CourseOffering.Status.HIDDEN:
        raise CourseOffering.DoesNotExist()
    try:
        offering = resolve_canonical_offering(offering)
    except ValueError as exc:
        if str(exc) in {
            "offering_hidden",
            "offering_inactive",
            "offering_merge_cycle",
        }:
            raise CourseOffering.DoesNotExist() from exc
        raise
    if offering.status != CourseOffering.Status.ACTIVE:
        raise CourseOffering.DoesNotExist()
    return offering


def _clear_stale_course_talk_fk(offering: CourseOffering, stale_id: int | None) -> None:
    """chat_room_id が欠落 Room を指すとき FK を外す。"""
    logger.warning(
        "course talk stale chat_room_id=%s offering=%s; clearing",
        stale_id,
        offering.pk,
    )
    CourseOffering.objects.filter(pk=offering.pk).update(chat_room_id=None)
    offering.chat_room_id = None


def _load_course_talk_room(chat_room_id: int) -> ChatRoom | None:
    """select_related の None キャッシュに頼らず実在 Room を取る。"""
    return ChatRoom.objects.filter(pk=chat_room_id).first()


@transaction.atomic
def get_or_create_course_talk_room(
    offering: CourseOffering,
    *,
    actor: AbstractBaseUser | None = None,
) -> tuple[ChatRoom, bool]:
    """Offering に紐づく授業トークを安全に get_or_create。

    Returns (room, created).
    """
    locked = CourseOffering.objects.select_for_update().get(pk=offering.pk)
    locked = resolve_canonical_offering(locked)
    locked = CourseOffering.objects.select_for_update().get(pk=locked.pk)

    if locked.chat_room_id:
        # select_related("chat_room") だと欠落 FK が None になり DoesNotExist が
        # 上がらず、後段の race 復旧で ChatRoom.DoesNotExist → save_failed になる。
        room = _load_course_talk_room(locked.chat_room_id)
        if room is None:
            _clear_stale_course_talk_fk(locked, locked.chat_room_id)
        else:
            if room.kind != ChatRoom.Kind.COURSE:
                room.kind = ChatRoom.Kind.COURSE
                room.save(update_fields=["kind", "updated_at"])
            return room, False

    name = _course_room_name(locked)
    try:
        with transaction.atomic():
            room = ChatRoom.objects.create(
                kind=ChatRoom.Kind.COURSE,
                name=name,
                created_by=actor if getattr(actor, "is_authenticated", False) else None,
            )
            updated = CourseOffering.objects.filter(
                pk=locked.pk, chat_room__isnull=True
            ).update(chat_room_id=room.pk)
            if updated != 1:
                room.delete()
                raise IntegrityError("course_talk_race")
            locked.chat_room_id = room.pk
            return room, True
    except IntegrityError:
        locked.refresh_from_db()
        if locked.chat_room_id:
            room = _load_course_talk_room(locked.chat_room_id)
            if room is not None:
                return room, False
            # 孤児 FK のまま raise すると API が save_failed になるため消して再作成
            _clear_stale_course_talk_fk(locked, locked.chat_room_id)
            with transaction.atomic():
                room = ChatRoom.objects.create(
                    kind=ChatRoom.Kind.COURSE,
                    name=_course_room_name(locked),
                    created_by=(
                        actor if getattr(actor, "is_authenticated", False) else None
                    ),
                )
                updated = CourseOffering.objects.filter(
                    pk=locked.pk, chat_room__isnull=True
                ).update(chat_room_id=room.pk)
                if updated != 1:
                    room.delete()
                    locked.refresh_from_db()
                    if locked.chat_room_id:
                        existing = _load_course_talk_room(locked.chat_room_id)
                        if existing is not None:
                            return existing, False
                    raise
                locked.chat_room_id = room.pk
                return room, True
        raise


@transaction.atomic
def join_course_talk(
    user: AbstractBaseUser, offering: CourseOffering
) -> tuple[ChatRoom, ChatRoomMembership, bool]:
    """授業トークを開き、Membership を get_or_create。

    Returns (room, membership, membership_created).
    """
    room, _room_created = get_or_create_course_talk_room(offering, actor=user)
    membership, created = ChatRoomMembership.objects.get_or_create(
        room=room,
        user=user,
        defaults={"role": ChatRoomMembership.Role.MEMBER},
    )
    return room, membership, created


@transaction.atomic
def leave_course_talk(user: AbstractBaseUser, offering: CourseOffering) -> bool:
    """Membership のみ削除。メッセージ履歴は残す。"""
    if not offering.chat_room_id:
        return False
    deleted, _ = ChatRoomMembership.objects.filter(
        room_id=offering.chat_room_id, user=user
    ).delete()
    return deleted > 0


def maybe_auto_join_on_enroll(
    user: AbstractBaseUser, offering: CourseOffering
) -> None:
    """Enrollment(current) 時、既に ChatRoom がある場合のみ自動参加。

    空ルーム大量生成はしない。
    """
    if not offering.chat_room_id:
        return
    try:
        ChatRoomMembership.objects.get_or_create(
            room_id=offering.chat_room_id,
            user=user,
            defaults={"role": ChatRoomMembership.Role.MEMBER},
        )
    except Exception:
        logger.exception(
            "course talk auto-join failed user=%s offering=%s",
            getattr(user, "pk", None),
            offering.pk,
        )


def serialize_course_talk_message(
    message: ChatMessage,
    current_user_id: int,
    *,
    enrollment_role: str | None = None,
) -> dict[str, Any]:
    from .chat_message_services import serialize_chat_message

    role_label = None
    if enrollment_role == CourseEnrollment.Role.CURRENT:
        role_label = "履修中"
    elif enrollment_role == CourseEnrollment.Role.PAST:
        role_label = "履修済み"
    return serialize_chat_message(
        message,
        current_user_id,
        extra={
            "enrollment_role": enrollment_role,
            "enrollment_label": role_label,
        },
    )


def visible_course_messages_qs(room: ChatRoom):
    from .chat_message_services import visible_chat_messages_qs

    return visible_chat_messages_qs(room)


def build_course_talk_payload(
    room: ChatRoom,
    offering: CourseOffering,
    viewer: AbstractBaseUser,
    *,
    joined_now: bool = False,
) -> dict[str, Any]:
    mark_group_room_read(room, viewer)
    messages = list(visible_course_messages_qs(room).order_by("created_at"))
    sender_ids = [m.sender_id for m in messages if m.sender_id]
    roles = enrollment_roles_map(sender_ids, offering)
    viewer_role = enrollment_role_for(viewer, offering)
    latest_id = messages[-1].pk if messages else 0
    return {
        "ok": True,
        "joined": True,
        "joined_now": joined_now,
        "offering": serialize_offering(offering, viewer=viewer),
        "viewer_enrollment": viewer_role,
        "room": {
            "id": room.pk,
            "kind": "course",
            "name": room.name or _course_room_name(offering),
            "offering_id": offering.pk,
            "can_send": True,
            "membership_status": "member",
            "latest_id": latest_id,
            "member_count": ChatRoomMembership.objects.filter(room=room).count(),
        },
        "messages": [
            serialize_course_talk_message(
                m,
                viewer.pk,
                enrollment_role=roles.get(m.sender_id),
            )
            for m in messages
        ],
    }


def build_course_talk_messages_payload(
    room: ChatRoom,
    offering: CourseOffering,
    viewer: AbstractBaseUser,
    *,
    after: str = "",
) -> dict[str, Any]:
    qs = visible_course_messages_qs(room).order_by("created_at")
    if after.isdigit():
        qs = qs.filter(pk__gt=int(after))
    messages = list(qs)
    roles = enrollment_roles_map(
        [m.sender_id for m in messages if m.sender_id], offering
    )
    mark_group_room_read(room, viewer)
    latest_id = (
        visible_course_messages_qs(room)
        .order_by("-pk")
        .values_list("pk", flat=True)
        .first()
        or 0
    )
    return {
        "ok": True,
        "messages": [
            serialize_course_talk_message(
                m,
                viewer.pk,
                enrollment_role=roles.get(m.sender_id),
            )
            for m in messages
        ],
        "latest_id": latest_id,
        "can_send": is_course_talk_member(room, viewer),
    }


def send_course_talk_message(
    room: ChatRoom,
    sender: AbstractBaseUser,
    body: str,
    *,
    reply_to_id: int | None = None,
) -> ChatMessage:
    from .chat_message_services import create_chat_message

    if not is_course_talk_member(room, sender):
        raise ValueError("forbidden")
    if room.kind != ChatRoom.Kind.COURSE:
        raise ValueError("forbidden")
    # Push / in-app Notification: intentionally OFF for course talk (spam risk)
    return create_chat_message(room, sender, body, reply_to_id=reply_to_id)


def list_course_talk_rooms_for_user(user: AbstractBaseUser):
    latest_message = Prefetch(
        "chat_messages",
        queryset=ChatMessage.objects.filter(is_hidden=False)
        .select_related("sender")
        .order_by("-pk")[:1],
        to_attr="latest_messages",
    )
    return (
        ChatRoom.objects.filter(
            kind=ChatRoom.Kind.COURSE,
            memberships__user=user,
            course_offering__isnull=False,
            course_offering__status=CourseOffering.Status.ACTIVE,
        )
        .select_related("course_offering", "course_offering__course")
        .prefetch_related(latest_message)
        .distinct()
        .order_by("-updated_at")
    )


def build_course_talk_conversations(user: AbstractBaseUser) -> list[dict]:
    rooms = list(list_course_talk_rooms_for_user(user))
    room_ids = [r.pk for r in rooms]
    read_map = get_group_read_state_map(user, room_ids)
    offering_ids = [
        r.course_offering.pk
        for r in rooms
        if getattr(r, "course_offering", None) is not None
    ]
    enroll_map = {
        oid: role
        for oid, role in CourseEnrollment.objects.filter(
            user=user, offering_id__in=offering_ids
        ).values_list("offering_id", "role")
    }
    membership_joined = {
        mid: joined
        for mid, joined in ChatRoomMembership.objects.filter(
            room_id__in=room_ids, user=user
        ).values_list("room_id", "joined_at")
    }
    conversations = []
    for room in rooms:
        offering = room.course_offering
        if offering is None:
            continue
        latest = room.latest_messages[0] if room.latest_messages else None
        role = enroll_map.get(offering.pk)
        status_label = ""
        if role == CourseEnrollment.Role.CURRENT:
            status_label = "履修中"
        elif role == CourseEnrollment.Role.PAST:
            status_label = "履修済み"
        schedule = (
            f"{day_label(offering.day_of_week)}"
            f"{period_label(offering.period_kind, offering.period)}"
        )
        updated_at = (
            latest.created_at
            if latest
            else membership_joined.get(room.pk) or room.updated_at
        )
        conversations.append(
            {
                "kind": "course",
                "room": room,
                "offering": offering,
                "offering_id": offering.pk,
                "display_name": offering.title,
                "subtitle": f"{offering.instructor}｜{schedule}",
                "status_label": status_label,
                "latest_message": latest,
                "latest_sender_display_name": (
                    user_display_name(latest.sender)
                    if latest and latest.sender_id
                    else ""
                ),
                "unread_count": count_unread_group_messages(
                    room, user, read_map.get(room.pk, 0)
                ),
                "updated_at": updated_at,
                "thumbnail_url": "",
                "partner": None,
                "product": None,
                "is_blocked": False,
            }
        )
    return conversations


def build_course_talk_unread_summary(user: AbstractBaseUser) -> dict:
    conversations = build_course_talk_conversations(user)
    rooms = [
        {
            "kind": "course",
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


@transaction.atomic
def merge_course_talk_rooms(
    source: CourseOffering, target: CourseOffering
) -> None:
    """Offering merge 時に授業トークを canonical へ統合。"""
    source = CourseOffering.objects.select_for_update().select_related(
        "chat_room"
    ).get(pk=source.pk)
    target = CourseOffering.objects.select_for_update().select_related(
        "chat_room"
    ).get(pk=target.pk)

    source_room = source.chat_room
    if source_room is None:
        return

    target_room = target.chat_room
    if target_room is None:
        source.chat_room = None
        source.save(update_fields=["chat_room", "updated_at"])
        target.chat_room = source_room
        target.save(update_fields=["chat_room", "updated_at"])
        source_room.name = _course_room_name(target)
        source_room.kind = ChatRoom.Kind.COURSE
        source_room.save(update_fields=["name", "kind", "updated_at"])
        return

    if source_room.pk == target_room.pk:
        source.chat_room = None
        source.save(update_fields=["chat_room", "updated_at"])
        return

    # Move memberships (dedupe)
    for membership in ChatRoomMembership.objects.select_for_update().filter(
        room=source_room
    ):
        exists = ChatRoomMembership.objects.filter(
            room=target_room, user_id=membership.user_id
        ).exists()
        if exists:
            membership.delete()
        else:
            membership.room = target_room
            membership.save(update_fields=["room"])

    # Move messages
    ChatMessage.objects.filter(room=source_room).update(room=target_room)

    # Merge read states — keep the higher last_read_message_id
    for state in ChatReadState.objects.select_for_update().filter(room=source_room):
        existing = (
            ChatReadState.objects.select_for_update()
            .filter(room=target_room, user_id=state.user_id)
            .first()
        )
        if existing:
            if state.last_read_message_id > existing.last_read_message_id:
                existing.last_read_message_id = state.last_read_message_id
                existing.save(update_fields=["last_read_message_id", "updated_at"])
            state.delete()
        else:
            state.room = target_room
            state.save(update_fields=["room", "updated_at"])

    source.chat_room = None
    source.save(update_fields=["chat_room", "updated_at"])
    target_room.name = _course_room_name(target)
    target_room.save(update_fields=["name", "updated_at"])
    source_room.delete()
