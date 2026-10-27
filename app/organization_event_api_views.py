"""JSON API for organization recruiting events (Phase 4)."""

from __future__ import annotations

import json

from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from .organization_api_services import get_organization_by_slug
from .organization_event_lottery_services import (
    get_organization_event_lottery_payload,
    run_organization_event_lottery,
    serialize_organization_event_lottery,
    share_organization_event_lottery,
)
from .organization_event_services import (
    OrganizationEventError,
    cancel_organization_event,
    create_organization_event,
    delete_organization_event,
    get_event_for_organization,
    get_organization_event_payload,
    is_write_contention,
    list_event_registrations_payload,
    list_my_event_registrations_payload,
    list_organization_events_payload,
    publish_organization_event,
    register_organization_event,
    serialize_organization_event,
    share_organization_event_to_chat,
    unpublish_organization_event,
    unregister_organization_event,
    update_organization_event,
    duplicate_organization_event,
)
from .organization_services import can_manage_organization, can_view_organization_profile
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


def _viewer(request: HttpRequest):
    return request.user if request.user.is_authenticated else None


def _require_auth(request: HttpRequest) -> JsonResponse | None:
    if not request.user.is_authenticated:
        return _json_error(
            "unauthorized",
            status=401,
            message="authentication_required",
        )
    return None


def _error_response(exc: OrganizationEventError) -> JsonResponse:
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


def _event_response(event, viewer, *, status: int = 200) -> JsonResponse:
    return JsonResponse(
        {"ok": True, "event": serialize_organization_event(event, viewer)},
        status=status,
    )


@require_http_methods(["GET", "POST"])
def api_v1_organization_events(request: HttpRequest, slug: str) -> JsonResponse:
    if request.method == "GET":
        organization = _visible_organization(slug, _viewer(request))
        if isinstance(organization, JsonResponse):
            return organization
        manage = str(request.GET.get("manage") or "").strip().lower() in {
            "1",
            "true",
            "yes",
        }
        try:
            payload = list_organization_events_payload(
                organization,
                _viewer(request),
                offset=request.GET.get("offset"),
                limit=request.GET.get("limit"),
                manage=manage,
            )
        except OrganizationEventError as exc:
            return _error_response(exc)
        return JsonResponse(payload)

    auth_error = _require_auth(request)
    if auth_error:
        return auth_error
    limited = _write_allowed(request)
    if limited:
        return limited
    organization = _visible_organization(slug, request.user)
    if isinstance(organization, JsonResponse):
        return organization
    try:
        event = create_organization_event(
            organization=organization,
            actor=request.user,
            payload=_parse_json(request),
        )
    except OrganizationEventError as exc:
        return _error_response(exc)
    except Exception as exc:
        if is_write_contention(exc):
            return _json_error("busy", status=409)
        raise
    return _event_response(event, request.user, status=201)


@require_http_methods(["GET", "PATCH"])
def api_v1_organization_event_detail(
    request: HttpRequest, slug: str, event_id: int
) -> JsonResponse:
    organization = _visible_organization(slug, _viewer(request))
    if isinstance(organization, JsonResponse):
        return organization
    if request.method == "GET":
        try:
            payload = get_organization_event_payload(
                organization, event_id, _viewer(request)
            )
        except OrganizationEventError as exc:
            return _error_response(exc)
        return JsonResponse(payload)

    auth_error = _require_auth(request)
    if auth_error:
        return auth_error
    limited = _write_allowed(request)
    if limited:
        return limited
    event = get_event_for_organization(organization, event_id)
    if event is None:
        return _json_error("not_found", status=404)
    try:
        updated = update_organization_event(
            event=event, actor=request.user, payload=_parse_json(request)
        )
    except OrganizationEventError as exc:
        return _error_response(exc)
    except Exception as exc:
        if is_write_contention(exc):
            return _json_error("busy", status=409)
        raise
    return _event_response(updated, request.user)


