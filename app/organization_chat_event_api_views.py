"""JSON API for in-chat organization events (RSVP). Separate from public events."""

from __future__ import annotations

import json

from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_http_methods, require_POST

from .organization_api_services import get_organization_by_slug
from .organization_chat_event_services import (
    OrganizationChatEventError,
    cancel_organization_chat_event,
    create_organization_chat_event,
    get_organization_chat_event,
    list_organization_chat_events,
    rsvp_organization_chat_event,
    serialize_organization_chat_event,
    update_organization_chat_event,
)
from .organization_event_services import is_write_contention
from .organization_services import can_view_organization_profile
from .rate_limit_services import RATE_LIMIT_USER_MESSAGE, allow_organization_event_write


def _json_error(error: str, *, status: int = 400, **extra) -> JsonResponse:
    payload = {"ok": False, "error": error}
    payload.update(extra)
    return JsonResponse(payload, status=status)


def _parse_json(request: HttpRequest) -> dict:
    if request.content_type and "application/json" in request.content_type:
        try:
            data = json.loads(request.body.decode("utf-8") or "{}")
            return data if isinstance(data, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def _require_auth(request: HttpRequest) -> JsonResponse | None:
    if not request.user.is_authenticated:
        return _json_error(
            "unauthorized",
            status=401,
            message="authentication_required",
        )
    return None


def _error_response(exc: OrganizationChatEventError) -> JsonResponse:
    extra = dict(getattr(exc, "extra", None) or {})
    return _json_error(exc.code, status=exc.status, **extra)


def _write_allowed(request: HttpRequest) -> JsonResponse | None:
    if not allow_organization_event_write(request.user):
        return _json_error(
            "rate_limited",
            status=429,
            message=RATE_LIMIT_USER_MESSAGE,
        )
    return None


def _visible_organization(slug: str, viewer):
    organization = get_organization_by_slug(slug)
    if organization is None or not can_view_organization_profile(viewer, organization):
        return _json_error("not_found", status=404)
    return organization


def _chat_id(request: HttpRequest, payload: dict | None = None) -> int | None:
    raw = request.GET.get("chat") or request.GET.get("chat_id")
    if payload:
        raw = payload.get("chat_id") or payload.get("chat") or raw
    try:
        value = int(raw) if raw not in (None, "") else None
    except (TypeError, ValueError):
        return None
    return value if value and value > 0 else None


def _event_response(event, viewer, *, status: int = 200) -> JsonResponse:
    return JsonResponse(
        {
            "ok": True,
            "event": serialize_organization_chat_event(
                event, viewer, include_respondents=True
            ),
        },
        status=status,
    )


@require_http_methods(["GET", "POST"])
def api_v1_organization_chat_events(request: HttpRequest, slug: str) -> JsonResponse:
    auth_error = _require_auth(request)
    if auth_error:
        return auth_error
    organization = _visible_organization(slug, request.user)
    if isinstance(organization, JsonResponse):
        return organization
    if request.method == "GET":
        chat_id = _chat_id(request)
        try:
            payload = list_organization_chat_events(
                organization=organization,
                chat_id=chat_id or 0,
                viewer=request.user,
            )
        except OrganizationChatEventError as exc:
            return _error_response(exc)
        return JsonResponse(payload)

    limited = _write_allowed(request)
    if limited:
        return limited
    data = _parse_json(request)
    chat_id = _chat_id(request, data)
    try:
        event = create_organization_chat_event(
            organization=organization,
            actor=request.user,
            chat_id=chat_id or 0,
            payload=data,
        )
    except OrganizationChatEventError as exc:
        return _error_response(exc)
    except Exception as exc:
        if is_write_contention(exc):
            return _json_error("busy", status=409)
        raise
    return _event_response(event, request.user, status=201)


@require_http_methods(["GET", "PATCH"])
def api_v1_organization_chat_event_detail(
    request: HttpRequest, slug: str, event_id: int
) -> JsonResponse:
    auth_error = _require_auth(request)
    if auth_error:
        return auth_error
    organization = _visible_organization(slug, request.user)
    if isinstance(organization, JsonResponse):
        return organization
    chat_id = _chat_id(request, _parse_json(request) if request.method == "PATCH" else None)
    try:
        event = get_organization_chat_event(
            organization=organization,
            chat_id=chat_id or 0,
            event_id=event_id,
            viewer=request.user,
        )
    except OrganizationChatEventError as exc:
        return _error_response(exc)
    if request.method == "GET":
        return _event_response(event, request.user)
    limited = _write_allowed(request)
    if limited:
        return limited
    try:
        updated = update_organization_chat_event(
            event=event, actor=request.user, payload=_parse_json(request)
        )
    except OrganizationChatEventError as exc:
        return _error_response(exc)
    except Exception as exc:
        if is_write_contention(exc):
            return _json_error("busy", status=409)
        raise
    return _event_response(updated, request.user)


@require_POST
def api_v1_organization_chat_event_rsvp(
    request: HttpRequest, slug: str, event_id: int
) -> JsonResponse:
    auth_error = _require_auth(request)
    if auth_error:
        return auth_error
    limited = _write_allowed(request)
    if limited:
        return limited
    organization = _visible_organization(slug, request.user)
    if isinstance(organization, JsonResponse):
        return organization
    data = _parse_json(request)
    chat_id = _chat_id(request, data)
    try:
        event = get_organization_chat_event(
            organization=organization,
            chat_id=chat_id or 0,
            event_id=event_id,
            viewer=request.user,
        )
        rsvp_organization_chat_event(
            event=event, user=request.user, answer=str(data.get("answer") or "")
        )
        event = get_organization_chat_event(
            organization=organization,
            chat_id=chat_id or 0,
            event_id=event_id,
            viewer=request.user,
        )
    except OrganizationChatEventError as exc:
        return _error_response(exc)
    except Exception as exc:
        if is_write_contention(exc):
            return _json_error("busy", status=409)
        raise
    return _event_response(event, request.user)


@require_POST
def api_v1_organization_chat_event_cancel(
    request: HttpRequest, slug: str, event_id: int
) -> JsonResponse:
    auth_error = _require_auth(request)
    if auth_error:
        return auth_error
    limited = _write_allowed(request)
    if limited:
        return limited
    organization = _visible_organization(slug, request.user)
    if isinstance(organization, JsonResponse):
        return organization
    data = _parse_json(request)
    chat_id = _chat_id(request, data)
    try:
        event = get_organization_chat_event(
            organization=organization,
            chat_id=chat_id or 0,
            event_id=event_id,
            viewer=request.user,
        )
        event = cancel_organization_chat_event(event=event, actor=request.user)
    except OrganizationChatEventError as exc:
        return _error_response(exc)
    except Exception as exc:
        if is_write_contention(exc):
            return _json_error("busy", status=409)
        raise
    return _event_response(event, request.user)
