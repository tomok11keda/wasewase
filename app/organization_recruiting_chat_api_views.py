"""JSON API for organization recruiting chats (Phase 3-B)."""

from __future__ import annotations

import json

from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from .chat_message_services import serialize_chat_message, soft_delete_own_chat_message
from .models import ChatMessage, Organization
from .organization_api_services import get_organization_by_slug
from .organization_recruiting_chat_services import (
    OrganizationRecruitingChatError,
    approve_recruiting_application,
    build_recruiting_messages_payload,
    build_recruiting_room_payload,
    can_access_recruiting_room,
    can_discover_recruiting_chat,
    create_recruiting_chat,
    get_accessible_recruiting_room,
    get_active_recruiting_chat,
    join_or_apply_recruiting_chat,
    leave_recruiting_chat,
    list_recruiting_applications,
    list_recruiting_participants,
    reject_recruiting_application,
    remove_recruiting_participant,
    send_recruiting_chat_message,
    serialize_recruiting_chat_for_viewer,
    update_recruiting_chat_settings,
    withdraw_recruiting_application,
)
from .organization_services import (
    can_manage_organization,
    can_view_organization_profile,
)
from .rate_limit_services import (
    RATE_LIMIT_USER_MESSAGE,
    allow_chat_message,
    allow_organization_recruiting_chat_write,
)


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


def _error_response(exc: OrganizationRecruitingChatError) -> JsonResponse:
    extra = dict(getattr(exc, "extra", None) or {})
    return _json_error(exc.code, status=exc.status, **extra)


def _visible_organization(slug: str, viewer) -> Organization | JsonResponse:
    organization = get_organization_by_slug(slug)
    if organization is None or not can_view_organization_profile(viewer, organization):
        return _json_error("not_found", status=404)
    return organization


def _managed_organization(request: HttpRequest, slug: str) -> Organization | JsonResponse:
    auth_error = _require_auth(request)
    if auth_error:
        return auth_error
    organization = get_organization_by_slug(slug)
    if organization is None or not can_view_organization_profile(
        request.user, organization
    ):
        return _json_error("not_found", status=404)
    if not can_manage_organization(request.user, organization):
        return _json_error("forbidden", status=403)
    return organization


def _managed_chat(request: HttpRequest, slug: str):
    organization = _managed_organization(request, slug)
    if isinstance(organization, JsonResponse):
        return organization
    chat = get_active_recruiting_chat(organization)
    if chat is None:
        return _json_error("not_found", status=404)
    return organization, chat


def _write_allowed(request: HttpRequest) -> JsonResponse | None:
    if not allow_organization_recruiting_chat_write(request.user):
        return _json_error(
            "rate_limited",
            status=429,
            message=RATE_LIMIT_USER_MESSAGE,
        )
    return None


def _truthy(value) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


@require_http_methods(["GET", "POST", "PATCH"])
def api_v1_organization_recruiting_chat(
    request: HttpRequest, slug: str
) -> JsonResponse:
    if request.method == "GET":
        return _get_recruiting_chat(request, slug)
    if request.method == "POST":
        return _create_recruiting_chat(request, slug)
    return _patch_recruiting_chat(request, slug)


def _get_recruiting_chat(request: HttpRequest, slug: str) -> JsonResponse:
    organization = _visible_organization(slug, _viewer(request))
    if isinstance(organization, JsonResponse):
        return organization
    viewer = _viewer(request)
    chat = get_active_recruiting_chat(organization)
    can_manage = can_manage_organization(viewer, organization)
    if chat is None:
        return JsonResponse(
            {
                "ok": True,
                "recruiting_chat": None,
                "can_create": can_manage,
                "can_manage": can_manage,
            }
        )
    can_access = can_access_recruiting_room(chat.room, viewer)
    discoverable = can_discover_recruiting_chat(viewer, chat)
    payload = serialize_recruiting_chat_for_viewer(
        chat, viewer, include_manager_fields=can_manage
    )
    if not (can_manage or can_access or discoverable):
        return JsonResponse(
            {
                "ok": True,
                "recruiting_chat": {
                    "membership_status": payload["membership_status"],
                    "join_mode": payload["join_mode"],
                    "listing_status": payload["listing_status"],
                    "can_join": False,
                    "can_apply": False,
                    "can_manage": False,
                    "room_id": None,
                },
                "can_create": False,
                "can_manage": False,
            }
        )
    return JsonResponse(
        {
            "ok": True,
            "recruiting_chat": payload,
            "can_create": False,
            "can_manage": can_manage,
        }
    )


