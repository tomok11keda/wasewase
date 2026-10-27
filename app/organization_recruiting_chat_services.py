"""学生団体の新歓チャット：権限・参加・申請（Phase 3-A）。

HTTP API / React は Phase 3-B。ここはサービス層と既存チャット認可への接続点。

参加者は ChatRoomMembership のみ。OrganizationMember は作らない。
会話本体は ChatRoom(kind=recruiting) + ChatMessage + ChatReadState を再利用する。
kind=GROUP の招待 API には載せない。
"""

from __future__ import annotations

from typing import Any

from django.conf import settings
from django.contrib.auth.models import AbstractBaseUser
from django.db import IntegrityError, transaction
from django.db.models import Prefetch
from django.db.models.signals import post_delete
from django.dispatch import receiver
from django.utils import timezone

from .chat_message_services import (
    create_chat_message,
    serialize_chat_message,
    visible_chat_messages_qs,
)
from .models import (
    ChatMessage,
    ChatRoom,
    ChatRoomInvitation,
    ChatRoomMembership,
    Organization,
    OrganizationChatShare,
    OrganizationRecruitingChat,
    OrganizationRecruitingChatApplication,
)
from .organization_services import (
    can_list_organization,
    can_manage_organization,
    can_view_organization_profile,
)
from .timeline_api_services import serialize_author

NAME_MAX = 120
DESCRIPTION_MAX = 2000
DEFAULT_MAX_ACTIVE_ORGANIZATION_CHATS = 12


def max_active_organization_chats() -> int:
    raw = getattr(
        settings, "MAX_ACTIVE_ORGANIZATION_CHATS", DEFAULT_MAX_ACTIVE_ORGANIZATION_CHATS
    )
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = DEFAULT_MAX_ACTIVE_ORGANIZATION_CHATS
    return max(1, value)


class OrganizationRecruitingChatError(ValueError):
    def __init__(self, code: str, *, status: int = 400, message: str = "", **extra):
        self.code = code
        self.status = status
        self.extra = extra
        super().__init__(message or code)


def _authenticated_user(user: AbstractBaseUser | None) -> bool:
    return bool(
        user is not None
        and getattr(user, "pk", None)
        and getattr(user, "is_authenticated", False)
        and getattr(user, "is_active", True)
    )


def _normalize_name(name: str) -> str:
    value = (name or "").strip()
    if not value:
        raise OrganizationRecruitingChatError("empty_name")
    if len(value) > NAME_MAX:
        raise OrganizationRecruitingChatError("name_too_long")
    return value


def _normalize_description(description: str) -> str:
    value = (description or "").strip()
    if len(value) > DESCRIPTION_MAX:
        raise OrganizationRecruitingChatError("description_too_long")
    return value


def is_recruiting_room(room: ChatRoom | None) -> bool:
    return bool(room is not None and room.kind == ChatRoom.Kind.RECRUITING)


def get_recruiting_chat_for_room(
    room: ChatRoom | None,
) -> OrganizationRecruitingChat | None:
    if not is_recruiting_room(room):
        return None
    return (
        OrganizationRecruitingChat.objects.select_related("organization", "room")
        .filter(room=room)
        .first()
    )


def get_active_recruiting_chat(
    organization: Organization | None,
) -> OrganizationRecruitingChat | None:
    """互換用。複数ある場合は最も古い有効チャット。"""
    chats = list_active_recruiting_chats(organization)
    return chats[0] if chats else None


def list_active_recruiting_chats(
    organization: Organization | None,
) -> list[OrganizationRecruitingChat]:
    if organization is None or not getattr(organization, "pk", None):
        return []
    return list(
        OrganizationRecruitingChat.objects.select_related("organization", "room")
        .filter(organization=organization, is_active=True)
        .order_by("pk")
    )


def get_organization_chat(
    organization: Organization | None,
    chat_id: int | None,
) -> OrganizationRecruitingChat | None:
    if organization is None or not getattr(organization, "pk", None) or not chat_id:
        return None
    return (
        OrganizationRecruitingChat.objects.select_related("organization", "room")
        .filter(organization=organization, pk=chat_id)
        .first()
    )


def count_active_organization_chats(organization: Organization | None) -> int:
    if organization is None or not getattr(organization, "pk", None):
        return 0
    return OrganizationRecruitingChat.objects.filter(
        organization=organization, is_active=True
    ).count()


def is_recruiting_participant(
    room: ChatRoom | None, user: AbstractBaseUser | None
) -> bool:
    """ChatRoomMembership があるか。団体 owner/admin だけでは True にしない。"""
    if not is_recruiting_room(room) or not _authenticated_user(user):
        return False
    return ChatRoomMembership.objects.filter(room=room, user=user).exists()


def organization_allows_recruiting_access(
    organization: Organization | None,
) -> bool:
    """suspended では会話・参加・管理を止める。listing_status=closed はここでは見ない。"""
    if organization is None or not getattr(organization, "pk", None):
        return False
    return organization.status != Organization.Status.SUSPENDED


def can_access_recruiting_room(
    room: ChatRoom | None, user: AbstractBaseUser | None
) -> bool:
    """メッセージ閲覧・送信・既読は参加者のみ。団体管理者でも未参加なら拒否。"""
    if not is_recruiting_room(room) or not _authenticated_user(user):
        return False
    chat = get_recruiting_chat_for_room(room)
    if chat is None:
        return False
    organization = _organization_for_chat(chat)
    if not organization_allows_recruiting_access(organization):
        return False
    return is_recruiting_participant(room, user)


def assert_can_send_recruiting_message(
    room: ChatRoom, sender: AbstractBaseUser
) -> None:
    if not can_access_recruiting_room(room, sender):
        raise OrganizationRecruitingChatError("forbidden", status=403)
    chat = get_recruiting_chat_for_room(room)
    if chat is None:
        raise OrganizationRecruitingChatError("not_found", status=404)
    if not chat.is_active:
        raise OrganizationRecruitingChatError("inactive", status=403)
    if chat.posting_mode == OrganizationRecruitingChat.PostingMode.ADMINS:
        organization = _organization_for_chat(chat)
        if not can_manage_organization(sender, organization):
            raise OrganizationRecruitingChatError("admins_only", status=403)


