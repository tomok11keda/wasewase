"""閲覧モード（未ログインのリード専用）用のセッション／パス判定。"""

from __future__ import annotations

from django.http import HttpRequest

BROWSE_MODE_SESSION_KEY = "browse_mode"

# 閲覧モード未選択でもアクセス可能なプレフィックス（認証・規約・静的など）
BROWSE_MODE_ALLOW_PREFIXES = (
    "/login",
    "/logout",
    "/signup",
    "/verify-otp",
    "/password-reset",
    "/browse",
    "/privacy",
    "/terms",
    "/support",
    "/manifest.json",
    "/service-worker.js",
    "/ads.txt",
    "/static/",
    "/media/",
    "/admin/",
    # React SPA auth surfaces (Phase 9)
    "/app/login",
    "/app/signup",
    "/app/verify",
    "/app/password-reset",
    "/api/v1/auth",
    "/api/v1/me",
)


def is_browse_mode(request: HttpRequest) -> bool:
    user = getattr(request, "user", None)
    if user is not None and getattr(user, "is_authenticated", False):
        return False
    return bool(request.session.get(BROWSE_MODE_SESSION_KEY))


def enable_browse_mode(request: HttpRequest) -> None:
    request.session[BROWSE_MODE_SESSION_KEY] = True
    request.session.modified = True


def clear_browse_mode(request: HttpRequest) -> None:
    if BROWSE_MODE_SESSION_KEY in request.session:
        request.session.pop(BROWSE_MODE_SESSION_KEY, None)
        request.session.modified = True


def path_allows_without_browse_mode(path: str) -> bool:
    path = path or "/"
    normalized = path.rstrip("/") or "/"
    for prefix in BROWSE_MODE_ALLOW_PREFIXES:
        base = prefix.rstrip("/") or "/"
        if normalized == base or normalized.startswith(base + "/"):
            return True
        if path.startswith(prefix):
            return True
    return False
