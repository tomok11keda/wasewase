"""Map classic Notification.link → React Router spa_path (basename=/app)."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

from django.contrib.auth.models import AbstractBaseUser
from django.utils import timezone

from .models import Notification
from .notification_services import (
    get_unread_notification_count,
    mark_all_notifications_read,
)


_DM_RE = re.compile(r"^/dm/(\d+)/?$")
_DM_INBOX_RE = re.compile(r"^/dm/?$")
_GROUP_RE = re.compile(r"^/dm/groups/(\d+)/?$")
_GROUP_CREATE_RE = re.compile(r"^/dm/groups/(?:new|create)/?$")
_USER_RE = re.compile(r"^/user/(\d+)/?")
_PRODUCT_TRADE_RE = re.compile(r"^/product/(\d+)/trade/?$")
_PRODUCT_RE = re.compile(r"^/product/(\d+)/?")
_CHAT_RE = re.compile(r"^/chat/(\d+)/?")
_COMMUNITY_THREAD_RE = re.compile(
    r"^/communities/([^/]+)/threads/(\d+)/?"
)
_COMMUNITY_INDEX_RE = re.compile(r"^/communities/?$")
_FLEA_RE = re.compile(r"^/flea/?$")
_TIMETABLE_RE = re.compile(r"^/timetable/?$")
_TIMETABLE_USER_RE = re.compile(r"^/timetable/user/(\d+)/?")
_SEARCH_RE = re.compile(r"^/search/?$")
_NOTIFICATIONS_RE = re.compile(r"^/notifications/?$")


def notification_spa_path(link: str) -> str:
    """Map classic Notification.link paths to React Router paths (basename=/app)."""
    raw = (link or "").strip()
    if not raw:
        return ""
    parsed = urlparse(raw)
    path = parsed.path or "/"
    query = parsed.query
    fragment = parsed.fragment

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
    m = _USER_RE.match(path)
    if m:
        return f"/users/{m.group(1)}/posts"
    m = _PRODUCT_TRADE_RE.match(path)
    if m:
        return f"/flea/products/{m.group(1)}"
    m = _PRODUCT_RE.match(path)
    if m:
        return f"/flea/products/{m.group(1)}"
    m = _CHAT_RE.match(path)
    if m:
        return f"/flea/chats/{m.group(1)}"
    m = _COMMUNITY_THREAD_RE.match(path)
    if m:
        return f"/communities/{m.group(1)}/threads/{m.group(2)}"
    if _COMMUNITY_INDEX_RE.match(path):
        spa = "/communities"
        if query:
            spa += f"?{query}"
        return spa
    if _FLEA_RE.match(path):
        spa = "/flea"
        if query:
            spa += f"?{query}"
        return spa
    m = _TIMETABLE_USER_RE.match(path)
    if m:
        return f"/timetable/user/{m.group(1)}"
    if _TIMETABLE_RE.match(path):
        return "/timetable"
    if _SEARCH_RE.match(path):
        spa = "/search"
        if query:
            spa += f"?{query}"
        return spa
    if _NOTIFICATIONS_RE.match(path):
        return "/notifications"

    if path in ("/", ""):
        spa = "/"
        if query:
            spa += f"?{query}"
        if fragment:
            spa += f"#{fragment}"
        return spa

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