def recruiting_chat_message_is_reportable_by(
    viewer: AbstractBaseUser | None, message: ChatMessage | None
) -> bool:
    """新歓メッセージの通報は参加者／団体管理者のみ。他 kind は従来どおり。"""
    if message is None:
        return False
    room = getattr(message, "room", None)
    if room is None and getattr(message, "room_id", None):
        room = ChatRoom.objects.filter(pk=message.room_id).first()
    if room is None or room.kind != ChatRoom.Kind.RECRUITING:
        return True
    return can_access_recruiting_room(room, viewer)


def assert_can_manage_recruiting_chat(
    actor: AbstractBaseUser | None, chat: OrganizationRecruitingChat | None
) -> OrganizationRecruitingChat:
    if chat is None or not getattr(chat, "pk", None):
        raise OrganizationRecruitingChatError("not_found", status=404)
    organization = _organization_for_chat(chat)
    if not can_manage_organization(actor, organization):
        raise OrganizationRecruitingChatError("forbidden", status=403)
    return chat


def organization_accepts_recruiting_join(organization: Organization | None) -> bool:
    return organization_allows_recruiting_access(organization)


def _organization_for_chat(
    chat: OrganizationRecruitingChat | None,
) -> Organization | None:
    if chat is None or not chat.organization_id:
        return None
    return Organization.objects.filter(pk=chat.organization_id).first()


def can_discover_recruiting_chat(
    viewer: AbstractBaseUser | None, chat: OrganizationRecruitingChat | None
) -> bool:
    """団体プロフィール上での発見。公開かつ募集中のときだけ。非公開は出さない。"""
    if chat is None or not chat.is_active:
        return False
    if chat.visibility != OrganizationRecruitingChat.Visibility.PUBLIC:
        return False
    if chat.listing_status != OrganizationRecruitingChat.ListingStatus.OPEN:
        return False
    organization = _organization_for_chat(chat)
    if organization is None:
        return False
    if not organization_accepts_recruiting_join(organization):
        return False
    return can_view_organization_profile(viewer, organization)


def can_list_recruiting_chat_publicly(
    chat: OrganizationRecruitingChat | None,
) -> bool:
    """検索・一覧カード。公開・募集中かつ団体自体が listed。"""
    if chat is None or not chat.is_active:
        return False
    if chat.visibility != OrganizationRecruitingChat.Visibility.PUBLIC:
        return False
    if chat.listing_status != OrganizationRecruitingChat.ListingStatus.OPEN:
        return False
    return can_list_organization(_organization_for_chat(chat))


def can_see_recruiting_chat(
    viewer: AbstractBaseUser | None, chat: OrganizationRecruitingChat | None
) -> bool:
    """存在を知ってよい相手。非公開は管理者・参加者・招待先のみ。"""
    if chat is None:
        return False
    organization = _organization_for_chat(chat)
    if can_manage_organization(viewer, organization):
        return True
    if is_recruiting_participant(chat.room, viewer):
        return True
    if viewer_has_pending_recruiting_invitation(chat, viewer):
        return True
    if can_discover_recruiting_chat(viewer, chat):
        return True
    if (
        chat.is_active
        and chat.visibility == OrganizationRecruitingChat.Visibility.PUBLIC
        and can_view_organization_profile(viewer, organization)
    ):
        return True
    return False


def _lock_chat(chat_id: int) -> OrganizationRecruitingChat:
    return (
        OrganizationRecruitingChat.objects.select_for_update()
        .select_related("organization", "room")
        .get(pk=chat_id)
    )


def _ensure_membership(room: ChatRoom, user: AbstractBaseUser) -> ChatRoomMembership:
    membership, _created = ChatRoomMembership.objects.get_or_create(
        room=room,
        user=user,
        defaults={"role": ChatRoomMembership.Role.MEMBER},
    )
    return membership


def _get_or_lock_application(
    chat: OrganizationRecruitingChat, user: AbstractBaseUser
) -> tuple[OrganizationRecruitingChatApplication, bool]:
    existing = (
        OrganizationRecruitingChatApplication.objects.select_for_update()
        .filter(recruiting_chat=chat, user=user)
        .first()
    )
    if existing is not None:
        return existing, False
    try:
        application = OrganizationRecruitingChatApplication.objects.create(
            recruiting_chat=chat,
            user=user,
            status=OrganizationRecruitingChatApplication.Status.PENDING,
        )
        return (
            OrganizationRecruitingChatApplication.objects.select_for_update().get(
                pk=application.pk
            ),
            True,
        )
    except IntegrityError:
        return (
            OrganizationRecruitingChatApplication.objects.select_for_update().get(
                recruiting_chat=chat, user=user
            ),
            False,
        )


def _mark_application_approved(
    application: OrganizationRecruitingChatApplication,
    *,
    reviewer: AbstractBaseUser | None,
) -> None:
    application.status = OrganizationRecruitingChatApplication.Status.APPROVED
    application.reviewed_at = timezone.now()
    application.reviewed_by = reviewer
    application.save(update_fields=["status", "reviewed_at", "reviewed_by", "updated_at"])


def count_pending_applications(chat: OrganizationRecruitingChat | None) -> int:
    if chat is None or not getattr(chat, "pk", None):
        return 0
    return OrganizationRecruitingChatApplication.objects.filter(
        recruiting_chat=chat,
        status=OrganizationRecruitingChatApplication.Status.PENDING,
    ).count()


def preview_join_mode_change(
    chat: OrganizationRecruitingChat,
) -> dict[str, Any]:
    pending_count = count_pending_applications(chat)
    would_auto_approve = (
        chat.join_mode == OrganizationRecruitingChat.JoinMode.APPROVAL
        and pending_count > 0
    )
    return {
        "pending_count": pending_count,
        "would_auto_approve_on_open": would_auto_approve,
        "current_join_mode": chat.join_mode,
    }


