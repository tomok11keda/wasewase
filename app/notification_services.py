"""通知バッジ・既読化の共通ロジック。"""

from __future__ import annotations

from django.contrib.auth.models import AbstractBaseUser

from .models import Notification


def get_unread_notification_count(user: AbstractBaseUser | None) -> int:
    if user is None or not user.is_authenticated:
        return 0
    return Notification.objects.filter(recipient=user, is_read=False).count()


def mark_all_notifications_read(user: AbstractBaseUser) -> int:
    return Notification.objects.filter(recipient=user, is_read=False).update(
        is_read=True
    )
