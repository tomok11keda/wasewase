"""通知バッジ・既読化の共通ロジック。"""

from __future__ import annotations

from django.contrib.auth.models import AbstractBaseUser
from django.db.models import Q, QuerySet

from .models import FollowRequest, Notification

# Follow-request notifications use link=/app/settings/follow-requests
_FOLLOW_REQUEST_LINK_MARKER = "/settings/follow-requests"


def follow_request_notification_q() -> Q:
    """Match Notification rows created for incoming follow requests."""
    return Q(link__icontains=_FOLLOW_REQUEST_LINK_MARKER)


def is_follow_request_notification(notification: Notification) -> bool:
    link = notification.link or ""
    return _FOLLOW_REQUEST_LINK_MARKER in link


def get_pending_follow_request_count(user: AbstractBaseUser | None) -> int:
    if user is None or not getattr(user, "is_authenticated", False):
        return 0
    return FollowRequest.objects.filter(to_user_id=user.pk).count()


def _regular_unread_qs(user: AbstractBaseUser) -> QuerySet[Notification]:
    return Notification.objects.filter(recipient=user, is_read=False).exclude(
        follow_request_notification_q()
    )


def get_regular_unread_notification_count(user: AbstractBaseUser | None) -> int:
    """Unread Notification rows excluding follow-request ping notifications."""
    if user is None or not getattr(user, "is_authenticated", False):
        return 0
    return _regular_unread_qs(user).count()


def get_unread_notification_count(user: AbstractBaseUser | None) -> int:
    """Badge total: regular unread notifications + pending follow requests.

    Follow-request Notification rows are excluded from the regular unread tally
    so the same request is not double-counted with FollowRequest rows.
    """
    if user is None or not getattr(user, "is_authenticated", False):
        return 0
    return get_regular_unread_notification_count(user) + get_pending_follow_request_count(
        user
    )


def mark_all_notifications_read(user: AbstractBaseUser) -> int:
    return Notification.objects.filter(recipient=user, is_read=False).update(
        is_read=True
    )