def _approve_pending_applications(
    chat: OrganizationRecruitingChat, reviewer: AbstractBaseUser
) -> int:
    pending = list(
        OrganizationRecruitingChatApplication.objects.select_for_update().filter(
            recruiting_chat=chat,
            status=OrganizationRecruitingChatApplication.Status.PENDING,
        )
    )
    for application in pending:
        _ensure_membership(chat.room, application.user)
        _mark_application_approved(application, reviewer=reviewer)
        _mark_pending_invite_accepted(chat.room, application.user)
        from .organization_recruiting_invite_services import (
            _resolve_recruiting_invite_notifications,
            _run_after_commit,
        )

        invitee = application.user
        _run_after_commit(
            lambda invitee=invitee: _resolve_recruiting_invite_notifications(
                invitee, chat, accepted=True
            )
        )
    return len(pending)


def _normalize_visibility(visibility: str) -> str:
    if visibility not in OrganizationRecruitingChat.Visibility.values:
        raise OrganizationRecruitingChatError("invalid_visibility")
    return visibility


def _normalize_posting_mode(posting_mode: str) -> str:
    if posting_mode not in OrganizationRecruitingChat.PostingMode.values:
        raise OrganizationRecruitingChatError("invalid_posting_mode")
    return posting_mode


def _apply_visibility_join_rules(
    *,
    join_mode: str,
    visibility: str,
    listing_status: str,
) -> tuple[str, str, str]:
    if visibility == OrganizationRecruitingChat.Visibility.PRIVATE:
        join_mode = OrganizationRecruitingChat.JoinMode.INVITE
        listing_status = OrganizationRecruitingChat.ListingStatus.CLOSED
    elif join_mode == OrganizationRecruitingChat.JoinMode.INVITE:
        visibility = OrganizationRecruitingChat.Visibility.PRIVATE
        listing_status = OrganizationRecruitingChat.ListingStatus.CLOSED
    return join_mode, visibility, listing_status


def create_recruiting_chat(
    *,
    organization: Organization,
    actor: AbstractBaseUser,
    name: str,
    description: str = "",
    join_mode: str = OrganizationRecruitingChat.JoinMode.OPEN,
    listing_status: str = OrganizationRecruitingChat.ListingStatus.OPEN,
    visibility: str = OrganizationRecruitingChat.Visibility.PUBLIC,
    posting_mode: str = OrganizationRecruitingChat.PostingMode.ALL,
) -> OrganizationRecruitingChat:
    if not can_manage_organization(actor, organization):
        raise OrganizationRecruitingChatError("forbidden", status=403)
    name = _normalize_name(name)
    description = _normalize_description(description)
    if join_mode not in OrganizationRecruitingChat.JoinMode.values:
        raise OrganizationRecruitingChatError("invalid_join_mode")
    if listing_status not in OrganizationRecruitingChat.ListingStatus.values:
        raise OrganizationRecruitingChatError("invalid_listing_status")
    visibility = _normalize_visibility(visibility)
    posting_mode = _normalize_posting_mode(posting_mode)
    join_mode, visibility, listing_status = _apply_visibility_join_rules(
        join_mode=join_mode,
        visibility=visibility,
        listing_status=listing_status,
    )

    with transaction.atomic():
        locked_org = Organization.objects.select_for_update().get(pk=organization.pk)
        if not can_manage_organization(actor, locked_org):
            raise OrganizationRecruitingChatError("forbidden", status=403)
        active_count = OrganizationRecruitingChat.objects.filter(
            organization=locked_org, is_active=True
        ).count()
        limit = max_active_organization_chats()
        if active_count >= limit:
            raise OrganizationRecruitingChatError(
                "chat_limit_reached",
                status=409,
                chat_max=limit,
                chat_count=active_count,
            )
        room = ChatRoom.objects.create(
            kind=ChatRoom.Kind.RECRUITING,
            name=name,
            created_by=actor,
        )
        chat = OrganizationRecruitingChat.objects.create(
            organization=locked_org,
            room=room,
            name=name,
            description=description,
            join_mode=join_mode,
            listing_status=listing_status,
            visibility=visibility,
            posting_mode=posting_mode,
            is_active=True,
            created_by=actor,
        )
        _ensure_membership(room, actor)
    return (
        OrganizationRecruitingChat.objects.select_related("organization", "room")
        .get(pk=chat.pk)
    )


