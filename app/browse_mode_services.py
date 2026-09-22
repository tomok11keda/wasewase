"""閲覧モード（未ログインのリード専用）用のセッション／パス判定。"""

from __future__ import annotations

from django.http import HttpRequest, JsonResponse

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
    # Staff-gated; anonymous/browse still reach the view so it can 404
    # instead of leaking a 401 for an internal endpoint.
    "/api/v1/internal",
)

# Browse Mode 中に呼べる API。これ以外の /api/* は学生データとして 401。
BROWSE_MODE_API_ALLOW_PREFIXES = (
    "/api/v1/auth",
    "/api/v1/me",
    "/api/v1/courses/meta",
    "/api/v1/internal",
)


def unauthorized_json_response() -> JsonResponse:
    return JsonResponse(
        {
            "ok": False,
            "error": "unauthorized",
            "message": "authentication_required",
        },
        status=401,
    )


def _path_matches_prefixes(path: str, prefixes: tuple[str, ...]) -> bool:
    path = path or "/"
    normalized = path.rstrip("/") or "/"
    for prefix in prefixes:
        base = prefix.rstrip("/") or "/"
        if normalized == base or normalized.startswith(base + "/"):
            return True
    return False


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
    return _path_matches_prefixes(path, BROWSE_MODE_ALLOW_PREFIXES)


def path_allows_browse_mode_api(path: str) -> bool:
    return _path_matches_prefixes(path, BROWSE_MODE_API_ALLOW_PREFIXES)


def path_is_api(path: str) -> bool:
    return (path or "").startswith("/api/")


def path_denies_student_data_in_browse_mode(path: str) -> bool:
    """Browse Mode でも SPA/HTML は通す。学生データ API だけ拒否。"""
    if not path_is_api(path):
        return False
    return not path_allows_browse_mode_api(path)
