"""Map classic Notification.link → React Router spa_path (basename=/app)."""

from __future__ import annotations

import re
from typing import Any

from django.contrib.auth.models import AbstractBaseUser
from django.utils import timezone

from .models import Notification
from .notification_services import (
    get_unread_notification_count,
    mark_all_notifications_read,
)
from .spa_canonical import normalize_path_for_spa_mapping


_DM_RE = re.compile(r"^/dm/(\d+)/?$")
_DM_INBOX_RE = re.compile(r"^/dm/?$")
_GROUP_RE = re.compile(r"^/dm/groups/(\d+)/?$")
_GROUP_CREATE_RE = re.compile(r"^/dm/groups/(?:new|create)/?$")
_USER_RE = re.compile(r"^/user/(\d+)/?")
_USERS_SPA_RE = re.compile(r"^/users/(\d+)(?:/([\w-]+))?/?$")
_PRODUCT_TRADE_RE = re.compile(r"^/product/(\d+)/trade/?$")
_PRODUCT_RE = re.compile(r"^/product/(\d+)/?")
_FLEA_PRODUCT_RE = re.compile(r"^/flea/products/(\d+)/?")
_CHAT_RE = re.compile(r"^/chat/(\d+)/?")
_FLEA_CHAT_RE = re.compile(r"^/flea/chats/(\d+)/?")
_COMMUNITY_THREAD_RE = re.compile(
    r"^/communities/([^/]+)/threads/(\d+)/?"
)
_COMMUNITY_INDEX_RE = re.compile(r"^/communities/?$")
_FLEA_RE = re.compile(r"^/flea/?$")
_EXHIBIT_RE = re.compile(r"^/exhibit/?$")
_FLEA_EXHIBIT_RE = re.compile(r"^/flea/exhibit/?$")
_TIMETABLE_RE = re.compile(r"^/timetable/?$")
_TIMETABLE_USER_RE = re.compile(r"^/timetable/user/(\d+)/?")
_SEARCH_RE = re.compile(r"^/search/?$")
_NOTIFICATIONS_RE = re.compile(r"^/notifications/?$")
_MORE_RE = re.compile(r"^/more/?$")
_FOLLOW_REQUESTS_RE = re.compile(r"^/settings/follow-requests/?$")
_LOGIN_RE = re.compile(r"^/login/?$")
_SIGNUP_RE = re.compile(r"^/signup/?$")
_VERIFY_RE = re.compile(r"^/verify(?:-otp)?/?$")
_PASSWORD_RESET_RE = re.compile(r"^/password-reset/?$")
_PASSWORD_RESET_VERIFY_RE = re.compile(r"^/password-reset/verify/?$")
_PASSWORD_RESET_SET_RE = re.compile(r"^/password-reset/set/?$")


def _with_query_fragment(spa: str, query: str, fragment: str) -> str:
    if query:
        spa = f"{spa}?{query}"
    if fragment:
        spa = f"{spa}#{fragment}"
    return spa


def notification_spa_path(link: str) -> str:
    """Map Notification.link (classic or /app/…) to React Router paths."""
    path, query, fragment = normalize_path_for_spa_mapping(link)
    if not path and not fragment:
        return ""

    m = _DM_RE.match(path)
    if m:
        return f"/dm/{m.group(1)}"
    if _DM_INBOX_RE.match(path):
        return "/dm"
    m = _GROUP_RE.match(path)
    if m:
        return f"/dm/groups/{m.group(1)}"
    if _GROUP_CREATE_RE.match(path):
        return "/dm/groups/new"
    m = _USERS_SPA_RE.match(path)
    if m:
        tab = m.group(2) or "posts"
        return f"/users/{m.group(1)}/{tab}"
    m = _USER_RE.match(path)
    if m:
        return f"/users/{m.group(1)}/posts"
    m = _PRODUCT_TRADE_RE.match(path)
    if m:
        return f"/flea/products/{m.group(1)}"
    m = _FLEA_PRODUCT_RE.match(path)
    if m:
        return f"/flea/products/{m.group(1)}"
    m = _PRODUCT_RE.match(path)
    if m:
        return f"/flea/products/{m.group(1)}"
    m = _FLEA_CHAT_RE.match(path)
    if m:
        return f"/flea/chats/{m.group(1)}"
    m = _CHAT_RE.match(path)
    if m:
        return f"/flea/chats/{m.group(1)}"
    m = _COMMUNITY_THREAD_RE.match(path)
    if m:
        return f"/communities/{m.group(1)}/threads/{m.group(2)}"
    if _COMMUNITY_INDEX_RE.match(path):
        return _with_query_fragment("/communities", query, "")
    if _FLEA_EXHIBIT_RE.match(path) or _EXHIBIT_RE.match(path):
        return "/flea/exhibit"
    if _FLEA_RE.match(path):
        return _with_query_fragment("/flea", query, "")
    m = _TIMETABLE_USER_RE.match(path)
    if m:
        return f"/timetable/user/{m.group(1)}"
    if _TIMETABLE_RE.match(path):
        return "/timetable"
    if _SEARCH_RE.match(path):
        return _with_query_fragment("/search", query, "")
    if _NOTIFICATIONS_RE.match(path):
        return "/notifications"
    if _MORE_RE.match(path):
        return "/more"
    if _FOLLOW_REQUESTS_RE.match(path):
        return "/settings/follow-requests"
    if _LOGIN_RE.match(path):
        return _with_query_fragment("/login", query, "")
    if _SIGNUP_RE.match(path):
        return "/signup"
    if _VERIFY_RE.match(path):
        return "/verify"
    if _PASSWORD_RESET_SET_RE.match(path):
        return "/password-reset/set"
    if _PASSWORD_RESET_VERIFY_RE.match(path):
        return "/password-reset/verify"
    if _PASSWORD_RESET_RE.match(path):
        return "/password-reset"

    if path in ("/", ""):
        return _with_query_fragment("/", query, fragment)

    return ""


def serialize_notification(n: Notification) -> dict[str, Any]:
    created = timezone.localtime(n.created_at)
    link = n.link or ""
    return {
        "id": n.pk,
        "message": n.message,
        "link": link,
        "spa_path": notification_spa_path(link),
        "is_read": bool(n.is_read),
        "created_at": created.strftime("%Y/%m/%d %H:%M"),
    }


def build_notifications_payload(
    user: AbstractBaseUser, *, mark_read: bool = True
) -> dict[str, Any]:
    items = list(
        Notification.objects.filter(recipient=user).order_by("-created_at")[:200]
    )
    payload_items = [serialize_notification(n) for n in items]
    marked = 0
    if mark_read:
        marked = mark_all_notifications_read(user)
    return {
        "ok": True,
        "notifications": payload_items,
        "unread_count": 0 if mark_read else get_unread_notification_count(user),
        "marked_count": marked,
    }
