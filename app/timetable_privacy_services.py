"""時間割公開設定の読み書き（Django DB + Firestore ミラー）。"""

from __future__ import annotations

import logging

from django.contrib.auth.models import AbstractBaseUser

from .bookmark_services import get_firestore_client
from .models import UserProfile

logger = logging.getLogger(__name__)


def get_or_create_profile(user: AbstractBaseUser) -> UserProfile:
    profile, _ = UserProfile.objects.get_or_create(user=user)
    return profile


def is_timetable_public_for(user: AbstractBaseUser | None) -> bool:
    if user is None or not getattr(user, "pk", None):
        return False
    return bool(
        UserProfile.objects.filter(user_id=user.pk)
        .values_list("is_timetable_public", flat=True)
        .first()
    )


def _mirror_timetable_public_to_firestore(user: AbstractBaseUser, is_public: bool) -> None:
    """users/{userId} に isTimetablePublic を同期（利用可能な場合のみ）。"""
    db = get_firestore_client()
    if db is None:
        return
    try:
        db.collection("users").document(str(user.pk)).set(
            {"isTimetablePublic": bool(is_public)},
            merge=True,
        )
    except Exception as exc:
        logger.warning(
            "Failed to mirror isTimetablePublic for user=%s: %s",
            getattr(user, "pk", None),
            exc,
        )


def set_timetable_public(user: AbstractBaseUser, is_public: bool) -> UserProfile:
    profile = get_or_create_profile(user)
    profile.is_timetable_public = bool(is_public)
    profile.save(update_fields=["is_timetable_public"])
    _mirror_timetable_public_to_firestore(user, profile.is_timetable_public)
    return profile


def toggle_timetable_public(user: AbstractBaseUser) -> UserProfile:
    profile = get_or_create_profile(user)
    return set_timetable_public(user, not profile.is_timetable_public)
