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
    can_see_recruiting_chat,
    count_active_organization_chats,
    create_recruiting_chat,
    deactivate_recruiting_chat,
    get_accessible_recruiting_room,
    get_active_recruiting_chat,
    get_organization_chat,
    join_or_apply_recruiting_chat,
    leave_recruiting_chat,
    list_recruiting_applications,
    list_recruiting_participants,
    list_visible_organization_chats,
    max_active_organization_chats,
    pin_recruiting_message,
    reject_recruiting_application,
    remove_recruiting_participant,
    send_recruiting_chat_message,
    serialize_recruiting_chat_for_viewer,
    update_recruiting_chat_settings,
    withdraw_recruiting_application,
)
from .organization_recruiting_invite_services import (
    CANDIDATE_QUERY_MIN,
    accept_recruiting_invitation,
    cancel_recruiting_invitation,
    create_recruiting_invitations,
    decline_recruiting_invitation,
    get_recruiting_invitation_for_invitee,
    list_pending_recruiting_invites,
    list_recruiting_invite_candidates,
    serialize_recruiting_invitation,
    viewer_recruiting_invitation_payload,
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


def _chat_id_from_request(request: HttpRequest, data: dict | None = None) -> int | None:
    raw = request.GET.get("chat") or request.GET.get("chat_id")
    if raw in (None, "") and data:
        raw = data.get("chat") if data.get("chat") is not None else data.get("chat_id")
    if raw in (None, ""):
        return None
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def _resolve_chat(organization, chat_id: int | None, *, required_if_many: bool = False):
    if chat_id:
        chat = get_organization_chat(organization, chat_id)
        if chat is None:
            return None
        return chat
    chats = list(
        organization.recruiting_chats.filter(is_active=True).order_by("pk")
        if hasattr(organization, "recruiting_chats")
        else []
    )
    if not chats:
        chat = get_active_recruiting_chat(organization)
        return chat
    if required_if_many and len(chats) > 1:
        return "many"
    return chats[0]


def _managed_chat(request: HttpRequest, slug: str, data: dict | None = None):
    organization = _managed_organization(request, slug)
    if isinstance(organization, JsonResponse):
        return organization
    chat_id = _chat_id_from_request(request, data)
    chat = _resolve_chat(organization, chat_id, required_if_many=True)
    if chat == "many":
        return _json_error("chat_id_required", status=409)
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


def _chat_list_payload(organization, viewer, *, can_manage: bool) -> dict:
    chats = list_visible_organization_chats(organization, viewer)
    serialized = [
        serialize_recruiting_chat_for_viewer(
            chat, viewer, include_manager_fields=can_manage
        )
        for chat in chats
    ]
    active_count = count_active_organization_chats(organization)
    limit = max_active_organization_chats()
    return {
        "ok": True,
        "recruiting_chats": serialized,
        "recruiting_chat": serialized[0] if serialized else None,
        "can_create": bool(can_manage and active_count < limit),
        "can_manage": can_manage,
        "chat_count": active_count,
        "chat_max": limit,
    }


def _get_recruiting_chat(request: HttpRequest, slug: str) -> JsonResponse:
    organization = get_organization_by_slug(slug)
    if organization is None:
        return _json_error("not_found", status=404)
    viewer = _viewer(request)
    visible = can_view_organization_profile(viewer, organization)
    can_manage = can_manage_organization(viewer, organization)
    if not visible and not can_manage:
        if not list_visible_organization_chats(organization, viewer):
            return _json_error("not_found", status=404)
    chat_id = _chat_id_from_request(request)
    if chat_id:
        chat = get_organization_chat(organization, chat_id)
        if chat is None or not can_see_recruiting_chat(viewer, chat):
            return _json_error("not_found", status=404)
        payload = serialize_recruiting_chat_for_viewer(
            chat, viewer, include_manager_fields=can_manage
        )
        active_count = count_active_organization_chats(organization)
        limit = max_active_organization_chats()
        return JsonResponse(
            {
                "ok": True,
                "recruiting_chat": payload,
                "recruiting_chats": [payload],
                "can_create": bool(can_manage and active_count < limit),
                "can_manage": can_manage,
                "chat_count": active_count,
                "chat_max": limit,
            }
        )
    return JsonResponse(_chat_list_payload(organization, viewer, can_manage=can_manage))


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
            join_mode=str(data.get("join_mode") or "open"),
            listing_status=str(data.get("listing_status") or "open"),
            visibility=str(data.get("visibility") or "public"),
            posting_mode=str(data.get("posting_mode") or "all"),
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
    data = _parse_json(request)
    result = _managed_chat(request, slug, data)
    if isinstance(result, JsonResponse):
        return result
    _organization, chat = result
    limited = _write_allowed(request)
    if limited:
        return limited
    if "is_active" in data and not _truthy(data.get("is_active")):
        try:
            chat = deactivate_recruiting_chat(chat=chat, actor=request.user)
        except OrganizationRecruitingChatError as exc:
            return _error_response(exc)
        return JsonResponse(
            {
                "ok": True,
                "archived": True,
                "recruiting_chat": serialize_recruiting_chat_for_viewer(
                    chat, request.user, include_manager_fields=True
                ),
            }
        )
    if "pinned_message_id" in data:
        try:
            chat = pin_recruiting_message(
                chat=chat,
                actor=request.user,
                message_id=data.get("pinned_message_id"),
            )
        except OrganizationRecruitingChatError as exc:
            return _error_response(exc)
        return JsonResponse(
            {
                "ok": True,
                "recruiting_chat": serialize_recruiting_chat_for_viewer(
                    chat, request.user, include_manager_fields=True
                ),
            }
        )
    kwargs = {"chat": chat, "actor": request.user}
    if "name" in data:
        kwargs["name"] = str(data.get("name") or "")
    if "description" in data:
        kwargs["description"] = str(data.get("description") or "")
    if "join_mode" in data:
        kwargs["join_mode"] = str(data.get("join_mode") or "")
    if "listing_status" in data:
        kwargs["listing_status"] = str(data.get("listing_status") or "")
    if "visibility" in data:
        kwargs["visibility"] = str(data.get("visibility") or "")
    if "posting_mode" in data:
        kwargs["posting_mode"] = str(data.get("posting_mode") or "")
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
    data = _parse_json(request)
    chat = _resolve_chat(
        organization, _chat_id_from_request(request, data), required_if_many=True
    )
    if chat is None or chat == "many":
        return _json_error(
            "chat_id_required" if chat == "many" else "not_found",
            status=409 if chat == "many" else 404,
        )
    if not can_see_recruiting_chat(request.user, chat) and not can_discover_recruiting_chat(
        request.user, chat
    ):
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
    data = _parse_json(request)
    chat = _resolve_chat(
        organization, _chat_id_from_request(request, data), required_if_many=True
    )
    if chat is None or chat == "many":
        return _json_error(
            "chat_id_required" if chat == "many" else "not_found",
            status=409 if chat == "many" else 404,
        )
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
    data = _parse_json(request)
    chat = _resolve_chat(
        organization, _chat_id_from_request(request, data), required_if_many=True
    )
    if chat is None or chat == "many":
        return _json_error(
            "chat_id_required" if chat == "many" else "not_found",
            status=409 if chat == "many" else 404,
        )
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


def _parse_invitee_ids(data: dict) -> list[int]:
    raw = data.get("invitee_ids")
    if not isinstance(raw, list):
        return []
    ids: list[int] = []
    for value in raw:
        try:
            ids.append(int(value))
        except (TypeError, ValueError):
            continue
    return ids


@require_GET
def api_v1_organization_recruiting_invite_candidates(
    request: HttpRequest, slug: str
) -> JsonResponse:
    result = _managed_chat(request, slug)
    if isinstance(result, JsonResponse):
        return result
    _organization, chat = result
    query = (request.GET.get("q") or "").strip()
    if query and len(query.lstrip("@")) < CANDIDATE_QUERY_MIN:
        return JsonResponse({"ok": True, "users": [], "query": query})
    try:
        users = list_recruiting_invite_candidates(
            chat=chat, actor=request.user, query=query
        )
    except OrganizationRecruitingChatError as exc:
        return _error_response(exc)
    return JsonResponse({"ok": True, "users": users, "query": query})


@require_http_methods(["GET", "POST"])
def api_v1_organization_recruiting_invites(
    request: HttpRequest, slug: str
) -> JsonResponse:
    result = _managed_chat(request, slug)
    if isinstance(result, JsonResponse):
        return result
    _organization, chat = result
    if request.method == "GET":
        try:
            invites = list_pending_recruiting_invites(chat=chat, actor=request.user)
        except OrganizationRecruitingChatError as exc:
            return _error_response(exc)
        return JsonResponse({"ok": True, "invites": invites})
    limited = _write_allowed(request)
    if limited:
        return limited
    data = _parse_json(request)
    try:
        payload = create_recruiting_invitations(
            chat=chat,
            actor=request.user,
            invitee_ids=_parse_invitee_ids(data),
        )
    except OrganizationRecruitingChatError as exc:
        return _error_response(exc)
    return JsonResponse({"ok": True, **payload}, status=201)


@require_POST
def api_v1_organization_recruiting_invite_cancel(
    request: HttpRequest, slug: str, invitation_id: int
) -> JsonResponse:
    result = _managed_chat(request, slug)
    if isinstance(result, JsonResponse):
        return result
    _organization, chat = result
    limited = _write_allowed(request)
    if limited:
        return limited
    try:
        invitation = cancel_recruiting_invitation(
            chat=chat, actor=request.user, invitation_id=invitation_id
        )
    except OrganizationRecruitingChatError as exc:
        return _error_response(exc)
    return JsonResponse(
        {
            "ok": True,
            "invitation": serialize_recruiting_invitation(
                invitation, include_invitee=True
            ),
        }
    )


@require_GET
def api_v1_organization_recruiting_invitation(
    request: HttpRequest, slug: str
) -> JsonResponse:
    auth_error = _require_auth(request)
    if auth_error:
        return auth_error
    # Invitees may open a pending invite even when the org profile is draft
    # or unlisted. Inbox/notifications already show that row.
    organization = get_organization_by_slug(slug)
    if organization is None:
        return _json_error("not_found", status=404)
    chat = get_active_recruiting_chat(organization)
    invitation = viewer_recruiting_invitation_payload(chat, request.user)
    if invitation is None or chat is None:
        return _json_error("not_found", status=404)
    return JsonResponse(
        {
            "ok": True,
            "invitation": invitation,
            "recruiting_chat": serialize_recruiting_chat_for_viewer(
                chat, request.user, include_manager_fields=False
            ),
        }
    )


@require_GET
def api_v1_recruiting_invitation_detail(
    request: HttpRequest, invitation_id: int
) -> JsonResponse:
    auth_error = _require_auth(request)
    if auth_error:
        return auth_error
    try:
        invitation = get_recruiting_invitation_for_invitee(invitation_id, request.user)
    except OrganizationRecruitingChatError as exc:
        return _error_response(exc)
    chat = getattr(invitation.room, "organization_recruiting_chat", None)
    return JsonResponse(
        {
            "ok": True,
            "invitation": serialize_recruiting_invitation(invitation),
            "recruiting_chat": (
                serialize_recruiting_chat_for_viewer(
                    chat, request.user, include_manager_fields=False
                )
                if chat is not None
                else None
            ),
        }
    )


@require_POST
def api_v1_recruiting_invitation_accept(
    request: HttpRequest, invitation_id: int
) -> JsonResponse:
    auth_error = _require_auth(request)
    if auth_error:
        return auth_error
    try:
        invitation = get_recruiting_invitation_for_invitee(invitation_id, request.user)
        payload = accept_recruiting_invitation(invitation=invitation, user=request.user)
    except OrganizationRecruitingChatError as exc:
        return _error_response(exc)
    return JsonResponse({"ok": True, **payload})


@require_POST
def api_v1_recruiting_invitation_decline(
    request: HttpRequest, invitation_id: int
) -> JsonResponse:
    auth_error = _require_auth(request)
    if auth_error:
        return auth_error
    try:
        invitation = get_recruiting_invitation_for_invitee(invitation_id, request.user)
        payload = decline_recruiting_invitation(invitation=invitation, user=request.user)
    except OrganizationRecruitingChatError as exc:
        return _error_response(exc)
    return JsonResponse({"ok": True, **payload})