def _create_recruiting_chat(request: HttpRequest, slug: str) -> JsonResponse:
    organization = _managed_organization(request, slug)
    if isinstance(organization, JsonResponse):
        return organization
    limited = _write_allowed(request)
    if limited:
        return limited
    data = _parse_json(request)
    try:
        chat = create_recruiting_chat(
            organization=organization,
            actor=request.user,
            name=str(data.get("name") or ""),
            description=str(data.get("description") or ""),
            join_mode=str(
                data.get("join_mode") or "open"
            ),
            listing_status=str(data.get("listing_status") or "open"),
        )
    except OrganizationRecruitingChatError as exc:
        return _error_response(exc)
    return JsonResponse(
        {
            "ok": True,
            "created": True,
            "recruiting_chat": serialize_recruiting_chat_for_viewer(
                chat, request.user, include_manager_fields=True
            ),
        },
        status=201,
    )


def _patch_recruiting_chat(request: HttpRequest, slug: str) -> JsonResponse:
    result = _managed_chat(request, slug)
    if isinstance(result, JsonResponse):
        return result
    _organization, chat = result
    limited = _write_allowed(request)
    if limited:
        return limited
    data = _parse_json(request)
    kwargs = {"chat": chat, "actor": request.user}
    if "name" in data:
        kwargs["name"] = str(data.get("name") or "")
    if "description" in data:
        kwargs["description"] = str(data.get("description") or "")
    if "join_mode" in data:
        kwargs["join_mode"] = str(data.get("join_mode") or "")
    if "listing_status" in data:
        kwargs["listing_status"] = str(data.get("listing_status") or "")
    kwargs["confirm_auto_approve"] = _truthy(
        data.get("confirm_auto_approve")
    )
    try:
        chat, stats = update_recruiting_chat_settings(**kwargs)
    except OrganizationRecruitingChatError as exc:
        return _error_response(exc)
    payload = serialize_recruiting_chat_for_viewer(
        chat, request.user, include_manager_fields=True
    )
    payload.update(stats)
    return JsonResponse({"ok": True, "recruiting_chat": payload, **stats})


@require_POST
def api_v1_organization_recruiting_chat_join(
    request: HttpRequest, slug: str
) -> JsonResponse:
    auth_error = _require_auth(request)
    if auth_error:
        return auth_error
    organization = _visible_organization(slug, request.user)
    if isinstance(organization, JsonResponse):
        return organization
    limited = _write_allowed(request)
    if limited:
        return limited
    chat = get_active_recruiting_chat(organization)
    if chat is None:
        return _json_error("not_found", status=404)
    try:
        application = join_or_apply_recruiting_chat(chat=chat, user=request.user)
    except OrganizationRecruitingChatError as exc:
        return _error_response(exc)
    payload = serialize_recruiting_chat_for_viewer(chat, request.user)
    return JsonResponse(
        {
            "ok": True,
            "application_id": application.pk,
            "application_status": application.status,
            "recruiting_chat": payload,
        },
        status=201,
    )


