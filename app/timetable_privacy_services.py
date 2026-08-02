"""時間割公開設定の読み書き（Django DB + Firestore ミラー）。"""

from __future__ import annotations

import logging

from django.contrib.auth.models import AbstractBaseUser
from django.db.utils import OperationalError, ProgrammingError

from .bookmark_services import get_firestore_client
from .models import UserProfile

logger = logging.getLogger(__name__)


def _ensure_is_timetable_public_column() -> None:
    try:
        from app.media_services import ensure_userprofile_is_timetable_public_column

        ensure_userprofile_is_timetable_public_column()
    except Exception as exc:
        logger.warning("Failed to ensure is_timetable_public column: %s", exc)


def is_timetable_public_value(profile: UserProfile | None) -> bool:
    """プロファイルから公開フラグを安全に読む。未設定・欠損時は False。"""
    if profile is None:
        return False
    value = getattr(profile, "is_timetable_public", None)
    if value is None:
        return False
    return bool(value)


def get_or_create_profile(user: AbstractBaseUser) -> UserProfile:
    _ensure_is_timetable_public_column()
    try:
        profile, _ = UserProfile.objects.get_or_create(user=user)
        return profile
    except (OperationalError, ProgrammingError) as exc:
        logger.warning(
            "get_or_create UserProfile failed (retry after schema repair): %s",
            exc,
        )
        _ensure_is_timetable_public_column()
        profile, _ = UserProfile.objects.get_or_create(user=user)
        return profile


def is_timetable_public_for(user: AbstractBaseUser | None) -> bool:
    if user is None or not getattr(user, "pk", None):
        return False
    try:
        value = (
            UserProfile.objects.filter(user_id=user.pk)
            .values_list("is_timetable_public", flat=True)
            .first()
        )
    except (OperationalError, ProgrammingError) as exc:
        logger.warning(
            "is_timetable_public_for failed for user=%s: %s",
            getattr(user, "pk", None),
            exc,
        )
        _ensure_is_timetable_public_column()
        try:
            value = (
                UserProfile.objects.filter(user_id=user.pk)
                .values_list("is_timetable_public", flat=True)
                .first()
            )
        except (OperationalError, ProgrammingError):
            return False
    if value is None:
        return False
    return bool(value)


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
    try:
        profile.save(update_fields=["is_timetable_public"])
    except (OperationalError, ProgrammingError) as exc:
        logger.warning(
            "save is_timetable_public failed (retry after schema repair): %s",
            exc,
        )
        _ensure_is_timetable_public_column()
        profile.is_timetable_public = bool(is_public)
        profile.save(update_fields=["is_timetable_public"])
    _mirror_timetable_public_to_firestore(user, is_timetable_public_value(profile))
    return profile


def toggle_timetable_public(user: AbstractBaseUser) -> UserProfile:
    profile = get_or_create_profile(user)
    return set_timetable_public(user, not is_timetable_public_value(profile))