def update_recruiting_chat_settings(
    *,
    chat: OrganizationRecruitingChat,
    actor: AbstractBaseUser,
    name: str | None = None,
    description: str | None = None,
    join_mode: str | None = None,
    listing_status: str | None = None,
    visibility: str | None = None,
    posting_mode: str | None = None,
    confirm_auto_approve: bool = False,
) -> tuple[OrganizationRecruitingChat, dict[str, Any]]:
    assert_can_manage_recruiting_chat(actor, chat)
    with transaction.atomic():
        locked = _lock_chat(chat.pk)
        assert_can_manage_recruiting_chat(actor, locked)
        update_fields = ["updated_at"]
        previous_mode = locked.join_mode
        previous_visibility = locked.visibility
        pending_before = count_pending_applications(locked)
        next_join = join_mode if join_mode is not None else locked.join_mode
        next_visibility = (
            visibility if visibility is not None else locked.visibility
        )
        next_listing = (
            listing_status if listing_status is not None else locked.listing_status
        )
        if join_mode is not None and next_join not in OrganizationRecruitingChat.JoinMode.values:
            raise OrganizationRecruitingChatError("invalid_join_mode")
        if visibility is not None:
            next_visibility = _normalize_visibility(next_visibility)
        if listing_status is not None and next_listing not in OrganizationRecruitingChat.ListingStatus.values:
            raise OrganizationRecruitingChatError("invalid_listing_status")
        next_join, next_visibility, next_listing = _apply_visibility_join_rules(
            join_mode=next_join,
            visibility=next_visibility,
            listing_status=next_listing,
        )
        switching_to_open = (
            previous_mode != OrganizationRecruitingChat.JoinMode.OPEN
            and next_join == OrganizationRecruitingChat.JoinMode.OPEN
        )
        if switching_to_open and pending_before > 0 and not confirm_auto_approve:
            raise OrganizationRecruitingChatError(
                "confirm_auto_approve_required",
                status=409,
                pending_count=pending_before,
                would_auto_approve=True,
            )
        if locked.join_mode != next_join:
            locked.join_mode = next_join
            update_fields.append("join_mode")
        if locked.visibility != next_visibility:
            locked.visibility = next_visibility
            update_fields.append("visibility")
        if locked.listing_status != next_listing:
            locked.listing_status = next_listing
            update_fields.append("listing_status")
        if name is not None:
            locked.name = _normalize_name(name)
            locked.room.name = locked.name
            locked.room.save(update_fields=["name", "updated_at"])
            update_fields.append("name")
        if description is not None:
            locked.description = _normalize_description(description)
            update_fields.append("description")
        if posting_mode is not None:
            locked.posting_mode = _normalize_posting_mode(posting_mode)
            update_fields.append("posting_mode")
        locked.save(update_fields=update_fields)
        switched_to_open = (
            previous_mode != OrganizationRecruitingChat.JoinMode.OPEN
            and locked.join_mode == OrganizationRecruitingChat.JoinMode.OPEN
        )
        auto_approved_count = 0
        if switched_to_open:
            auto_approved_count = _approve_pending_applications(locked, actor)
        became_public = (
            previous_visibility != OrganizationRecruitingChat.Visibility.PUBLIC
            and locked.visibility == OrganizationRecruitingChat.Visibility.PUBLIC
        )
    refreshed = (
        OrganizationRecruitingChat.objects.select_related("organization", "room")
        .get(pk=locked.pk)
    )
    return refreshed, {
        "pending_count_before": pending_before,
        "would_auto_approve": switched_to_open and pending_before > 0,
        "auto_approved_count": auto_approved_count,
        "became_public": became_public,
    }


def deactivate_recruiting_chat(
    *, chat: OrganizationRecruitingChat, actor: AbstractBaseUser
) -> OrganizationRecruitingChat:
    """有効フラグを外し、翌年度の新規チャットを作れるようにする。既存参加者は残す。"""
    assert_can_manage_recruiting_chat(actor, chat)
    with transaction.atomic():
        locked = _lock_chat(chat.pk)
        assert_can_manage_recruiting_chat(actor, locked)
        locked.is_active = False
        locked.listing_status = OrganizationRecruitingChat.ListingStatus.CLOSED
        locked.save(update_fields=["is_active", "listing_status", "updated_at"])
    return locked


def _assert_can_join_or_apply(
    chat: OrganizationRecruitingChat, user: AbstractBaseUser
) -> None:
    if not _authenticated_user(user):
        raise OrganizationRecruitingChatError("forbidden", status=403)
    organization = chat.organization
    if not organization_accepts_recruiting_join(organization):
        raise OrganizationRecruitingChatError("organization_suspended", status=403)
    if not chat.is_active:
        raise OrganizationRecruitingChatError("inactive", status=404)
    if can_manage_organization(user, organization):
        return
    invited = viewer_has_pending_recruiting_invitation(chat, user)
    if invited:
        return
    if chat.visibility != OrganizationRecruitingChat.Visibility.PUBLIC:
        raise OrganizationRecruitingChatError("not_found", status=404)
    if not can_view_organization_profile(user, organization):
        raise OrganizationRecruitingChatError("organization_not_viewable", status=404)
    if chat.listing_status != OrganizationRecruitingChat.ListingStatus.OPEN:
        raise OrganizationRecruitingChatError("listing_closed", status=403)
    if chat.join_mode == OrganizationRecruitingChat.JoinMode.INVITE:
        raise OrganizationRecruitingChatError("invite_only", status=403)


def _mark_pending_invite_accepted(room: ChatRoom, user: AbstractBaseUser) -> None:
    ChatRoomInvitation.objects.filter(
        room=room,
        invitee=user,
        status=ChatRoomInvitation.Status.PENDING,
    ).update(status=ChatRoomInvitation.Status.ACCEPTED, responded_at=timezone.now())


def join_or_apply_recruiting_chat(
    *,
    chat: OrganizationRecruitingChat,
    user: AbstractBaseUser,
) -> OrganizationRecruitingChatApplication:
    """自由参加なら即メンバー化。承認制なら pending 申請。Membership 以外は作らない。"""
    with transaction.atomic():
        locked = _lock_chat(chat.pk)
        _assert_can_join_or_apply(locked, user)
        pending_invite = (
            ChatRoomInvitation.objects.select_for_update()
            .filter(
                room=locked.room,
                invitee=user,
                status=ChatRoomInvitation.Status.PENDING,
            )
            .first()
        )
        if pending_invite is not None:
            from .organization_recruiting_invite_services import (
                _resolve_recruiting_invite_notifications,
                _run_after_commit,
                complete_recruiting_invite_acceptance,
            )

            application = complete_recruiting_invite_acceptance(
                locked, user, pending_invite, reviewer=pending_invite.inviter
            )
            _run_after_commit(
                lambda: _resolve_recruiting_invite_notifications(
                    user, chat, accepted=True
                )
            )
        elif ChatRoomMembership.objects.filter(room=locked.room, user=user).exists():
            raise OrganizationRecruitingChatError("already_member", status=409)
        elif can_manage_organization(user, locked.organization):
            application, _created = _get_or_lock_application(locked, user)
            _ensure_membership(locked.room, user)
            _mark_application_approved(application, reviewer=user)
        elif locked.join_mode == OrganizationRecruitingChat.JoinMode.INVITE:
            raise OrganizationRecruitingChatError("invite_only", status=403)
        else:
            application, created = _get_or_lock_application(locked, user)
            if locked.join_mode == OrganizationRecruitingChat.JoinMode.OPEN:
                _ensure_membership(locked.room, user)
                _mark_application_approved(application, reviewer=None)
            elif (
                not created
                and application.status
                == OrganizationRecruitingChatApplication.Status.PENDING
            ):
                raise OrganizationRecruitingChatError("already_pending", status=409)
            elif not created:
                application.status = OrganizationRecruitingChatApplication.Status.PENDING
                application.reviewed_at = None
                application.reviewed_by = None
                application.save(
                    update_fields=["status", "reviewed_at", "reviewed_by", "updated_at"]
                )
    return application