@require_POST
def api_v1_organization_recruiting_chat_leave(
    request: HttpRequest, slug: str
) -> JsonResponse:
    auth_error = _require_auth(request)
    if auth_error:
        return auth_error
    organization = _visible_organization(slug, request.user)
    if isinstance(organization, JsonResponse):
        return organization
    limited = _write_allowed(request)
    if limited:
        return limited
    chat = get_active_recruiting_chat(organization)
    if chat is None:
        return _json_error("not_found", status=404)
    try:
        leave_recruiting_chat(chat=chat, user=request.user)
    except OrganizationRecruitingChatError as exc:
        return _error_response(exc)
    return JsonResponse(
        {
            "ok": True,
            "left": True,
            "recruiting_chat": serialize_recruiting_chat_for_viewer(chat, request.user),
        }
    )


@require_POST
def api_v1_organization_recruiting_chat_withdraw(
    request: HttpRequest, slug: str
) -> JsonResponse:
    auth_error = _require_auth(request)
    if auth_error:
        return auth_error
    organization = _visible_organization(slug, request.user)
    if isinstance(organization, JsonResponse):
        return organization
    limited = _write_allowed(request)
    if limited:
        return limited
    chat = get_active_recruiting_chat(organization)
    if chat is None:
        return _json_error("not_found", status=404)
    try:
        application = withdraw_recruiting_application(chat=chat, user=request.user)
    except OrganizationRecruitingChatError as exc:
        return _error_response(exc)
    return JsonResponse(
        {
            "ok": True,
            "withdrawn": True,
            "application_status": application.status,
            "recruiting_chat": serialize_recruiting_chat_for_viewer(chat, request.user),
        }
    )


@require_GET
def api_v1_organization_recruiting_chat_applications(
    request: HttpRequest, slug: str
) -> JsonResponse:
    result = _managed_chat(request, slug)
    if isinstance(result, JsonResponse):
        return result
    _organization, chat = result
    try:
        rows = list_recruiting_applications(chat=chat, actor=request.user)
    except OrganizationRecruitingChatError as exc:
        return _error_response(exc)
    status_filter = (request.GET.get("status") or "").strip()
    if status_filter:
        rows = [row for row in rows if row.get("status") == status_filter]
    return JsonResponse(
        {
            "ok": True,
            "applications": rows,
            "pending_count": sum(1 for row in rows if row.get("status") == "pending"),
        }
    )


@require_POST
def api_v1_organization_recruiting_chat_approve(
    request: HttpRequest, slug: str, application_id: int
) -> JsonResponse:
    result = _managed_chat(request, slug)
    if isinstance(result, JsonResponse):
        return result
    _organization, chat = result
    limited = _write_allowed(request)
    if limited:
        return limited
    try:
        application = approve_recruiting_application(
            chat=chat, application_id=application_id, actor=request.user
        )
    except OrganizationRecruitingChatError as exc:
        return _error_response(exc)
    return JsonResponse(
        {
            "ok": True,
            "application_id": application.pk,
            "application_status": application.status,
            "recruiting_chat": serialize_recruiting_chat_for_viewer(
                chat, request.user, include_manager_fields=True
            ),
        }
    )


@require_POST
def api_v1_organization_recruiting_chat_reject(
    request: HttpRequest, slug: str, application_id: int
) -> JsonResponse:
    result = _managed_chat(request, slug)
    if isinstance(result, JsonResponse):
        return result
    _organization, chat = result
    limited = _write_allowed(request)
    if limited:
        return limited
    try:
        application = reject_recruiting_application(
            chat=chat, application_id=application_id, actor=request.user
        )
    except OrganizationRecruitingChatError as exc:
        return _error_response(exc)
    return JsonResponse(
        {
            "ok": True,
            "application_id": application.pk,
            "application_status": application.status,
            "recruiting_chat": serialize_recruiting_chat_for_viewer(
                chat, request.user, include_manager_fields=True
            ),
        }
    )


@require_GET
def api_v1_organization_recruiting_chat_members(
    request: HttpRequest, slug: str
) -> JsonResponse:
    auth_error = _require_auth(request)
    if auth_error:
        return auth_error
    organization = _visible_organization(slug, request.user)
    if isinstance(organization, JsonResponse):
        return organization
    chat = get_active_recruiting_chat(organization)
    if chat is None:
        return _json_error("not_found", status=404)
    try:
        members = list_recruiting_participants(chat=chat, viewer=request.user)
    except OrganizationRecruitingChatError as exc:
        return _error_response(exc)
    return JsonResponse({"ok": True, "members": members})


