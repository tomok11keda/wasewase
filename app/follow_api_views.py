"""Follow-request inbox + account privacy JSON API."""

from __future__ import annotations

import json

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from .follow_services import (
    FollowForbidden,
    accept_follow_request,
    list_incoming_follow_requests,
    reject_follow_request,
    serialize_follow_request,
    set_account_privacy,
)


def _json_error(message: str, *, status: int = 400, **extra) -> JsonResponse:
    payload = {"ok": False, "error": message}
    payload.update(extra)
    return JsonResponse(payload, status=status)


def _parse_json(request: HttpRequest) -> dict:
    if not request.body:
        return {}
    try:
        data = json.loads(request.body.decode("utf-8"))
    except (TypeError, ValueError, UnicodeDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


@login_required
@require_GET
def api_v1_follow_requests(request: HttpRequest) -> JsonResponse:
    qs = list_incoming_follow_requests(request.user)
    return JsonResponse(
        {
            "ok": True,
            "requests": [serialize_follow_request(r) for r in qs],
        }
    )


@login_required
@require_POST
def api_v1_follow_request_accept(request: HttpRequest, pk: int) -> JsonResponse:
    try:
        payload = accept_follow_request(request.user, pk)
    except FollowForbidden as exc:
        return _json_error(exc.code, status=403)
    except ValueError as exc:
        code = str(exc)
        status = 404 if code == "not_found" else 400
        return _json_error(code, status=status)
    return JsonResponse(payload)


@login_required
@require_POST
def api_v1_follow_request_reject(request: HttpRequest, pk: int) -> JsonResponse:
    try:
        payload = reject_follow_request(request.user, pk)
    except ValueError as exc:
        code = str(exc)
        status = 404 if code == "not_found" else 400
        return _json_error(code, status=status)
    return JsonResponse(payload)


@login_required
@require_http_methods(["PATCH", "POST"])
def api_v1_me_privacy(request: HttpRequest) -> JsonResponse:
    """PATCH/POST /api/v1/me/privacy/  body: {"is_private": bool}."""
    data = _parse_json(request)
    if "is_private" not in data and request.method == "POST":
        # form-encoded fallback
        raw = request.POST.get("is_private")
        if raw is not None:
            data = {
                "is_private": str(raw).lower() in ("1", "true", "yes", "on")
            }
    if "is_private" not in data:
        return _json_error("is_private_required", status=400)
    value = data.get("is_private")
    if not isinstance(value, bool):
        if isinstance(value, (int, str)):
            value = str(value).lower() in ("1", "true", "yes", "on")
        else:
            return _json_error("invalid_is_private", status=400)
    payload = set_account_privacy(request.user, is_private=bool(value))
    return JsonResponse(payload)