def approve_recruiting_application(
    *,
    chat: OrganizationRecruitingChat,
    application_id: int,
    actor: AbstractBaseUser,
) -> OrganizationRecruitingChatApplication:
    assert_can_manage_recruiting_chat(actor, chat)
    with transaction.atomic():
        locked = _lock_chat(chat.pk)
        assert_can_manage_recruiting_chat(actor, locked)
        try:
            application = (
                OrganizationRecruitingChatApplication.objects.select_for_update()
                .select_related("user")
                .get(pk=application_id, recruiting_chat=locked)
            )
        except OrganizationRecruitingChatApplication.DoesNotExist as exc:
            raise OrganizationRecruitingChatError("not_found", status=404) from exc
        if application.status != OrganizationRecruitingChatApplication.Status.PENDING:
            raise OrganizationRecruitingChatError("not_pending")
        _ensure_membership(locked.room, application.user)
        _mark_application_approved(application, reviewer=actor)
        _mark_pending_invite_accepted(locked.room, application.user)
        from .organization_recruiting_invite_services import (
            _resolve_recruiting_invite_notifications,
            _run_after_commit,
        )

        invitee = application.user
        _run_after_commit(
            lambda: _resolve_recruiting_invite_notifications(
                invitee, locked, accepted=True
            )
        )
        return application


def reject_recruiting_application(
    *,
    chat: OrganizationRecruitingChat,
    application_id: int,
    actor: AbstractBaseUser,
) -> OrganizationRecruitingChatApplication:
    assert_can_manage_recruiting_chat(actor, chat)
    with transaction.atomic():
        locked = _lock_chat(chat.pk)
        assert_can_manage_recruiting_chat(actor, locked)
        try:
            application = (
                OrganizationRecruitingChatApplication.objects.select_for_update()
                .select_related("user")
                .get(pk=application_id, recruiting_chat=locked)
            )
        except OrganizationRecruitingChatApplication.DoesNotExist as exc:
            raise OrganizationRecruitingChatError("not_found", status=404) from exc
        if application.status != OrganizationRecruitingChatApplication.Status.PENDING:
            raise OrganizationRecruitingChatError("not_pending")
        application.status = OrganizationRecruitingChatApplication.Status.REJECTED
        application.reviewed_at = timezone.now()
        application.reviewed_by = actor
        application.save(
            update_fields=["status", "reviewed_at", "reviewed_by", "updated_at"]
        )
        ChatRoomMembership.objects.filter(
            room=locked.room, user_id=application.user_id
        ).delete()
        return application


def withdraw_recruiting_application(
    *, chat: OrganizationRecruitingChat, user: AbstractBaseUser
) -> OrganizationRecruitingChatApplication:
    if not _authenticated_user(user):
        raise OrganizationRecruitingChatError("forbidden", status=403)
    with transaction.atomic():
        locked = _lock_chat(chat.pk)
        if ChatRoomMembership.objects.filter(room=locked.room, user=user).exists():
            raise OrganizationRecruitingChatError("already_member", status=409)
        application = (
            OrganizationRecruitingChatApplication.objects.select_for_update()
            .filter(recruiting_chat=locked, user=user)
            .first()
        )
        if (
            application is None
            or application.status
            != OrganizationRecruitingChatApplication.Status.PENDING
        ):
            raise OrganizationRecruitingChatError("not_pending", status=409)
        application.status = OrganizationRecruitingChatApplication.Status.WITHDRAWN
        application.reviewed_at = timezone.now()
        application.reviewed_by = None
        application.save(
            update_fields=["status", "reviewed_at", "reviewed_by", "updated_at"]
        )
        return application


def leave_recruiting_chat(
    *, chat: OrganizationRecruitingChat, user: AbstractBaseUser
) -> None:
    if not _authenticated_user(user):
        raise OrganizationRecruitingChatError("forbidden", status=403)
    with transaction.atomic():
        locked = _lock_chat(chat.pk)
        deleted, _ = ChatRoomMembership.objects.filter(
            room=locked.room, user=user
        ).delete()
        if not deleted:
            raise OrganizationRecruitingChatError("not_member", status=403)
        application = (
            OrganizationRecruitingChatApplication.objects.select_for_update()
            .filter(recruiting_chat=locked, user=user)
            .first()
        )
        if application is not None:
            application.status = OrganizationRecruitingChatApplication.Status.WITHDRAWN
            application.reviewed_at = timezone.now()
            application.reviewed_by = None
            application.save(
                update_fields=["status", "reviewed_at", "reviewed_by", "updated_at"]
            )


def remove_recruiting_participant(
    *,
    chat: OrganizationRecruitingChat,
    actor: AbstractBaseUser,
    user_id: int,
) -> None:
    assert_can_manage_recruiting_chat(actor, chat)
    with transaction.atomic():
        locked = _lock_chat(chat.pk)
        assert_can_manage_recruiting_chat(actor, locked)
        deleted, _ = ChatRoomMembership.objects.filter(
            room=locked.room, user_id=user_id
        ).delete()
        if not deleted:
            raise OrganizationRecruitingChatError("not_member", status=404)
        application = (
            OrganizationRecruitingChatApplication.objects.select_for_update()
            .filter(recruiting_chat=locked, user_id=user_id)
            .first()
        )
        if application is not None:
            application.status = OrganizationRecruitingChatApplication.Status.WITHDRAWN
            application.reviewed_at = timezone.now()
            application.reviewed_by = actor
            application.save(
                update_fields=["status", "reviewed_at", "reviewed_by", "updated_at"]
            )