def _event_action(
    request: HttpRequest, slug: str, event_id: int, handler
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
    event = get_event_for_organization(organization, event_id)
    if event is None:
        return _json_error("not_found", status=404)
    try:
        result = handler(event=event, actor=request.user)
    except OrganizationEventError as exc:
        return _error_response(exc)
    except Exception as exc:
        if is_write_contention(exc):
            return _json_error("busy", status=409)
        raise
    if result is None:
        return JsonResponse({"ok": True})
    return _event_response(result, request.user)


@require_POST
def api_v1_organization_event_publish(
    request: HttpRequest, slug: str, event_id: int
) -> JsonResponse:
    return _event_action(request, slug, event_id, publish_organization_event)


@require_POST
def api_v1_organization_event_unpublish(
    request: HttpRequest, slug: str, event_id: int
) -> JsonResponse:
    return _event_action(request, slug, event_id, unpublish_organization_event)


@require_POST
def api_v1_organization_event_cancel(
    request: HttpRequest, slug: str, event_id: int
) -> JsonResponse:
    return _event_action(request, slug, event_id, cancel_organization_event)


@require_POST
def api_v1_organization_event_delete(
    request: HttpRequest, slug: str, event_id: int
) -> JsonResponse:
    return _event_action(request, slug, event_id, delete_organization_event)


@require_POST
def api_v1_organization_event_register(
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
    event = get_event_for_organization(organization, event_id)
    if event is None:
        return _json_error("not_found", status=404)
    try:
        register_organization_event(event=event, user=request.user)
        payload = get_organization_event_payload(organization, event_id, request.user)
    except OrganizationEventError as exc:
        return _error_response(exc)
    except Exception as exc:
        if is_write_contention(exc):
            return _json_error("busy", status=409)
        raise
    return JsonResponse(payload)


@require_POST
def api_v1_organization_event_unregister(
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
    event = get_event_for_organization(organization, event_id)
    if event is None:
        return _json_error("not_found", status=404)
    try:
        unregister_organization_event(event=event, user=request.user)
        payload = get_organization_event_payload(organization, event_id, request.user)
    except OrganizationEventError as exc:
        return _error_response(exc)
    except Exception as exc:
        if is_write_contention(exc):
            return _json_error("busy", status=409)
        raise
    return JsonResponse(payload)


@require_GET
def api_v1_organization_event_registrations(
    request: HttpRequest, slug: str, event_id: int
) -> JsonResponse:
    auth_error = _require_auth(request)
    if auth_error:
        return auth_error
    organization = _visible_organization(slug, request.user)
    if isinstance(organization, JsonResponse):
        return organization
    if not can_manage_organization(request.user, organization):
        return _json_error("forbidden", status=403)
    event = get_event_for_organization(organization, event_id)
    if event is None:
        return _json_error("not_found", status=404)
    try:
        payload = list_event_registrations_payload(
            event=event,
            actor=request.user,
            offset=request.GET.get("offset"),
            limit=request.GET.get("limit"),
        )
    except OrganizationEventError as exc:
        return _error_response(exc)
    return JsonResponse(payload)


def _lottery_response(lottery, viewer, *, status: int = 200) -> JsonResponse:
    event = lottery.event
    return JsonResponse(
        {
            "ok": True,
            "event": serialize_organization_event(
                event, viewer, lottery=lottery, lottery_loaded=True
            ),
            "lottery": serialize_organization_event_lottery(lottery, viewer),
        },
        status=status,
    )


@require_http_methods(["GET", "POST"])
def api_v1_organization_event_lottery(
    request: HttpRequest, slug: str, event_id: int
) -> JsonResponse:
    if request.method == "GET":
        auth_error = _require_auth(request)
        if auth_error:
            return auth_error
        organization = _visible_organization(slug, request.user)
        if isinstance(organization, JsonResponse):
            return organization
        try:
            payload = get_organization_event_lottery_payload(
                organization, event_id, request.user
            )
        except OrganizationEventError as exc:
            return _error_response(exc)
        return JsonResponse(payload)

    auth_error = _require_auth(request)
    if auth_error:
        return auth_error
    limited = _write_allowed(request)
    if limited:
        return limited
    organization = _visible_organization(slug, request.user)
    if isinstance(organization, JsonResponse):
        return organization
    event = get_event_for_organization(organization, event_id)
    if event is None:
        return _json_error("not_found", status=404)
    try:
        lottery = run_organization_event_lottery(
            event=event, actor=request.user, payload=_parse_json(request)
        )
    except OrganizationEventError as exc:
        return _error_response(exc)
    except Exception as exc:
        if is_write_contention(exc):
            return _json_error("busy", status=409)
        raise
    return _lottery_response(lottery, request.user, status=201)


@require_POST
def api_v1_organization_event_lottery_share(
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
    event = get_event_for_organization(organization, event_id)
    if event is None:
        return _json_error("not_found", status=404)
    try:
        data = _parse_json(request)
        chat_id = data.get("chat_id") or data.get("chat")
        try:
            chat_id = int(chat_id) if chat_id not in (None, "") else None
        except (TypeError, ValueError):
            chat_id = None
        lottery = share_organization_event_lottery(
            event=event, actor=request.user, chat_id=chat_id
        )
    except OrganizationEventError as exc:
        return _error_response(exc)
    except Exception as exc:
        if is_write_contention(exc):
            return _json_error("busy", status=409)
        raise
    return _lottery_response(lottery, request.user)


@require_POST
def api_v1_organization_event_share(
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
    event = get_event_for_organization(organization, event_id)
    if event is None:
        return _json_error("not_found", status=404)
    data = _parse_json(request)
    try:
        chat_id = int(data.get("chat_id") or data.get("chat") or 0)
    except (TypeError, ValueError):
        chat_id = 0
    if chat_id <= 0:
        return _json_error("chat_id_required", status=400)
    try:
        share = share_organization_event_to_chat(
            event=event, actor=request.user, chat_id=chat_id
        )
    except OrganizationEventError as exc:
        return _error_response(exc)
    except Exception as exc:
        if is_write_contention(exc):
            return _json_error("busy", status=409)
        raise
    return JsonResponse(
        {
            "ok": True,
            "shared": True,
            "chat_id": share.recruiting_chat_id,
            "message_id": share.message_id,
            "event": serialize_organization_event(event, request.user),
        },
        status=201,
    )


@require_POST
def api_v1_organization_event_duplicate(
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
    event = get_event_for_organization(organization, event_id)
    if event is None:
        return _json_error("not_found", status=404)
    data = _parse_json(request)
    try:
        copy = duplicate_organization_event(
            event=event, actor=request.user, payload=data or None
        )
    except OrganizationEventError as exc:
        return _error_response(exc)
    return JsonResponse(
        {
            "ok": True,
            "event": serialize_organization_event(copy, request.user),
        },
        status=201,
    )


@require_GET
def api_v1_me_event_registrations(request: HttpRequest) -> JsonResponse:
    auth_error = _require_auth(request)
    if auth_error:
        return auth_error
    try:
        payload = list_my_event_registrations_payload(
            request.user,
            offset=request.GET.get("offset"),
            limit=request.GET.get("limit"),
        )
    except OrganizationEventError as exc:
        return _error_response(exc)
    return JsonResponse(payload)
