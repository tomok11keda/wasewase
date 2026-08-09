"""Classic page URLs → React SPA `/app/*` (when WASE_REACT_SPA is on).

Keeps Classic views/templates in the tree; GET entrypoints redirect to SPA routes
that already exist in frontend/src/App.tsx.
"""

from __future__ import annotations

from functools import wraps
from typing import Callable
from urllib.parse import urlparse

from django.conf import settings
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.urls import reverse


def spa_enabled() -> bool:
    return bool(getattr(settings, "WASE_REACT_SPA", False))


def app_absolute(spa_router_path: str) -> str:
    """Map a React Router path (basename=/app) to a site path under /app/."""
    path = (spa_router_path or "/").strip() or "/"
    if not path.startswith("/"):
        path = f"/{path}"
    if path == "/app" or path.startswith("/app/"):
        return "/app/" if path == "/app" else path
    if path == "/":
        return "/app/"
    return f"/app{path}"


def with_request_query(request: HttpRequest, target: str) -> str:
    qs = request.META.get("QUERY_STRING") or ""
    if not qs:
        return target
    sep = "&" if "?" in target else "?"
    return f"{target}{sep}{qs}"


def spa_get_redirect(
    spa_path_factory: Callable[..., str | None],
) -> Callable[[Callable[..., HttpResponse]], Callable[..., HttpResponse]]:
    """Wrap a Classic page view: GET/HEAD → SPA when enabled; else Classic."""

    def decorator(view_func: Callable[..., HttpResponse]) -> Callable[..., HttpResponse]:
        @wraps(view_func)
        def wrapped(request: HttpRequest, *args, **kwargs) -> HttpResponse:
            if spa_enabled() and request.method in ("GET", "HEAD"):
                spa = spa_path_factory(request, *args, **kwargs)
                if spa:
                    return redirect(with_request_query(request, app_absolute(spa)))
            return view_func(request, *args, **kwargs)

        return wrapped

    return decorator


# --- Absolute links stored on notifications / push / redirects -----------------


def trade_chat_url(room_pk: int) -> str:
    if spa_enabled():
        return app_absolute(f"/flea/chats/{room_pk}")
    return reverse("chat_room", kwargs={"room_pk": room_pk})


def product_detail_url(pk: int) -> str:
    if spa_enabled():
        return app_absolute(f"/flea/products/{pk}")
    return reverse("product_detail", kwargs={"pk": pk})


def dm_room_url(room_pk: int) -> str:
    if spa_enabled():
        return app_absolute(f"/dm/{room_pk}")
    return reverse("user_dm_room", kwargs={"room_pk": room_pk})


def dm_inbox_url() -> str:
    if spa_enabled():
        return app_absolute("/dm")
    return reverse("user_dm_inbox")


def group_room_url(room_pk: int) -> str:
    if spa_enabled():
        return app_absolute(f"/dm/groups/{room_pk}")
    return reverse("dm_group_room", kwargs={"room_pk": room_pk})


def group_create_url() -> str:
    if spa_enabled():
        return app_absolute("/dm/groups/new")
    return reverse("dm_group_create")


def user_profile_url(pk: int, *, tab: str = "posts") -> str:
    if spa_enabled():
        return app_absolute(f"/users/{pk}/{tab}")
    return reverse("user_profile", kwargs={"pk": pk})


def normalize_path_for_spa_mapping(link: str) -> tuple[str, str, str]:
    """Return (path, query, fragment) with optional /app prefix stripped."""
    raw = (link or "").strip()
    if not raw:
        return "", "", ""
    parsed = urlparse(raw)
    path = parsed.path or "/"
    if path == "/app":
        path = "/"
    elif path.startswith("/app/"):
        path = path[4:] or "/"
    return path, parsed.query, parsed.fragment


def canonicalize_next_url(raw: str | None, *, default: str = "/app/") -> str:
    """Normalize post-login `next` to a same-origin path.

    - External / protocol-relative URLs → ``default``
    - Mapped Classic or ``/app/...`` paths → absolute ``/app/...`` (SPA)
    - Unmapped relative paths (e.g. ``/mypage/settings/``) → kept as-is
    """
    # Lazy import: notification_api_services imports helpers from this module.
    from .notification_api_services import notification_spa_path

    next_url = (raw or "").strip()
    if not next_url:
        return default
    if next_url.startswith("//") or next_url.startswith("\\\\"):
        return default

    parsed = urlparse(next_url)
    if parsed.scheme or parsed.netloc:
        return default
    if not next_url.startswith("/"):
        return default

    path, query, fragment = normalize_path_for_spa_mapping(next_url)
    spa_router = notification_spa_path(path)
    if not spa_router:
        rebuilt = path or "/"
        if query:
            rebuilt = f"{rebuilt}?{query}"
        if fragment:
            rebuilt = f"{rebuilt}#{fragment}"
        return rebuilt

    spa_parsed = urlparse(spa_router)
    spa_path = spa_parsed.path or "/"
    out_q = spa_parsed.query or query
    out_f = spa_parsed.fragment or fragment
    result = app_absolute(spa_path)
    if out_q:
        result = f"{result}?{out_q}"
    if out_f:
        result = f"{result}#{out_f}"
    return result
