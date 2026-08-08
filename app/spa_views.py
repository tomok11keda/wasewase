"""React SPA (Phase 1–2) 向けの薄い JSON API。"""

from __future__ import annotations

from django.conf import settings
from django.http import HttpRequest, HttpResponse, HttpResponseNotFound, JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET

from .browse_mode_services import is_browse_mode
from .inbox_services import get_unread_inbox_message_count
from .notification_services import get_unread_notification_count


def _display_name(user) -> str:
    profile = getattr(user, "profile", None)
    name = (getattr(profile, "name", None) or "").strip()
    if name:
        return name
    return (user.get_username() or user.email or "ユーザー").strip()


def _avatar_url(user) -> str:
    profile = getattr(user, "profile", None)
    avatar = getattr(profile, "avatar", None) if profile is not None else None
    if avatar:
        try:
            return avatar.url
        except ValueError:
            pass
    return ""


def _initial(user) -> str:
    label = _display_name(user)
    return (label[:1] or "?").upper()


@require_GET
def api_v1_me(request: HttpRequest) -> JsonResponse:
    """セッション状態のブートストラップ（認証・閲覧モード・バッジ）。"""
    user = request.user
    authenticated = bool(getattr(user, "is_authenticated", False))
    payload: dict = {
        "authenticated": authenticated,
        "is_browse_mode": is_browse_mode(request),
        "react_spa_enabled": bool(getattr(settings, "WASE_REACT_SPA", False)),
        "user": None,
        "unread_notifications": 0,
        "dm_unread_total": 0,
    }
    if authenticated:
        payload["user"] = {
            "id": user.pk,
            "email": user.email,
            "username": user.get_username(),
            "display_name": _display_name(user),
            "avatar_url": _avatar_url(user),
            "initial": _initial(user),
        }
        payload["unread_notifications"] = get_unread_notification_count(user)
        try:
            payload["dm_unread_total"] = int(
                get_unread_inbox_message_count(user) or 0
            )
        except Exception:
            payload["dm_unread_total"] = 0
    return JsonResponse(payload)


@require_GET
def spa_app(request: HttpRequest, rest: str = "") -> HttpResponse:
    """
    React SPA シェル。WASE_REACT_SPA が無効なら 404（旧 UI はそのまま）。
    /app/ および /app/<path> をすべて同一 HTML で返す。
    """
    if not getattr(settings, "WASE_REACT_SPA", False):
        return HttpResponseNotFound("React SPA is disabled (WASE_REACT_SPA=False).")
    return render(request, "spa.html")
