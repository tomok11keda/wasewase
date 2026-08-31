"""グループチャット招待（承認制）ヘルパー。"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from django.contrib.auth.models import AbstractBaseUser
from django.db import IntegrityError, transaction
from django.utils import timezone

from .group_chat_services import group_room_link, is_group_member
from .models import (
    ChatMessage,
    ChatRoom,
    ChatRoomInvitation,
    ChatRoomMembership,
    Notification,
)
from .services import search_users, user_display_name
from .ugc_services import is_either_blocked, is_user_blocked

MAX_INVITES_PER_BATCH = 20
MAX_PENDING_INVITES_PER_HOUR = 60


def get_pending_invitation(
    room: ChatRoom, user: AbstractBaseUser
) -> ChatRoomInvitation | None:
    if not getattr(user, "is_authenticated", False):
        return None
    return (
        ChatRoomInvitation.objects.filter(
            room=room,
            invitee=user,
            status=ChatRoomInvitation.Status.PENDING,
        )
        .select_related("inviter", "inviter__profile")
        .first()
    )


def can_view_group_room(room: ChatRoom, user: AbstractBaseUser) -> bool:
    """正式メンバー、または pending 招待の受信者ならルームを開ける。"""
    if not getattr(user, "is_authenticated", False):
        return False
    if room.kind != ChatRoom.Kind.GROUP:
        return False
    if is_group_member(room, user):
        return True
    return get_pending_invitation(room, user) is not None


def _group_display_name(room: ChatRoom) -> str:
    return (room.name or "").strip() or f"グループ #{room.pk}"


def _notify_group_invite(
    *,
    invitee: AbstractBaseUser,
    inviter: AbstractBaseUser,
    room: ChatRoom,
) -> None:
    if is_user_blocked(invitee, inviter):
        return
    room_name = _group_display_name(room)
    inviter_name = user_display_name(inviter)
    Notification.objects.create(
        recipient=invitee,
        message=f"{inviter_name}さんから『{room_name}』への招待が届いています",
        link=group_room_link(room),
    )


def _resolve_invite_notifications(
    invitee: AbstractBaseUser,
    room: ChatRoom,
    *,
    accepted: bool,
) -> None:
    room_name = _group_display_name(room)
    new_message = (
        f"『{room_name}』への招待に参加しました"
        if accepted
        else f"『{room_name}』への招待を辞退しました"
    )
    notifications = Notification.objects.filter(recipient=invitee)
    for note in notifications:
        if "招待" not in (note.message or ""):
            continue
        if not _notification_link_matches_group_room(note.link or "", room.pk):
            continue
        note.message = new_message
        note.is_read = True
        note.save(update_fields=["message", "is_read"])


def _notification_link_matches_group_room(link: str, room_pk: int) -> bool:
    path = (link or "").split("?", 1)[0].rstrip("/")
    return path.endswith(f"/dm/groups/{room_pk}")


def _assert_invite_rate_limit(inviter: AbstractBaseUser, batch_size: int) -> None:
    if batch_size > MAX_INVITES_PER_BATCH:
        raise ValueError("too_many_invites")
    since = timezone.now() - timedelta(hours=1)
    recent = ChatRoomInvitation.objects.filter(
        inviter=inviter,
        created_at__gte=since,
    ).count()
    if recent + batch_size > MAX_PENDING_INVITES_PER_HOUR:
        raise ValueError("rate_limited")


def create_or_refresh_invitations(
    room: ChatRoom,
    inviter: AbstractBaseUser,
    invitee_ids: list[int],
) -> list[ChatRoomInvitation]:
    """
    招待を作成または declined→pending に戻す。
    既にメンバー / pending のユーザーはスキップ。
    """
    selected = {int(x) for x in invitee_ids if int(x) != inviter.id}
    if not selected:
        raise ValueError("no_invitees")
    _assert_invite_rate_limit(inviter, len(selected))

    from django.contrib.auth import get_user_model

    User = get_user_model()
    candidates = list(User.objects.filter(pk__in=selected, is_active=True))
    if not candidates:
        raise ValueError("no_invitees")

    member_ids = set(
        ChatRoomMembership.objects.filter(room=room).values_list("user_id", flat=True)
    )
    created: list[ChatRoomInvitation] = []
    with transaction.atomic():
        for user in candidates:
            if user.pk in member_ids:
                continue
            if is_either_blocked(inviter, user):
                continue
            existing = ChatRoomInvitation.objects.filter(
                room=room, invitee=user
            ).first()
            if existing and existing.status == ChatRoomInvitation.Status.PENDING:
                continue
            if existing and existing.status == ChatRoomInvitation.Status.ACCEPTED:
                # Membership missing somehow — skip
                continue
            if existing and existing.status == ChatRoomInvitation.Status.DECLINED:
                existing.status = ChatRoomInvitation.Status.PENDING
                existing.inviter = inviter
                existing.responded_at = None
                existing.save(
                    update_fields=["status", "inviter", "responded_at", "updated_at"]
                )
                invitation = existing
            else:
                try:
                    invitation = ChatRoomInvitation.objects.create(
                        room=room,
                        inviter=inviter,
                        invitee=user,
                        status=ChatRoomInvitation.Status.PENDING,
                    )
                except IntegrityError:
                    continue
            created.append(invitation)
            _notify_group_invite(invitee=user, inviter=inviter, room=room)
            room.save(update_fields=["updated_at"])
    if not created and not candidates:
        raise ValueError("no_invitees")
    return created


def accept_group_invitation(
    room: ChatRoom, user: AbstractBaseUser
) -> ChatRoomMembership:
    invitation = get_pending_invitation(room, user)
    if invitation is None:
        if is_group_member(room, user):
            return ChatRoomMembership.objects.get(room=room, user=user)
        raise ValueError("no_invitation")
    with transaction.atomic():
        membership, _ = ChatRoomMembership.objects.get_or_create(
            room=room,
            user=user,
            defaults={"role": ChatRoomMembership.Role.MEMBER},
        )
        invitation.status = ChatRoomInvitation.Status.ACCEPTED
        invitation.responded_at = timezone.now()
        invitation.save(update_fields=["status", "responded_at", "updated_at"])
        ChatMessage.objects.create(
            room=room,
            sender=user,
            body=f"{user_display_name(user)}さんがグループに参加しました",
        )
        room.save(update_fields=["updated_at"])
    _resolve_invite_notifications(user, room, accepted=True)
    return membership


def decline_group_invitation(room: ChatRoom, user: AbstractBaseUser) -> None:
    invitation = get_pending_invitation(room, user)
    if invitation is None:
        raise ValueError("no_invitation")
    invitation.status = ChatRoomInvitation.Status.DECLINED
    invitation.responded_at = timezone.now()
    invitation.save(update_fields=["status", "responded_at", "updated_at"])
    _resolve_invite_notifications(user, room, accepted=False)


def list_pending_invitations_for_user(
    user: AbstractBaseUser,
) -> list[ChatRoomInvitation]:
    return list(
        ChatRoomInvitation.objects.filter(
            invitee=user,
            status=ChatRoomInvitation.Status.PENDING,
            room__kind=ChatRoom.Kind.GROUP,
        )
        .select_related(
            "room",
            "inviter",
            "inviter__profile",
        )
        .order_by("-updated_at")
    )


def build_group_invite_conversations(user: AbstractBaseUser) -> list[dict]:
    conversations = []
    for invitation in list_pending_invitations_for_user(user):
        room = invitation.room
        inviter_name = user_display_name(invitation.inviter)
        conversations.append(
            {
                "kind": "group_invite",
                "room": room,
                "invitation": invitation,
                "partner": invitation.inviter,
                "display_name": _group_display_name(room),
                "subtitle": f"{inviter_name}さんから招待されています",
                "status_label": "招待あり",
                "latest_message": None,
                "latest_sender_display_name": "",
                "unread_count": 1,
                "updated_at": invitation.updated_at or invitation.created_at,
                "thumbnail_url": "",
                "product": None,
                "is_blocked": False,
            }
        )
    return conversations


def serialize_invitation(invitation: ChatRoomInvitation) -> dict[str, Any]:
    from .timeline_api_services import serialize_author

    return {
        "id": invitation.pk,
        "status": invitation.status,
        "inviter": serialize_author(invitation.inviter),
        "created_at": invitation.created_at.isoformat()
        if invitation.created_at
        else "",
    }


def list_invite_candidates(
    viewer: AbstractBaseUser, *, query: str = ""
) -> list[dict[str, Any]]:
    """招待先候補。空クエリ時はフォロー中、入力時は全体検索。"""
    from .services import get_following_user_ids
    from .timeline_api_services import serialize_author

    q = (query or "").strip()
    if q:
        users = list(search_users(q, viewer=viewer)[:40])
    else:
        from django.contrib.auth import get_user_model

        User = get_user_model()
        following_ids = set(get_following_user_ids(viewer))
        following_ids.discard(viewer.id)
        users = list(
            User.objects.filter(id__in=following_ids, is_active=True).select_related(
                "profile"
            )[:80]
        )
    return [
        serialize_author(u)
        for u in users
        if u.pk != viewer.id and not is_either_blocked(viewer, u)
    ]


def list_pending_invites_for_room(room: ChatRoom) -> list[dict[str, Any]]:
    from .timeline_api_services import serialize_author

    rows = (
        ChatRoomInvitation.objects.filter(
            room=room, status=ChatRoomInvitation.Status.PENDING
        )
        .select_related("invitee", "invitee__profile", "inviter", "inviter__profile")
        .order_by("-created_at")
    )
    return [
        {
            "id": row.pk,
            "invitee": serialize_author(row.invitee),
            "inviter": serialize_author(row.inviter),
            "status": row.status,
        }
        for row in rows
    ]