def send_recruiting_chat_message(
    room: ChatRoom,
    sender: AbstractBaseUser,
    body: str,
    *,
    reply_to_id: int | None = None,
) -> ChatMessage:
    if not is_recruiting_room(room):
        raise OrganizationRecruitingChatError("not_found", status=404)
    assert_can_send_recruiting_message(room, sender)
    return create_chat_message(room, sender, body, reply_to_id=reply_to_id)


def list_recruiting_messages(room: ChatRoom, viewer: AbstractBaseUser):
    if not can_access_recruiting_room(room, viewer):
        raise OrganizationRecruitingChatError("forbidden", status=403)
    return visible_chat_messages_qs(room)


def list_recruiting_rooms_for_user(user: AbstractBaseUser):
    """チャット一覧接続点。参加者のみ。pending と未参加の管理者は含めない。"""
    if not _authenticated_user(user):
        return ChatRoom.objects.none()
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
        ChatRoom.objects.filter(kind=ChatRoom.Kind.RECRUITING)
        .filter(memberships__user_id=user.pk)
        .exclude(
            organization_recruiting_chat__organization__status=Organization.Status.SUSPENDED
        )
        .select_related(
            "organization_recruiting_chat",
            "organization_recruiting_chat__organization",
        )
        .prefetch_related(latest_message, member_count)
        .distinct()
        .order_by("-updated_at")
    )


def viewer_application_status(
    chat: OrganizationRecruitingChat, user: AbstractBaseUser | None
) -> str:
    if is_recruiting_participant(chat.room, user):
        return "member"
    if not _authenticated_user(user):
        return "none"
    status = (
        OrganizationRecruitingChatApplication.objects.filter(
            recruiting_chat=chat, user=user
        )
        .values_list("status", flat=True)
        .first()
    )
    return status or "none"


def viewer_has_pending_recruiting_invitation(
    chat: OrganizationRecruitingChat, user: AbstractBaseUser | None
) -> bool:
    if not _authenticated_user(user):
        return False
    return ChatRoomInvitation.objects.filter(
        room=chat.room,
        invitee=user,
        status=ChatRoomInvitation.Status.PENDING,
    ).exists()


def public_membership_status(
    chat: OrganizationRecruitingChat, user: AbstractBaseUser | None
) -> str:
    """フロント判別用: not_joined / pending / invited / joined / rejected / closed。"""
    state = viewer_application_status(chat, user)
    if state == "member":
        return "joined"
    if viewer_has_pending_recruiting_invitation(chat, user):
        return "invited"
    if state == "pending":
        return "pending"
    if state == "rejected":
        return "rejected"
    if (
        not chat.is_active
        or chat.listing_status != OrganizationRecruitingChat.ListingStatus.OPEN
    ):
        return "closed"
    return "not_joined"


def list_recruiting_applications(
    *, chat: OrganizationRecruitingChat, actor: AbstractBaseUser
) -> list[dict[str, Any]]:
    assert_can_manage_recruiting_chat(actor, chat)
    rows = (
        OrganizationRecruitingChatApplication.objects.filter(recruiting_chat=chat)
        .select_related("user", "user__profile")
        .order_by("created_at", "pk")
    )
    return [serialize_recruiting_application(row) for row in rows]


def list_recruiting_participants(
    *,
    chat: OrganizationRecruitingChat,
    viewer: AbstractBaseUser,
) -> list[dict[str, Any]]:
    organization = _organization_for_chat(chat)
    if not (
        can_access_recruiting_room(chat.room, viewer)
        or can_manage_organization(viewer, organization)
    ):
        raise OrganizationRecruitingChatError("forbidden", status=403)
    memberships = (
        ChatRoomMembership.objects.filter(room=chat.room)
        .select_related("user", "user__profile")
        .order_by("joined_at", "pk")
    )
    return [
        serialize_recruiting_participant(membership) for membership in memberships
    ]


def serialize_recruiting_participant(membership: ChatRoomMembership) -> dict[str, Any]:
    """メールアドレスは出さない。非公開プロフィールの投稿・時間割も出さない。"""
    author = serialize_author(membership.user) or {}
    return {
        "user_id": membership.user_id,
        "username": author.get("username", ""),
        "display_name": author.get("display_name", ""),
        "avatar_url": author.get("avatar_url", ""),
        "joined_at": membership.joined_at.isoformat(),
        "role": membership.role,
    }


def serialize_recruiting_application(
    application: OrganizationRecruitingChatApplication,
) -> dict[str, Any]:
    """管理者向け。メールアドレスは出さない。"""
    author = serialize_author(application.user) or {}
    return {
        "id": application.pk,
        "user_id": application.user_id,
        "username": author.get("username", ""),
        "display_name": author.get("display_name", ""),
        "avatar_url": author.get("avatar_url", ""),
        "status": application.status,
        "created_at": application.created_at.isoformat(),
        "reviewed_at": (
            application.reviewed_at.isoformat() if application.reviewed_at else None
        ),
    }


