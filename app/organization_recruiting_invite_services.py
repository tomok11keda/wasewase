"""新歓チャットへの運営者招待。グループDM招待 API とは分離する。"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any, Callable

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AbstractBaseUser
from django.db import IntegrityError, OperationalError, transaction
from django.db.models import Q
from django.utils import timezone

from .follow_services import can_view_private_content
from .models import (
    ChatRoom,
    ChatRoomInvitation,
    ChatRoomMembership,
    Notification,
    OrganizationRecruitingChat,
    OrganizationRecruitingChatApplication,
)
from .notification_services import PUSH_KIND_RECRUITING_INVITE, create_notification
from .organization_recruiting_chat_services import (
    OrganizationRecruitingChatError,
    _ensure_membership,
    _get_or_lock_application,
    _lock_chat,
    _mark_application_approved,
    organization_allows_recruiting_access,
    serialize_recruiting_chat_for_viewer,
)
from .organization_services import (
    can_manage_organization,
    can_view_organization_profile,
)
from .services import search_users
from .spa_canonical import recruiting_invite_spa_path, recruiting_invite_url
from .timeline_api_services import serialize_author
from .ugc_services import is_either_blocked

User = get_user_model()
logger = logging.getLogger(__name__)

MAX_INVITES_PER_BATCH = 20
# 管理者1人あたり。同一団体の複数管理者は下の room 上限が効く。
MAX_RECRUITING_INVITES_PER_HOUR = 60
# 新歓チャット1件あたり。owner+admin が同時に送っても団体として60人/時。
MAX_RECRUITING_INVITES_PER_ROOM_HOUR = 60
CANDIDATE_QUERY_MIN = 2
CANDIDATE_RESULT_LIMIT = 20
DECLINE_COOLDOWN = timedelta(days=30)

SKIP_SELF = "self"
SKIP_ALREADY_MEMBER = "already_member"
SKIP_ALREADY_PENDING = "already_pending"
SKIP_BLOCKED = "blocked"
SKIP_COOLDOWN = "cooldown"
SKIP_INACTIVE = "inactive"
SKIP_PRIVATE = "private"
SKIP_INVALID = "invalid"


def _authenticated_user(user: AbstractBaseUser | None) -> bool:
    return bool(
        user is not None
        and getattr(user, "pk", None)
        and getattr(user, "is_authenticated", False)
        and getattr(user, "is_active", True)
    )


def assert_can_manage_recruiting_invites(
    actor: AbstractBaseUser | None, chat: OrganizationRecruitingChat
) -> None:
    if not _authenticated_user(actor):
        raise OrganizationRecruitingChatError("unauthorized", status=401)
    organization = chat.organization
    if not organization_allows_recruiting_access(organization):
        raise OrganizationRecruitingChatError("organization_suspended", status=403)
    if not can_manage_organization(actor, organization):
        raise OrganizationRecruitingChatError("forbidden", status=403)
    if not chat.is_active:
        raise OrganizationRecruitingChatError("inactive", status=404)


def assert_can_send_recruiting_invites(
    actor: AbstractBaseUser | None, chat: OrganizationRecruitingChat
) -> None:
    assert_can_manage_recruiting_invites(actor, chat)
    if chat.listing_status != OrganizationRecruitingChat.ListingStatus.OPEN:
        raise OrganizationRecruitingChatError("listing_closed", status=403)


def get_pending_recruiting_invitation(
    chat: OrganizationRecruitingChat | None, user: AbstractBaseUser | None
) -> ChatRoomInvitation | None:
    if chat is None or not _authenticated_user(user):
        return None
    if chat.room.kind != ChatRoom.Kind.RECRUITING:
        return None
    return (
        ChatRoomInvitation.objects.filter(
            room=chat.room,
            invitee=user,
            status=ChatRoomInvitation.Status.PENDING,
        )
        .select_related("inviter", "inviter__profile")
        .first()
    )


def get_recruiting_invitation_for_invitee(
    invitation_id: int, user: AbstractBaseUser | None
) -> ChatRoomInvitation:
    if not _authenticated_user(user):
        raise OrganizationRecruitingChatError("unauthorized", status=401)
    invitation = (
        ChatRoomInvitation.objects.select_related(
            "room",
            "room__organization_recruiting_chat",
            "room__organization_recruiting_chat__organization",
            "inviter",
            "inviter__profile",
            "invitee",
            "invitee__profile",
        )
        .filter(pk=invitation_id, room__kind=ChatRoom.Kind.RECRUITING)
        .first()
    )
    if invitation is None or invitation.invitee_id != user.pk:
        raise OrganizationRecruitingChatError("not_found", status=404)
    return invitation


def serialize_recruiting_invitation(
    invitation: ChatRoomInvitation,
    *,
    include_invitee: bool = False,
) -> dict[str, Any]:
    from .organization_api_services import get_organization_avatar_url

    chat = getattr(invitation.room, "organization_recruiting_chat", None)
    organization = getattr(chat, "organization", None) if chat is not None else None
    payload: dict[str, Any] = {
        "id": invitation.pk,
        "status": invitation.status,
        "created_at": invitation.created_at.isoformat() if invitation.created_at else "",
        "responded_at": (
            invitation.responded_at.isoformat() if invitation.responded_at else None
        ),
        "organization_id": getattr(organization, "pk", None),
        "organization_slug": getattr(organization, "slug", "") or "",
        "organization_name": getattr(organization, "name", "") or "",
        "organization_avatar_url": (
            get_organization_avatar_url(organization) if organization is not None else ""
        ),
        "chat_name": (getattr(chat, "name", None) or invitation.room.name or ""),
        "inviter": serialize_author(invitation.inviter),
    }
    if include_invitee:
        payload["invitee"] = serialize_author(invitation.invitee)
    return payload


def serialize_invitee_preview(user: AbstractBaseUser) -> dict[str, Any]:
    author = serialize_author(user) or {}
    return {
        "id": user.pk,
        "username": author.get("username", ""),
        "display_name": author.get("display_name", ""),
        "avatar_url": author.get("avatar_url", ""),
        "initial": author.get("initial") or (author.get("display_name") or "?")[:1],
    }


def _cooldown_active(invitation: ChatRoomInvitation | None) -> bool:
    if invitation is None:
        return False
    if invitation.status != ChatRoomInvitation.Status.DECLINED:
        return False
    stamp = invitation.responded_at or invitation.updated_at
    if stamp is None:
        return True
    return timezone.now() - stamp < DECLINE_COOLDOWN


def _invitee_skip_reason(
    *,
    actor: AbstractBaseUser,
    invitee: AbstractBaseUser | None,
    member_ids: set[int],
    pending_ids: set[int],
    existing: ChatRoomInvitation | None,
) -> str | None:
    if invitee is None or not getattr(invitee, "is_active", False):
        return SKIP_INACTIVE
    if invitee.pk == actor.pk:
        return SKIP_SELF
    if invitee.pk in member_ids:
        return SKIP_ALREADY_MEMBER
    if invitee.pk in pending_ids or (
        existing is not None and existing.status == ChatRoomInvitation.Status.PENDING
    ):
        return SKIP_ALREADY_PENDING
    if is_either_blocked(actor, invitee):
        return SKIP_BLOCKED
    if not can_view_private_content(actor, invitee):
        return SKIP_PRIVATE
    if _cooldown_active(existing):
        return SKIP_COOLDOWN
    return None


def _is_write_contention(exc: BaseException) -> bool:
    text = str(exc).lower()
    return "locked" in text or "deadlock" in text


def _run_after_commit(fn: Callable[[], None]) -> None:
    """Notify only after the invite row is committed. Nested atomic rollback discards this."""

    def _runner() -> None:
        try:
            fn()
        except Exception:
            logger.exception("recruiting invite after-commit callback failed")

    transaction.on_commit(_runner)


def _recent_recruiting_invite_count(
    *,
    inviter: AbstractBaseUser | None = None,
    room: ChatRoom | None = None,
) -> int:
    """作成または pending への再開が直近1時間の行。skip 分は含めない。"""
    since = timezone.now() - timedelta(hours=1)
    qs = ChatRoomInvitation.objects.filter(room__kind=ChatRoom.Kind.RECRUITING).filter(
        Q(created_at__gte=since)
        | Q(
            status=ChatRoomInvitation.Status.PENDING,
            updated_at__gte=since,
        )
    )
    if inviter is not None:
        qs = qs.filter(inviter=inviter)
    if room is not None:
        qs = qs.filter(room=room)
    return qs.count()


def _assert_batch_size(batch_size: int) -> None:
    if batch_size > MAX_INVITES_PER_BATCH:
        raise OrganizationRecruitingChatError(
            "too_many_invites",
            status=400,
            max=MAX_INVITES_PER_BATCH,
        )


def _assert_invite_quota(
    *,
    inviter: AbstractBaseUser,
    room: ChatRoom,
    additional: int,
) -> None:
    if additional <= 0:
        return
    if (
        _recent_recruiting_invite_count(inviter=inviter) + additional
        > MAX_RECRUITING_INVITES_PER_HOUR
    ):
        raise OrganizationRecruitingChatError("rate_limited", status=429)
    if (
        _recent_recruiting_invite_count(room=room) + additional
        > MAX_RECRUITING_INVITES_PER_ROOM_HOUR
    ):
        raise OrganizationRecruitingChatError("rate_limited", status=429)


def list_recruiting_invite_candidates(
    *,
    chat: OrganizationRecruitingChat,
    actor: AbstractBaseUser,
    query: str,
) -> list[dict[str, Any]]:
    assert_can_manage_recruiting_invites(actor, chat)
    q = (query or "").strip().lstrip("@")
    if len(q) < CANDIDATE_QUERY_MIN:
        return []
    member_ids = set(
        ChatRoomMembership.objects.filter(room=chat.room).values_list(
            "user_id", flat=True
        )
    )
    pending_ids = set(
        ChatRoomInvitation.objects.filter(
            room=chat.room, status=ChatRoomInvitation.Status.PENDING
        ).values_list("invitee_id", flat=True)
    )
    declined_recent_ids = set(
        ChatRoomInvitation.objects.filter(
            room=chat.room,
            status=ChatRoomInvitation.Status.DECLINED,
            responded_at__gte=timezone.now() - DECLINE_COOLDOWN,
        ).values_list("invitee_id", flat=True)
    )
    excluded = member_ids | pending_ids | declined_recent_ids | {actor.pk}
    users = list(search_users(q, viewer=actor)[: CANDIDATE_RESULT_LIMIT * 3])
    results: list[dict[str, Any]] = []
    for user in users:
        if user.pk in excluded:
            continue
        if not can_view_private_content(actor, user):
            continue
        if is_either_blocked(actor, user):
            continue
        results.append(serialize_invitee_preview(user))
        if len(results) >= CANDIDATE_RESULT_LIMIT:
            break
    return results


def list_pending_recruiting_invites(
    *, chat: OrganizationRecruitingChat, actor: AbstractBaseUser
) -> list[dict[str, Any]]:
    assert_can_manage_recruiting_invites(actor, chat)
    rows = (
        ChatRoomInvitation.objects.filter(
            room=chat.room, status=ChatRoomInvitation.Status.PENDING
        )
        .select_related("invitee", "invitee__profile", "inviter", "inviter__profile")
        .order_by("-created_at", "-pk")
    )
    return [
        serialize_recruiting_invitation(row, include_invitee=True) for row in rows
    ]


def create_recruiting_invitations(
    *,
    chat: OrganizationRecruitingChat,
    actor: AbstractBaseUser,
    invitee_ids: list[int],
) -> dict[str, Any]:
    assert_can_send_recruiting_invites(actor, chat)
    raw_ids: list[int] = []
    seen: set[int] = set()
    for value in invitee_ids:
        try:
            pk = int(value)
        except (TypeError, ValueError):
            continue
        if pk in seen:
            continue
        seen.add(pk)
        raw_ids.append(pk)
    if not raw_ids:
        raise OrganizationRecruitingChatError("no_invitees")
    _assert_batch_size(len(raw_ids))

    invited: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    with transaction.atomic():
        locked = _lock_chat(chat.pk)
        assert_can_send_recruiting_invites(actor, locked)
        member_ids = set(
            ChatRoomMembership.objects.filter(room=locked.room).values_list(
                "user_id", flat=True
            )
        )
        pending_ids = set(
            ChatRoomInvitation.objects.filter(
                room=locked.room, status=ChatRoomInvitation.Status.PENDING
            ).values_list("invitee_id", flat=True)
        )
        existing_map = {
            row.invitee_id: row
            for row in ChatRoomInvitation.objects.select_for_update().filter(
                room=locked.room, invitee_id__in=raw_ids
            )
        }
        users = {
            user.pk: user
            for user in User.objects.filter(pk__in=raw_ids).select_related("profile")
        }
        planned: list[tuple[AbstractBaseUser, ChatRoomInvitation | None]] = []
        for pk in raw_ids:
            invitee = users.get(pk)
            existing = existing_map.get(pk)
            reason = _invitee_skip_reason(
                actor=actor,
                invitee=invitee,
                member_ids=member_ids,
                pending_ids=pending_ids,
                existing=existing,
            )
            if reason:
                skipped.append({"id": pk, "reason": reason})
                continue
            pending_ids.add(pk)
            planned.append((invitee, existing))
        _assert_invite_quota(
            inviter=actor, room=locked.room, additional=len(planned)
        )
        created_rows: list[ChatRoomInvitation] = []
        for invitee, existing in planned:
            if existing is not None:
                existing.status = ChatRoomInvitation.Status.PENDING
                existing.inviter = actor
                existing.responded_at = None
                existing.save(
                    update_fields=["status", "inviter", "responded_at", "updated_at"]
                )
                invitation = existing
            else:
                try:
                    # Savepoint: PostgreSQL aborts the whole transaction on
                    # IntegrityError unless the insert is wrapped.
                    with transaction.atomic():
                        invitation = ChatRoomInvitation.objects.create(
                            room=locked.room,
                            inviter=actor,
                            invitee=invitee,
                            status=ChatRoomInvitation.Status.PENDING,
                        )
                except IntegrityError:
                    skipped.append({"id": invitee.pk, "reason": SKIP_ALREADY_PENDING})
                    continue
                except OperationalError as exc:
                    if not _is_write_contention(exc):
                        raise
                    raise OrganizationRecruitingChatError("busy", status=503) from exc
            created_rows.append(invitation)
            invited.append(
                {
                    "id": invitation.pk,
                    "invitee": serialize_invitee_preview(invitee),
                }
            )
        if created_rows and (
            _recent_recruiting_invite_count(inviter=actor)
            > MAX_RECRUITING_INVITES_PER_HOUR
            or _recent_recruiting_invite_count(room=locked.room)
            > MAX_RECRUITING_INVITES_PER_ROOM_HOUR
        ):
            raise OrganizationRecruitingChatError("rate_limited", status=429)
        notify_rows = tuple(created_rows)
        _run_after_commit(lambda: _notify_created_invites(notify_rows))

    return {
        "invited_count": len(invited),
        "invited": invited,
        "skipped": skipped,
        "recruiting_chat": serialize_recruiting_chat_for_viewer(
            chat, actor, include_manager_fields=True
        ),
    }


def cancel_recruiting_invitation(
    *,
    chat: OrganizationRecruitingChat,
    actor: AbstractBaseUser,
    invitation_id: int,
) -> ChatRoomInvitation:
    assert_can_manage_recruiting_invites(actor, chat)
    with transaction.atomic():
        locked = _lock_chat(chat.pk)
        assert_can_manage_recruiting_invites(actor, locked)
        invitation = (
            ChatRoomInvitation.objects.select_for_update()
            .select_related("invitee", "room")
            .filter(
                pk=invitation_id,
                room=locked.room,
                room__kind=ChatRoom.Kind.RECRUITING,
            )
            .first()
        )
        if invitation is None:
            raise OrganizationRecruitingChatError("not_found", status=404)
        if invitation.status != ChatRoomInvitation.Status.PENDING:
            raise OrganizationRecruitingChatError("not_pending", status=409)
        invitation.status = ChatRoomInvitation.Status.CANCELLED
        invitation.responded_at = timezone.now()
        invitation.save(update_fields=["status", "responded_at", "updated_at"])
        invitee = invitation.invitee
        _run_after_commit(
            lambda: _resolve_recruiting_invite_notifications(
                invitee, locked, accepted=False, cancelled=True
            )
        )
    return invitation


def complete_recruiting_invite_acceptance(
    chat: OrganizationRecruitingChat,
    user: AbstractBaseUser,
    invitation: ChatRoomInvitation,
    *,
    reviewer: AbstractBaseUser | None,
) -> OrganizationRecruitingChatApplication:
    """Caller must hold the chat row lock. Does not send notifications."""
    if invitation.status != ChatRoomInvitation.Status.PENDING:
        raise OrganizationRecruitingChatError("not_pending", status=409)
    _ensure_membership(chat.room, user)
    application, _created = _get_or_lock_application(chat, user)
    _mark_application_approved(application, reviewer=reviewer)
    invitation.status = ChatRoomInvitation.Status.ACCEPTED
    invitation.responded_at = timezone.now()
    invitation.save(update_fields=["status", "responded_at", "updated_at"])
    return application


def accept_recruiting_invitation(
    *, invitation: ChatRoomInvitation, user: AbstractBaseUser
) -> dict[str, Any]:
    if not _authenticated_user(user):
        raise OrganizationRecruitingChatError("unauthorized", status=401)
    if invitation.invitee_id != user.pk:
        raise OrganizationRecruitingChatError("forbidden", status=403)
    if invitation.room.kind != ChatRoom.Kind.RECRUITING:
        raise OrganizationRecruitingChatError("not_found", status=404)
    chat = getattr(invitation.room, "organization_recruiting_chat", None)
    if chat is None:
        raise OrganizationRecruitingChatError("not_found", status=404)
    organization = chat.organization
    if not organization_allows_recruiting_access(organization):
        raise OrganizationRecruitingChatError("organization_suspended", status=403)
    if not chat.is_active:
        raise OrganizationRecruitingChatError("inactive", status=404)
    if not can_view_organization_profile(user, organization):
        raise OrganizationRecruitingChatError("organization_not_viewable", status=404)
    if is_either_blocked(user, invitation.inviter):
        raise OrganizationRecruitingChatError("blocked", status=403)

    with transaction.atomic():
        locked = _lock_chat(chat.pk)
        if not organization_allows_recruiting_access(locked.organization):
            raise OrganizationRecruitingChatError("organization_suspended", status=403)
        if not locked.is_active:
            raise OrganizationRecruitingChatError("inactive", status=404)
        row = (
            ChatRoomInvitation.objects.select_for_update()
            .filter(pk=invitation.pk, room=locked.room, invitee=user)
            .first()
        )
        if row is None:
            raise OrganizationRecruitingChatError("not_found", status=404)
        if ChatRoomMembership.objects.filter(room=locked.room, user=user).exists():
            if row.status == ChatRoomInvitation.Status.PENDING:
                complete_recruiting_invite_acceptance(
                    locked, user, row, reviewer=invitation.inviter
                )
                row.refresh_from_db()
                _run_after_commit(
                    lambda: _resolve_recruiting_invite_notifications(
                        user, chat, accepted=True
                    )
                )
            return {
                "recruiting_chat": serialize_recruiting_chat_for_viewer(
                    locked, user, include_manager_fields=False
                ),
                "invitation": serialize_recruiting_invitation(row),
            }
        if row.status != ChatRoomInvitation.Status.PENDING:
            raise OrganizationRecruitingChatError("not_pending", status=409)
        complete_recruiting_invite_acceptance(
            locked, user, row, reviewer=invitation.inviter
        )
        row.refresh_from_db()
        payload_chat = serialize_recruiting_chat_for_viewer(
            locked, user, include_manager_fields=False
        )
        _run_after_commit(
            lambda: _resolve_recruiting_invite_notifications(
                user, chat, accepted=True
            )
        )

    return {
        "recruiting_chat": payload_chat,
        "invitation": serialize_recruiting_invitation(row),
    }


def decline_recruiting_invitation(
    *, invitation: ChatRoomInvitation, user: AbstractBaseUser
) -> dict[str, Any]:
    if not _authenticated_user(user):
        raise OrganizationRecruitingChatError("unauthorized", status=401)
    if invitation.invitee_id != user.pk:
        raise OrganizationRecruitingChatError("forbidden", status=403)
    if invitation.room.kind != ChatRoom.Kind.RECRUITING:
        raise OrganizationRecruitingChatError("not_found", status=404)
    chat = getattr(invitation.room, "organization_recruiting_chat", None)
    if chat is None:
        raise OrganizationRecruitingChatError("not_found", status=404)

    with transaction.atomic():
        locked = _lock_chat(chat.pk)
        row = (
            ChatRoomInvitation.objects.select_for_update()
            .filter(pk=invitation.pk, room=locked.room, invitee=user)
            .first()
        )
        if row is None:
            raise OrganizationRecruitingChatError("not_found", status=404)
        if row.status != ChatRoomInvitation.Status.PENDING:
            raise OrganizationRecruitingChatError("not_pending", status=409)
        row.status = ChatRoomInvitation.Status.DECLINED
        row.responded_at = timezone.now()
        row.save(update_fields=["status", "responded_at", "updated_at"])
        _run_after_commit(
            lambda: _resolve_recruiting_invite_notifications(user, chat, accepted=False)
        )

    return {
        "ok": True,
        "invitation": serialize_recruiting_invitation(row),
        "recruiting_chat": serialize_recruiting_chat_for_viewer(
            chat, user, include_manager_fields=False
        ),
    }


def viewer_recruiting_invitation_payload(
    chat: OrganizationRecruitingChat | None, user: AbstractBaseUser | None
) -> dict[str, Any] | None:
    if chat is None or not _authenticated_user(user):
        return None
    row = (
        ChatRoomInvitation.objects.filter(room=chat.room, invitee=user)
        .select_related(
            "inviter",
            "inviter__profile",
            "room",
            "room__organization_recruiting_chat",
            "room__organization_recruiting_chat__organization",
        )
        .order_by("-updated_at", "-pk")
        .first()
    )
    if row is None:
        return None
    return serialize_recruiting_invitation(row)


def list_pending_recruiting_invitations_for_user(
    user: AbstractBaseUser,
) -> list[ChatRoomInvitation]:
    if not _authenticated_user(user):
        return []
    return list(
        ChatRoomInvitation.objects.filter(
            invitee=user,
            status=ChatRoomInvitation.Status.PENDING,
            room__kind=ChatRoom.Kind.RECRUITING,
        )
        .select_related(
            "room",
            "room__organization_recruiting_chat",
            "room__organization_recruiting_chat__organization",
            "inviter",
            "inviter__profile",
        )
        .order_by("-updated_at")
    )


def build_recruiting_invite_conversations(user: AbstractBaseUser) -> list[dict]:
    from .organization_api_services import get_organization_avatar_url

    conversations = []
    for invitation in list_pending_recruiting_invitations_for_user(user):
        chat = getattr(invitation.room, "organization_recruiting_chat", None)
        organization = getattr(chat, "organization", None) if chat is not None else None
        if organization is None:
            continue
        slug = organization.slug or ""
        conversations.append(
            {
                "kind": "recruiting_invite",
                "room": invitation.room,
                "invitation": invitation,
                "partner": None,
                "display_name": organization.name,
                "subtitle": f"{organization.name}から新歓チャットに招待されています",
                "status_label": "招待あり",
                "latest_message": None,
                "latest_sender_display_name": "",
                "unread_count": 1,
                "updated_at": invitation.updated_at or invitation.created_at,
                "thumbnail_url": get_organization_avatar_url(organization),
                "product": None,
                "is_blocked": False,
                "organization_id": organization.pk,
                "organization_slug": slug,
                "organization_name": organization.name,
                "organization_avatar_url": get_organization_avatar_url(organization),
                "member_count": 0,
                "viewer_role": "invited",
                "spa_path": recruiting_invite_spa_path(slug),
            }
        )
    return conversations


def _notify_created_invites(invitations: tuple[ChatRoomInvitation, ...]) -> None:
    for invitation in invitations:
        _notify_recruiting_invite(invitation)


def _notify_recruiting_invite(invitation: ChatRoomInvitation) -> None:
    chat = getattr(invitation.room, "organization_recruiting_chat", None)
    organization = getattr(chat, "organization", None) if chat is not None else None
    if organization is None:
        return
    if is_either_blocked(invitation.invitee, invitation.inviter):
        return
    slug = organization.slug or ""
    link = recruiting_invite_url(slug)
    if Notification.objects.filter(
        recipient=invitation.invitee, link=link, is_read=False
    ).exists():
        return
    org_name = organization.name
    create_notification(
        recipient=invitation.invitee,
        message=f"{org_name}から新歓チャットに招待されました",
        link=link,
        actor=invitation.inviter,
        push_kind=PUSH_KIND_RECRUITING_INVITE,
        push_body=f"「{org_name}から新歓チャットに招待されました」",
    )


def _resolve_recruiting_invite_notifications(
    invitee: AbstractBaseUser,
    chat: OrganizationRecruitingChat,
    *,
    accepted: bool,
    cancelled: bool = False,
) -> None:
    organization = chat.organization
    slug = getattr(organization, "slug", "") or ""
    org_name = getattr(organization, "name", "") or "団体"
    if cancelled:
        new_message = f"{org_name}からの新歓チャット招待は取り消されました"
    elif accepted:
        new_message = f"{org_name}の新歓チャットに参加しました"
    else:
        new_message = f"{org_name}からの新歓チャット招待を辞退しました"
    for note in Notification.objects.filter(recipient=invitee):
        if not _notification_link_matches_recruiting_invite(note.link or "", slug):
            continue
        if "新歓チャット" not in (note.message or "") and "招待" not in (
            note.message or ""
        ):
            continue
        note.message = new_message
        note.is_read = True
        note.save(update_fields=["message", "is_read"])


def _notification_link_matches_recruiting_invite(link: str, slug: str) -> bool:
    path = (link or "").split("?", 1)[0].rstrip("/")
    if path.endswith(f"/organizations/{slug}/recruiting-chat/invite"):
        return True
    if path.endswith(f"/orgs/{slug}/recruiting-chat/invite"):
        return True
    if path.endswith(f"/app/organizations/{slug}/recruiting-chat/invite"):
        return True
    return False
