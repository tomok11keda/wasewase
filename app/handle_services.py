"""Public @username (handle) helpers — display, validation, mention resolution."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

from .constants import HANDLE_PATTERN

User = get_user_model()


def normalize_handle(raw: str | None) -> str:
    """Trim and strip a leading @; does not validate format."""
    return (raw or "").strip().lstrip("@").strip()


def public_username(user) -> str:
    """
    Return the public handle stored on User.username.

    Never use user.get_username() for display: with USERNAME_FIELD=email that
    returns the email address.
    """
    if user is None:
        return ""
    return (getattr(user, "username", None) or "").strip()


def resolve_user_by_username(username: str | None):
    """Resolve @handle / handle to a User (case-insensitive). Returns None if missing."""
    handle = normalize_handle(username)
    if not handle:
        return None
    return User.objects.filter(username__iexact=handle).first()


def clean_unique_handle(
    raw: str | None,
    *,
    exclude_user_pk: int | None = None,
) -> str:
    """Validate and normalize a handle; raise ValidationError on failure."""
    handle = normalize_handle(raw)
    if not handle:
        raise ValidationError("ユーザー名を入力してください。")
    if not HANDLE_PATTERN.match(handle):
        raise ValidationError(
            "ユーザー名は英数字とアンダースコア（_）のみ、3〜30文字で入力してください。"
        )
    qs = User.objects.filter(username__iexact=handle)
    if exclude_user_pk is not None:
        qs = qs.exclude(pk=exclude_user_pk)
    if qs.exists():
        raise ValidationError("このユーザー名はすでに使われています。")
    return handle
