"""JSON API for React DM / Group Chat (Phase 8)."""

from __future__ import annotations

import json

from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from .dm_services import can_access_dm_room  # noqa: F401 — kept for start_dm paths
from .group_chat_services import can_access_group_room
from .group_invite_services import (
    accept_group_invitation,
    can_view_group_room,
    create_or_refresh_invitations,
    decline_group_invitation,
    list_invite_candidates,
)
from .dm_request_services import (
    accept_dm_request,
    can_access_dm_room_for_viewer,
    decline_dm_request,
    list_pending_dm_requests_payload,
)
from .models import ChatRoom, UserDirectMessageRoom
from .dm_api_services import (
    build_dm_messages_payload,
    build_dm_room_payload,
    build_group_messages_payload,
    build_group_room_payload,
    build_inbox_payload,
    create_group_chat,
    list_following_for_group,
    send_dm_message,
    send_group_chat_message,
    serialize_dm_message,
    serialize_group_message,
    start_dm,
)

User = get_user_model()


def _json_error(message: str, *, status: int = 400, **extra) -> JsonResponse:
    payload = {"ok": False, "error": message}
    payload.update(extra)
    return JsonResponse(payload, status=status)


def _parse_json(request: HttpRequest) -> dict:
    if request.content_type and "application/json" in request.content_type:
        try:
            return json.loads(request.body.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            return {}
    return {}


def _parse_id_list(raw_ids) -> list[int]:
    ids: list[int] = []
    if raw_ids is None:
        return ids
    if not isinstance(raw_ids, (list, tuple)):
        raw_ids = [raw_ids]
    for raw in raw_ids:
        try:
            ids.append(int(raw))
        except (TypeError, ValueError):
            continue
    return ids


@login_required
@require_GET
def api_v1_dm_inbox(request: HttpRequest) -> JsonResponse:
    return JsonResponse(build_inbox_payload(request.user, request.GET.get("tab")))


@login_required
@require_POST
def api_v1_dm_start(request: HttpRequest) -> JsonResponse:
    data = _parse_json(request)
    raw = data.get("user_id") or request.POST.get("user_id")
    try:
        user_id = int(raw)
    except (TypeError, ValueError):
        return _json_error("invalid_user", status=400)
    partner = get_object_or_404(User, pk=user_id)
    try:
        room, created = start_dm(request.user, partner)
    except ValueError as exc:
        return _json_error(str(exc), status=400)
    return JsonResponse(
        {"ok": True, "room_id": room.pk, "created": created, "spa_path": f"/dm/{room.pk}"}
    )


@login_required
@require_GET
def api_v1_dm_room(request: HttpRequest, room_pk: int) -> JsonResponse:
    room = get_object_or_404(
        UserDirectMessageRoom.objects.select_related(
            "user_a", "user_a__profile", "user_b", "user_b__profile"
        ),
        pk=room_pk,
    )
    if not can_access_dm_room_for_viewer(room, request.user):
        return _json_error("forbidden", status=403)
    return JsonResponse(build_dm_room_payload(room, request.user))


@login_required
@require_GET
def api_v1_dm_messages(request: HttpRequest, room_pk: int) -> JsonResponse:
    room = get_object_or_404(
        UserDirectMessageRoom.objects.select_related("user_a", "user_b"),
        pk=room_pk,
    )
    if not can_access_dm_room_for_viewer(room, request.user):
        return JsonResponse({"error": "forbidden"}, status=403)
    return JsonResponse(
        build_dm_messages_payload(
            room, request.user, after=request.GET.get("after", "")
        )
    )


@login_required
@require_POST
def api_v1_dm_send(request: HttpRequest, room_pk: int) -> JsonResponse:
    room = get_object_or_404(
        UserDirectMessageRoom.objects.select_related("user_a", "user_b"),
        pk=room_pk,
    )
    data = _parse_json(request)
    body = str(data.get("body") if data else request.POST.get("body", ""))
    try:
        message = send_dm_message(room, request.user, body)
    except ValueError as exc:
        code = str(exc)
        status = 403 if code in ("forbidden", "blocked", "request_pending") else 400
        return _json_error(code, status=status)
    message = (
        type(message)
        .objects.select_related("sender", "sender__profile")
        .get(pk=message.pk)
    )
    return JsonResponse(
        {
            "ok": True,
            "message": serialize_dm_message(message, request.user.id),
        },
        status=201,
    )


@login_required
@require_http_methods(["GET", "POST"])
def api_v1_dm_groups(request: HttpRequest) -> JsonResponse:
    if request.method == "GET":
        query = (request.GET.get("q") or "").strip()
        if query:
            candidates = list_invite_candidates(request.user, query=query)
        else:
            candidates = list_following_for_group(request.user)
        return JsonResponse(
            {
                "ok": True,
                "following": candidates,
                "candidates": candidates,
            }
        )
    data = _parse_json(request)
    member_ids = data.get("member_ids") or request.POST.getlist("member_ids")
    ids = _parse_id_list(member_ids)
    name = str(data.get("name") if data else request.POST.get("name", ""))
    try:
        room = create_group_chat(request.user, name=name, member_ids=ids)
    except ValueError as exc:
        return _json_error(str(exc), status=400)
    return JsonResponse(
        {
            "ok": True,
            "room_id": room.pk,
            "spa_path": f"/dm/groups/{room.pk}",
        },
        status=201,
    )


@login_required
@require_GET
def api_v1_dm_group_room(request: HttpRequest, room_pk: int) -> JsonResponse:
    room = get_object_or_404(
        ChatRoom.objects.prefetch_related("memberships__user__profile"),
        pk=room_pk,
        kind=ChatRoom.Kind.GROUP,
    )
    if not can_view_group_room(room, request.user):
        return _json_error("forbidden", status=403)
    return JsonResponse(build_group_room_payload(room, request.user))


@login_required
@require_GET
def api_v1_dm_group_messages(request: HttpRequest, room_pk: int) -> JsonResponse:
    room = get_object_or_404(ChatRoom, pk=room_pk, kind=ChatRoom.Kind.GROUP)
    if not can_view_group_room(room, request.user):
        return JsonResponse({"error": "forbidden"}, status=403)
    return JsonResponse(
        build_group_messages_payload(
            room, request.user, after=request.GET.get("after", "")
        )
    )


@login_required
@require_POST
def api_v1_dm_group_send(request: HttpRequest, room_pk: int) -> JsonResponse:
    room = get_object_or_404(ChatRoom, pk=room_pk, kind=ChatRoom.Kind.GROUP)
    data = _parse_json(request)
    body = str(data.get("body") if data else request.POST.get("body", ""))
    try:
        message = send_group_chat_message(room, request.user, body)
    except ValueError as exc:
        code = str(exc)
        status = 403 if code == "forbidden" else 400
        return _json_error(code, status=status)
    message = (
        type(message)
        .objects.select_related("sender", "sender__profile")
        .get(pk=message.pk)
    )
    return JsonResponse(
        {
            "ok": True,
            "message": serialize_group_message(message, request.user.id),
        },
        status=201,
    )


@login_required
@require_POST
def api_v1_dm_group_invite(request: HttpRequest, room_pk: int) -> JsonResponse:
    room = get_object_or_404(ChatRoom, pk=room_pk, kind=ChatRoom.Kind.GROUP)
    if not can_access_group_room(room, request.user):
        return _json_error("forbidden", status=403)
    data = _parse_json(request)
    invitee_ids = _parse_id_list(
        data.get("member_ids")
        or data.get("invitee_ids")
        or request.POST.getlist("member_ids")
    )
    try:
        invitations = create_or_refresh_invitations(
            room, request.user, invitee_ids
        )
    except ValueError as exc:
        return _json_error(str(exc), status=400)
    return JsonResponse(
        {
            "ok": True,
            "invited_count": len(invitations),
            "invitation_ids": [inv.pk for inv in invitations],
        },
        status=201,
    )


@login_required
@require_POST
def api_v1_dm_group_accept(request: HttpRequest, room_pk: int) -> JsonResponse:
    room = get_object_or_404(ChatRoom, pk=room_pk, kind=ChatRoom.Kind.GROUP)
    try:
        accept_group_invitation(room, request.user)
    except ValueError as exc:
        return _json_error(str(exc), status=400)
    return JsonResponse(build_group_room_payload(room, request.user))


@login_required
@require_POST
def api_v1_dm_group_decline(request: HttpRequest, room_pk: int) -> JsonResponse:
    room = get_object_or_404(ChatRoom, pk=room_pk, kind=ChatRoom.Kind.GROUP)
    try:
        decline_group_invitation(room, request.user)
    except ValueError as exc:
        return _json_error(str(exc), status=400)
    return JsonResponse({"ok": True, "declined": True, "spa_path": "/dm"})


@login_required
@require_GET
def api_v1_dm_message_requests(request: HttpRequest) -> JsonResponse:
    return JsonResponse(list_pending_dm_requests_payload(request.user))


@login_required
@require_POST
def api_v1_dm_request_accept(request: HttpRequest, room_pk: int) -> JsonResponse:
    room = get_object_or_404(
        UserDirectMessageRoom.objects.select_related(
            "user_a", "user_a__profile", "user_b", "user_b__profile"
        ),
        pk=room_pk,
    )
    try:
        accept_dm_request(room, request.user)
    except ValueError as exc:
        return _json_error(str(exc), status=400)
    return JsonResponse(build_dm_room_payload(room, request.user))


@login_required
@require_POST
def api_v1_dm_request_decline(request: HttpRequest, room_pk: int) -> JsonResponse:
    room = get_object_or_404(UserDirectMessageRoom, pk=room_pk)
    try:
        decline_dm_request(room, request.user)
    except ValueError as exc:
        return _json_error(str(exc), status=400)
    return JsonResponse({"ok": True, "declined": True, "spa_path": "/dm"})
