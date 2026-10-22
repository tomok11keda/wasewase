"""Throttle UserProfile.last_seen_at updates (at most once per hour)."""

from __future__ import annotations

import logging

from django.contrib.auth.models import AbstractBaseUser
from django.core.cache import cache
from django.utils import timezone

from .models import UserProfile

logger = logging.getLogger(__name__)

LAST_SEEN_TOUCH_SECONDS = 3600
_CACHE_KEY_PREFIX = "wase:last_seen:"
_SKIP_PREFIXES = (
    "/static/",
    "/media/",
    "/admin/",
    "/favicon",
)


def _should_skip_path(path: str) -> bool:
    value = path or "/"
    return any(value.startswith(prefix) for prefix in _SKIP_PREFIXES)


def last_seen_cache_key(user_id: int) -> str:
    return f"{_CACHE_KEY_PREFIX}{user_id}"


def maybe_touch_last_seen(
    user: AbstractBaseUser | None,
    *,
    path: str = "/",
) -> bool:
    """Update last_seen_at at most once an hour. Cache miss/error skips extra writes.

    Returns True when a DB row was updated.
    """
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    user_id = getattr(user, "pk", None)
    if not user_id:
        return False
    if _should_skip_path(path):
        return False

    key = last_seen_cache_key(int(user_id))
    try:
        if cache.get(key):
            return False
    except Exception:
        logger.warning("last_seen cache read failed user_id=%s", user_id)
        return False

    now = timezone.now()
    updated = UserProfile.objects.filter(user_id=user_id).update(last_seen_at=now)
    if updated == 0:
        return False

    try:
        cache.set(key, 1, LAST_SEEN_TOUCH_SECONDS)
    except Exception:
        logger.warning("last_seen cache write failed user_id=%s", user_id)
    return True