@require_POST
def api_v1_organization_recruiting_chat_remove_member(
    request: HttpRequest, slug: str, user_id: int
) -> JsonResponse:
    result = _managed_chat(request, slug)
    if isinstance(result, JsonResponse):
        return result
    _organization, chat = result
    limited = _write_allowed(request)
    if limited:
        return limited
    try:
        remove_recruiting_participant(
            chat=chat, actor=request.user, user_id=user_id
        )
    except OrganizationRecruitingChatError as exc:
        return _error_response(exc)
    return JsonResponse({"ok": True, "removed_user_id": user_id})


@require_GET
def api_v1_recruiting_chat_room(request: HttpRequest, room_pk: int) -> JsonResponse:
    auth_error = _require_auth(request)
    if auth_error:
        return auth_error
    try:
        room = get_accessible_recruiting_room(room_pk, request.user)
        return JsonResponse(build_recruiting_room_payload(room, request.user))
    except OrganizationRecruitingChatError as exc:
        return _error_response(exc)


@require_GET
def api_v1_recruiting_chat_messages(
    request: HttpRequest, room_pk: int
) -> JsonResponse:
    auth_error = _require_auth(request)
    if auth_error:
        return auth_error
    try:
        room = get_accessible_recruiting_room(room_pk, request.user)
        return JsonResponse(
            build_recruiting_messages_payload(
                room,
                request.user,
                after=request.GET.get("after", ""),
                before=request.GET.get("before", ""),
            )
        )
    except OrganizationRecruitingChatError as exc:
        return _error_response(exc)


@require_POST
def api_v1_recruiting_chat_send(request: HttpRequest, room_pk: int) -> JsonResponse:
    auth_error = _require_auth(request)
    if auth_error:
        return auth_error
    if not allow_chat_message(request.user):
        return _json_error(
            "rate_limited",
            status=429,
            message=RATE_LIMIT_USER_MESSAGE,
        )
    data = _parse_json(request)
    body = str(data.get("body") if data else request.POST.get("body", ""))
    reply_raw = data.get("reply_to_id") if data else None
    try:
        reply_to_id = int(reply_raw) if reply_raw not in (None, "") else None
    except (TypeError, ValueError):
        return _json_error("invalid_reply_to")
    try:
        room = get_accessible_recruiting_room(room_pk, request.user)
        message = send_recruiting_chat_message(
            room, request.user, body, reply_to_id=reply_to_id
        )
    except OrganizationRecruitingChatError as exc:
        return _error_response(exc)
    except ValueError as exc:
        code = str(exc)
        status = 403 if code == "forbidden" else 400
        return _json_error(code, status=status)
    return JsonResponse(
        {
            "ok": True,
            "message": serialize_chat_message(message, request.user.pk),
        },
        status=201,
    )


@require_POST
def api_v1_recruiting_chat_message_delete(
    request: HttpRequest, room_pk: int, message_pk: int
) -> JsonResponse:
    auth_error = _require_auth(request)
    if auth_error:
        return auth_error
    try:
        room = get_accessible_recruiting_room(room_pk, request.user)
    except OrganizationRecruitingChatError as exc:
        return _error_response(exc)
    try:
        message = ChatMessage.objects.select_related(
            "sender", "sender__profile", "reply_to", "reply_to__sender"
        ).get(pk=message_pk, room=room)
    except ChatMessage.DoesNotExist:
        return _json_error("not_found", status=404)
    try:
        message = soft_delete_own_chat_message(message, request.user)
    except ValueError as exc:
        code = str(exc)
        status = 403 if code == "forbidden" else 400
        return _json_error(code, status=status)
    return JsonResponse(
        {
            "ok": True,
            "message": serialize_chat_message(message, request.user.pk),
        }
    )
