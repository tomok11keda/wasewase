"""ChatMessage の運営削除・復元・異議申し立て。"""

from __future__ import annotations

from django.contrib.auth.base_user import AbstractBaseUser
from django.db import IntegrityError, transaction
from django.utils import timezone

from .models import ChatMessage, ChatMessageModerationAppeal, ContentReport

APPEAL_EXPLANATION_MAX = 1000


def mark_chat_message_reports_handled(
    message_id: int, moderator: AbstractBaseUser
) -> int:
    now = timezone.now()
    return ContentReport.objects.filter(
        target_type=ContentReport.TargetType.CHAT_MESSAGE,
        target_id=message_id,
        handled_at__isnull=True,
    ).update(handled_at=now, handled_by=moderator)


@transaction.atomic
def hide_chat_message(
    *,
    message: ChatMessage,
    moderator: AbstractBaseUser,
    reason: str = "",
) -> ChatMessage:
    locked = ChatMessage.objects.select_for_update().get(pk=message.pk)
    if not locked.is_hidden:
        locked.is_hidden = True
        locked.removed_at = timezone.now()
        locked.removed_by = moderator
        locked.removal_reason = (reason or "").strip()[:200]
        locked.save(
            update_fields=["is_hidden", "removed_at", "removed_by", "removal_reason"]
        )
    mark_chat_message_reports_handled(locked.pk, moderator)
    return locked


@transaction.atomic
def restore_chat_message(
    *,
    message: ChatMessage,
    moderator: AbstractBaseUser,
    review_note: str = "",
) -> ChatMessage:
    locked = ChatMessage.objects.select_for_update().get(pk=message.pk)
    if locked.is_hidden:
        locked.is_hidden = False
        locked.removed_at = None
        locked.removed_by = None
        locked.removal_reason = ""
        locked.save(
            update_fields=["is_hidden", "removed_at", "removed_by", "removal_reason"]
        )
    now = timezone.now()
    note = (review_note or "").strip()
    pending = ChatMessageModerationAppeal.objects.select_for_update().filter(
        message=locked,
        status=ChatMessageModerationAppeal.Status.PENDING,
    )
    for appeal in pending:
        appeal.status = ChatMessageModerationAppeal.Status.ACCEPTED
        appeal.reviewed_at = now
        appeal.reviewer = moderator
        if note:
            appeal.review_note = note
        appeal.save(
            update_fields=["status", "reviewed_at", "reviewer", "review_note"]
        )
    return locked


def submit_chat_message_appeal(
    *,
    message: ChatMessage,
    user: AbstractBaseUser,
    explanation: str,
) -> ChatMessageModerationAppeal:
    if message.sender_id != user.pk:
        raise ValueError("forbidden")
    if not message.is_hidden:
        raise ValueError("not_removed")
    text = (explanation or "").strip()
    if not text:
        raise ValueError("empty")
    if len(text) > APPEAL_EXPLANATION_MAX:
        raise ValueError("too_long")
    if ChatMessageModerationAppeal.objects.filter(
        message=message,
        appellant=user,
        status=ChatMessageModerationAppeal.Status.PENDING,
    ).exists():
        raise ValueError("already_pending")
    try:
        return ChatMessageModerationAppeal.objects.create(
            message=message,
            appellant=user,
            explanation=text,
        )
    except IntegrityError as exc:
        raise ValueError("already_pending") from exc


@transaction.atomic
def accept_chat_message_appeal(
    appeal: ChatMessageModerationAppeal,
    reviewer: AbstractBaseUser,
    *,
    note: str = "",
) -> ChatMessageModerationAppeal:
    locked = ChatMessageModerationAppeal.objects.select_for_update().select_related(
        "message"
    ).get(pk=appeal.pk)
    if locked.status == ChatMessageModerationAppeal.Status.REJECTED:
        raise ValueError("already_reviewed")
    restore_chat_message(
        message=locked.message,
        moderator=reviewer,
        review_note=note,
    )
    return ChatMessageModerationAppeal.objects.get(pk=locked.pk)


@transaction.atomic
def reject_chat_message_appeal(
    appeal: ChatMessageModerationAppeal,
    reviewer: AbstractBaseUser,
    *,
    note: str = "",
) -> ChatMessageModerationAppeal:
    locked = ChatMessageModerationAppeal.objects.select_for_update().select_related(
        "message"
    ).get(pk=appeal.pk)
    if locked.status == ChatMessageModerationAppeal.Status.REJECTED:
        return locked
    if locked.status != ChatMessageModerationAppeal.Status.PENDING:
        raise ValueError("already_reviewed")
    locked.status = ChatMessageModerationAppeal.Status.REJECTED
    locked.reviewed_at = timezone.now()
    locked.reviewer = reviewer
    if note:
        locked.review_note = note.strip()
    locked.save(update_fields=["status", "reviewed_at", "reviewer", "review_note"])
    return locked
