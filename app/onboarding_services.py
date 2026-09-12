"""Post-OTP onboarding: profile, follow suggestions, completion."""

from __future__ import annotations

import random
from typing import Any

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AbstractBaseUser
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from .constants import FACULTY_CHOICES
from .follow_services import get_follow_state
from .handle_services import (
    clean_unique_handle,
    is_placeholder_handle,
    public_username,
)
from .media_services import validate_timeline_image_file
from .models import Follow, UserProfile
from .services import get_user_avatar_url
from .timeline_api_services import serialize_author
from .timetable_privacy_services import get_or_create_profile
from .ugc_services import get_either_blocked_user_ids

User = get_user_model()

ONBOARDING_STEP_PROFILE = UserProfile.ONBOARDING_STEP_PROFILE
ONBOARDING_STEP_FOLLOW = UserProfile.ONBOARDING_STEP_FOLLOW
ONBOARDING_STEP_WELCOME = UserProfile.ONBOARDING_STEP_WELCOME
SUGGESTION_LIMIT = 10
FOLLOW_GOAL = 3
FACULTY_VALUES = {value for value, _label in FACULTY_CHOICES}


def needs_onboarding(user: AbstractBaseUser | None) -> bool:
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_staff", False) or getattr(user, "is_superuser", False):
        return False
    profile = get_or_create_profile(user)
    if profile.onboarding_exempt:
        return False
    return profile.onboarding_completed_at is None


def _has_saved_identity(user: AbstractBaseUser, profile: UserProfile) -> bool:
    name = (profile.name or "").strip()
    department = (profile.department or "").strip()
    handle = public_username(user)
    return bool(name and department and handle and not is_placeholder_handle(handle))


def public_handle_for_me(user: AbstractBaseUser, profile: UserProfile) -> str:
    handle = public_username(user)
    if is_placeholder_handle(handle) and not _has_saved_identity(user, profile):
        return ""
    return handle


def display_name_for_me(user: AbstractBaseUser, profile: UserProfile) -> str:
    name = (profile.name or "").strip()
    if name:
        return name
    handle = public_handle_for_me(user, profile)
    return handle or "ユーザー"


def onboarding_payload(user: AbstractBaseUser) -> dict[str, Any]:
    profile = get_or_create_profile(user)
    required = needs_onboarding(user)
    handle = public_username(user)
    placeholder = is_placeholder_handle(handle) and not _has_saved_identity(
        user, profile
    )
    step = profile.onboarding_step or ONBOARDING_STEP_PROFILE
    if step not in {
        ONBOARDING_STEP_PROFILE,
        ONBOARDING_STEP_FOLLOW,
        ONBOARDING_STEP_WELCOME,
    }:
        step = ONBOARDING_STEP_PROFILE
    return {
        "ok": True,
        "required": required,
        "completed": not required,
        "step": step if required else ONBOARDING_STEP_WELCOME,
        "follow_goal": FOLLOW_GOAL,
        "profile": {
            "name": (profile.name or "").strip(),
            "username": "" if placeholder else handle,
            "username_is_placeholder": placeholder,
            "department": (profile.department or "").strip(),
            "avatar_url": get_user_avatar_url(user) or "",
        },
        "faculties": [{"value": v, "label": label} for v, label in FACULTY_CHOICES],
    }


def save_onboarding_profile(
    user: AbstractBaseUser,
    *,
    name: str,
    username: str,
    department: str,
    avatar=None,
) -> dict[str, Any]:
    profile = get_or_create_profile(user)
    nickname = (name or "").strip()
    faculty = (department or "").strip()
    errors: dict[str, list[str]] = {}
    if not nickname:
        errors["name"] = ["表示名を入力してください。"]
    elif len(nickname) > 80:
        errors["name"] = ["表示名は80文字以内で入力してください。"]
    if not faculty or faculty not in FACULTY_VALUES:
        errors["department"] = ["学部を選択してください。"]

    current = public_username(user)
    placeholder_current = is_placeholder_handle(current) and not _has_saved_identity(
        user, profile
    )
    try:
        handle = clean_unique_handle(username, exclude_user_pk=user.pk)
    except ValidationError as exc:
        errors["username"] = [str(e) for e in exc.messages]
        handle = ""
    else:
        if placeholder_current and is_placeholder_handle(handle):
            errors["username"] = ["ユーザー名を自分で設定してください。"]

    if avatar is not None and getattr(avatar, "name", ""):
        try:
            validate_timeline_image_file(avatar)
        except ValidationError as exc:
            errors["avatar"] = [str(e) for e in exc.messages]

    if errors:
        return {"ok": False, "error": "validation", "errors": errors}

    try:
        with transaction.atomic():
            profile.name = nickname
            profile.department = faculty
            profile.onboarding_step = ONBOARDING_STEP_FOLLOW
            if avatar is not None and getattr(avatar, "name", ""):
                profile.avatar = avatar
            profile.save()
            if handle != current:
                updated = User.objects.filter(pk=user.pk).update(username=handle)
                if not updated:
                    raise IntegrityError("username")
                user.username = handle
    except IntegrityError:
        return {
            "ok": False,
            "error": "validation",
            "errors": {"username": ["このユーザー名はすでに使われています。"]},
        }

    return {
        "ok": True,
        "step": ONBOARDING_STEP_FOLLOW,
        "profile": onboarding_payload(user)["profile"],
    }