def serialize_recruiting_chat_for_viewer(
    chat: OrganizationRecruitingChat,
    viewer: AbstractBaseUser | None,
    *,
    include_manager_fields: bool | None = None,
) -> dict[str, Any]:
    """発見・状態確認用。申請一覧やメールは含めない。"""
    member_count = ChatRoomMembership.objects.filter(room=chat.room).count()
    state = viewer_application_status(chat, viewer)
    membership_status = public_membership_status(chat, viewer)
    organization = _organization_for_chat(chat)
    discoverable = can_discover_recruiting_chat(viewer, chat)
    can_manage = can_manage_organization(viewer, organization)
    can_access = can_access_recruiting_room(chat.room, viewer)
    authenticated = _authenticated_user(viewer)
    invited = membership_status == "invited"
    can_invite = bool(
        can_manage
        and chat.is_active
        and organization_allows_recruiting_access(organization)
    )
    visible_meta = discoverable or can_manage or can_access or invited
    can_send = bool(
        can_access
        and chat.is_active
        and (
            chat.posting_mode != OrganizationRecruitingChat.PostingMode.ADMINS
            or can_manage
        )
    )
    payload: dict[str, Any] = {
        "id": chat.pk,
        "organization_id": chat.organization_id,
        "name": chat.name if visible_meta else "",
        "description": chat.description if (discoverable or can_manage or can_access) else "",
        "join_mode": chat.join_mode,
        "listing_status": chat.listing_status,
        "visibility": chat.visibility,
        "posting_mode": chat.posting_mode,
        "is_active": chat.is_active,
        "member_count": member_count if (discoverable or can_manage or can_access) else 0,
        "viewer_state": state,
        "membership_status": membership_status,
        "can_manage": can_manage,
        "can_discover": discoverable,
        "can_list_publicly": can_list_recruiting_chat_publicly(chat),
        "can_join": bool(
            authenticated
            and state != "member"
            and not invited
            and (
                can_manage
                or (
                    discoverable
                    and chat.join_mode == OrganizationRecruitingChat.JoinMode.OPEN
                )
            )
        ),
        "can_apply": bool(
            authenticated
            and discoverable
            and chat.join_mode == OrganizationRecruitingChat.JoinMode.APPROVAL
            and state not in {"member", "pending"}
            and not invited
        ),
        "can_leave": bool(state == "member"),
        "can_withdraw": bool(state == "pending" and not invited),
        "can_send": can_send,
        "can_invite": can_invite,
        "can_pin": bool(can_manage and can_access),
        "pinned_message_id": chat.pinned_message_id if can_access else None,
    }
    if can_access:
        payload["room_id"] = chat.room_id
    else:
        payload["room_id"] = None
    if include_manager_fields is None:
        include_manager_fields = can_manage
    if include_manager_fields:
        preview = preview_join_mode_change(chat)
        payload["pending_count"] = preview["pending_count"]
        payload["would_auto_approve_on_open"] = preview["would_auto_approve_on_open"]
    if invited and _authenticated_user(viewer):
        pending_invite = (
            ChatRoomInvitation.objects.filter(
                room=chat.room,
                invitee=viewer,
                status=ChatRoomInvitation.Status.PENDING,
            )
            .select_related(
                "inviter",
                "inviter__profile",
                "room",
                "room__organization_recruiting_chat",
                "room__organization_recruiting_chat__organization",
            )
            .first()
        )
        if pending_invite is not None:
            from .organization_recruiting_invite_services import (
                serialize_recruiting_invitation,
            )

            payload["invitation"] = serialize_recruiting_invitation(pending_invite)
    return payload


def _chat_summary_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": payload["id"],
        "name": payload["name"],
        "join_mode": payload["join_mode"],
        "listing_status": payload["listing_status"],
        "visibility": payload.get("visibility") or "public",
        "posting_mode": payload.get("posting_mode") or "all",
        "is_active": payload.get("is_active", True),
        "membership_status": payload["membership_status"],
        "can_join": payload["can_join"],
        "can_apply": payload["can_apply"],
        "can_manage": payload["can_manage"],
        "room_id": payload["room_id"],
        "member_count": payload["member_count"],
        "pending_count": payload.get("pending_count"),
    }


def serialize_recruiting_chat_summary(
    organization: Organization,
    viewer: AbstractBaseUser | None,
) -> dict[str, Any] | None:
    chats = list_visible_organization_chats(organization, viewer)
    if not chats:
        return None
    payload = serialize_recruiting_chat_for_viewer(
        chats[0],
        viewer,
        include_manager_fields=can_manage_organization(viewer, organization),
    )
    return _chat_summary_payload(payload)


def list_visible_organization_chats(
    organization: Organization | None,
    viewer: AbstractBaseUser | None,
) -> list[OrganizationRecruitingChat]:
    if organization is None or not getattr(organization, "pk", None):
        return []
    rows = list(
        OrganizationRecruitingChat.objects.select_related("organization", "room")
        .filter(organization=organization)
        .order_by("-is_active", "pk")
    )
    return [chat for chat in rows if can_see_recruiting_chat(viewer, chat)]


def pin_recruiting_message(
    *,
    chat: OrganizationRecruitingChat,
    actor: AbstractBaseUser,
    message_id: int | None,
) -> OrganizationRecruitingChat:
    assert_can_manage_recruiting_chat(actor, chat)
    if not can_access_recruiting_room(chat.room, actor):
        raise OrganizationRecruitingChatError("forbidden", status=403)
    with transaction.atomic():
        locked = _lock_chat(chat.pk)
        assert_can_manage_recruiting_chat(actor, locked)
        if message_id in (None, 0, ""):
            locked.pinned_message = None
        else:
            try:
                message = ChatMessage.objects.get(pk=int(message_id), room=locked.room)
            except (TypeError, ValueError, ChatMessage.DoesNotExist) as exc:
                raise OrganizationRecruitingChatError("not_found", status=404) from exc
            if message.deleted_at or message.is_hidden:
                raise OrganizationRecruitingChatError("invalid_message")
            locked.pinned_message = message
        locked.save(update_fields=["pinned_message", "updated_at"])
    return locked


def build_recruiting_conversations(user: AbstractBaseUser) -> list[dict[str, Any]]:
    from .group_chat_services import (
        count_unread_group_messages,
        get_group_read_state_map,
    )
    from .organization_api_services import get_organization_avatar_url
    from .spa_canonical import recruiting_chat_spa_path

    rooms = list(list_recruiting_rooms_for_user(user))
    read_map = get_group_read_state_map(user, [room.pk for room in rooms])
    conversations = []
    for room in rooms:
        chat = getattr(room, "organization_recruiting_chat", None)
        organization = getattr(chat, "organization", None) if chat else None
        if organization is None and chat is not None:
            organization = _organization_for_chat(chat)
        latest = room.latest_messages[0] if getattr(room, "latest_messages", None) else None
        member_count = len(room.member_list) if hasattr(room, "member_list") else 0
        can_manage = can_manage_organization(user, organization)
        slug = getattr(organization, "slug", "") or ""
        conversations.append(
            {
                "kind": "recruiting",
                "room": room,
                "display_name": (chat.name if chat else "")
                or room.name
                or f"団体チャット #{room.pk}",
                "subtitle": getattr(organization, "name", "") or "団体チャット",
                "status_label": "団体チャット",
                "member_count": member_count,
                "latest_message": latest,
                "unread_count": count_unread_group_messages(
                    room, user, read_map.get(room.pk, 0)
                ),
                "updated_at": latest.created_at if latest else room.updated_at,
                "organization_id": getattr(organization, "pk", None),
                "organization_slug": slug,
                "organization_name": getattr(organization, "name", "") or "",
                "organization_avatar_url": (
                    get_organization_avatar_url(organization) if organization else ""
                ),
                "viewer_role": "manager" if can_manage else "member",
                "spa_path": recruiting_chat_spa_path(
                    slug, room.pk, getattr(chat, "pk", None)
                ),
                "thumbnail_url": (
                    get_organization_avatar_url(organization) if organization else ""
                ),
            }
        )
    return conversations


def build_recruiting_unread_summary(user: AbstractBaseUser) -> dict[str, Any]:
    conversations = build_recruiting_conversations(user)
    rooms = [
        {
            "kind": "recruiting",
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


def _serialize_recruiting_messages(
    messages: list[ChatMessage], viewer_id: int
) -> list[dict[str, Any]]:
    from .organization_event_lottery_services import lottery_share_extras_for_messages
    from .organization_event_services import event_share_extras_for_messages

    extras = lottery_share_extras_for_messages(messages)
    extras.update(event_share_extras_for_messages(messages))
    return [
        serialize_chat_message(
            message,
            viewer_id,
            extra=(
                None
                if message.deleted_at or message.is_hidden
                else extras.get(message.pk)
            ),
        )
        for message in messages
    ]


def get_accessible_recruiting_room(
    room_pk: int, user: AbstractBaseUser
) -> ChatRoom:
    try:
        room = ChatRoom.objects.select_related(
            "organization_recruiting_chat",
            "organization_recruiting_chat__organization",
        ).get(pk=room_pk, kind=ChatRoom.Kind.RECRUITING)
    except ChatRoom.DoesNotExist as exc:
        raise OrganizationRecruitingChatError("not_found", status=404) from exc
    if not can_access_recruiting_room(room, user):
        raise OrganizationRecruitingChatError("forbidden", status=403)
    return room


def build_recruiting_room_payload(
    room: ChatRoom, viewer: AbstractBaseUser
) -> dict[str, Any]:
    from .chat_pagination import history_meta, slice_chat_history
    from .group_chat_services import mark_group_room_read

    chat = get_recruiting_chat_for_room(room)
    if chat is None:
        raise OrganizationRecruitingChatError("not_found", status=404)
    if not can_access_recruiting_room(room, viewer):
        raise OrganizationRecruitingChatError("forbidden", status=403)
    base_qs = visible_chat_messages_qs(room)
    messages, has_more, next_before = slice_chat_history(base_qs)
    latest_id = mark_group_room_read(room, viewer)
    organization = _organization_for_chat(chat)
    chat_payload = serialize_recruiting_chat_for_viewer(chat, viewer)
    return {
        "ok": True,
        "room": {
            "id": room.pk,
            "kind": ChatRoom.Kind.RECRUITING,
            "name": chat.name,
            "can_send": bool(chat_payload.get("can_send")),
            "latest_id": latest_id or 0,
            "member_count": ChatRoomMembership.objects.filter(room=room).count(),
            "viewer_role": (
                "manager"
                if can_manage_organization(viewer, organization)
                else "member"
            ),
            "organization_id": chat.organization_id,
            "organization_slug": getattr(organization, "slug", "") or "",
            "organization_name": getattr(organization, "name", "") or "",
            "membership_status": "joined",
        },
        "recruiting_chat": chat_payload,
        "messages": _serialize_recruiting_messages(messages, viewer.pk),
        **history_meta(has_more, next_before),
    }


def build_recruiting_messages_payload(
    room: ChatRoom,
    viewer: AbstractBaseUser,
    *,
    after: str = "",
    before: str = "",
) -> dict[str, Any]:
    from .chat_pagination import (
        history_meta,
        parse_message_pk,
        slice_chat_history,
        slice_chat_poll,
    )
    from .group_chat_services import mark_group_room_read

    if not can_access_recruiting_room(room, viewer):
        raise OrganizationRecruitingChatError("forbidden", status=403)
    base_qs = visible_chat_messages_qs(room)
    before_pk = parse_message_pk(before)
    after_pk = parse_message_pk(after)
    if before_pk is not None:
        page, has_more, next_before = slice_chat_history(base_qs, before=before_pk)
        messages = page
        history = history_meta(has_more, next_before)
    elif after_pk is not None:
        messages = slice_chat_poll(base_qs, after=after_pk)
        history = history_meta(False, None)
    else:
        messages, has_more, next_before = slice_chat_history(base_qs)
        history = history_meta(has_more, next_before)
    latest_id = mark_group_room_read(room, viewer)
    return {
        "ok": True,
        "messages": _serialize_recruiting_messages(messages, viewer.pk),
        "latest_id": latest_id or 0,
        "can_send": serialize_recruiting_chat_for_viewer(
            get_recruiting_chat_for_room(room), viewer
        ).get("can_send", False)
        if get_recruiting_chat_for_room(room)
        else False,
        **history,
    }


@receiver(post_delete, sender=OrganizationRecruitingChat)
def delete_orphaned_recruiting_room(sender, instance, **kwargs) -> None:
    """設定行削除時に kind=recruiting の ChatRoom を残さない。"""
    room_id = getattr(instance, "room_id", None)
    if not room_id:
        return
    ChatRoom.objects.filter(pk=room_id, kind=ChatRoom.Kind.RECRUITING).delete()