def _profile_step_completed_q() -> Q:
    """Public-profile-ready: Profile Step done, not full onboarding complete."""
    return Q(
        profile__onboarding_step__in=[
            ONBOARDING_STEP_FOLLOW,
            ONBOARDING_STEP_WELCOME,
        ]
    ) | Q(profile__onboarding_completed_at__isnull=False)


def _suggestion_qs(viewer: AbstractBaseUser, *, blocked_ids: set[int]):
    qs = (
        User.objects.filter(
            is_active=True,
            is_staff=False,
            is_superuser=False,
            profile__is_private=False,
        )
        .filter(_profile_step_completed_q())
        .exclude(pk=viewer.pk)
        .exclude(profile__name="")
        .select_related("profile")
    )
    if blocked_ids:
        qs = qs.exclude(pk__in=blocked_ids)
    return qs


def list_onboarding_suggestions(
    viewer: AbstractBaseUser, *, limit: int = SUGGESTION_LIMIT
) -> dict[str, Any]:
    profile = get_or_create_profile(viewer)
    blocked_ids = get_either_blocked_user_ids(viewer)
    following_ids = set(
        Follow.objects.filter(follower=viewer).values_list("following_id", flat=True)
    )
    qs = _suggestion_qs(viewer, blocked_ids=blocked_ids)
    faculty = (profile.department or "").strip()
    picked: list[AbstractBaseUser] = []
    seen: set[int] = set()

    def _take(pool, count: int) -> None:
        rows = [
            row
            for row in list(pool[: max(count * 4, count)])
            if not is_placeholder_handle(public_username(row))
            and (getattr(getattr(row, "profile", None), "name", None) or "").strip()
        ]
        random.shuffle(rows)
        for row in rows:
            if len(picked) >= limit:
                return
            if row.pk in seen:
                continue
            seen.add(row.pk)
            picked.append(row)

    if faculty:
        _take(qs.filter(profile__department=faculty).order_by("-date_joined"), limit)
    if len(picked) < limit:
        rest = qs.exclude(pk__in=seen).order_by("-date_joined")
        _take(rest, limit - len(picked))

    random.shuffle(picked)
    users = []
    for candidate in picked[:limit]:
        payload = serialize_author(candidate) or {}
        cand_profile = getattr(candidate, "profile", None)
        payload["department"] = (
            (getattr(cand_profile, "department", None) or "") if cand_profile else ""
        )
        payload["is_following"] = candidate.pk in following_ids
        payload["follow_state"] = get_follow_state(viewer, candidate)
        users.append(payload)
    following_count = sum(1 for row in users if row.get("is_following"))
    return {
        "ok": True,
        "users": users,
        "follow_goal": FOLLOW_GOAL,
        "following_count": following_count,
    }


def advance_follow_step(user: AbstractBaseUser) -> dict[str, Any]:
    if not needs_onboarding(user):
        return {"ok": True, "step": ONBOARDING_STEP_WELCOME, "completed": True}
    profile = get_or_create_profile(user)
    if profile.onboarding_step == ONBOARDING_STEP_PROFILE:
        return {
            "ok": False,
            "error": "profile_incomplete",
            "message": "先にプロフィールを設定してください。",
            "step": ONBOARDING_STEP_PROFILE,
        }
    profile.onboarding_step = ONBOARDING_STEP_WELCOME
    profile.save(update_fields=["onboarding_step"])
    return {"ok": True, "step": ONBOARDING_STEP_WELCOME, "completed": False}


def complete_onboarding(user: AbstractBaseUser) -> dict[str, Any]:
    if not needs_onboarding(user):
        return {"ok": True, "completed": True, "step": ONBOARDING_STEP_WELCOME}
    profile = get_or_create_profile(user)
    if profile.onboarding_step != ONBOARDING_STEP_WELCOME:
        return {
            "ok": False,
            "error": "not_ready",
            "message": "オンボーディングを最後まで進めてください。",
            "step": profile.onboarding_step or ONBOARDING_STEP_PROFILE,
        }
    profile.onboarding_completed_at = timezone.now()
    profile.save(update_fields=["onboarding_completed_at"])
    return {"ok": True, "completed": True, "step": ONBOARDING_STEP_WELCOME}
