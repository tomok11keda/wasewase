"""授業トーク API。"""

from __future__ import annotations

import json
import logging

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from .course_chat_services import (
    build_course_talk_messages_payload,
    build_course_talk_payload,
    get_visible_offering_for_talk,
    is_course_talk_member,
    join_course_talk,
    leave_course_talk,
    send_course_talk_message,
    serialize_course_talk_message,
    enrollment_role_for,
)
from .models import ChatRoom, CourseOffering

logger = logging.getLogger(__name__)


def _json_body(request: HttpRequest) -> dict:
    try:
        raw = request.body.decode("utf-8") or "{}"
        if len(raw) > 8_000:
            return {}
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {}


def _json_error(code: str, status: int = 400) -> JsonResponse:
    return JsonResponse({"ok": False, "error": code}, status=status)


def _get_course_room_for_member(
    room_pk: int, user
) -> tuple[ChatRoom, CourseOffering] | JsonResponse:
    try:
        room = ChatRoom.objects.select_related("course_offering").get(
            pk=room_pk, kind=ChatRoom.Kind.COURSE
        )
    except ChatRoom.DoesNotExist:
        return _json_error("not_found", status=404)
    offering = getattr(room, "course_offering", None)
    if offering is None:
        return _json_error("not_found", status=404)
    try:
        offering = get_visible_offering_for_talk(offering.pk)
    except CourseOffering.DoesNotExist:
        return _json_error("not_found", status=404)
    if offering.chat_room_id != room.pk:
        # Merged / reassigned — follow canonical
        if offering.chat_room_id:
            room = offering.chat_room
        else:
            return _json_error("not_found", status=404)
    if not is_course_talk_member(room, user):
        return _json_error("forbidden", status=403)
    return room, offering


@login_required
@require_http_methods(["GET", "POST"])
def api_v1_courses_offering_talk(
    request: HttpRequest, offering_pk: int
) -> JsonResponse:
    """授業トークを開く（lazy create + 自動参加）。"""
    try:
        offering = get_visible_offering_for_talk(offering_pk)
    except CourseOffering.DoesNotExist:
        return _json_error("not_found", status=404)

    try:
        room, _membership, joined_now = join_course_talk(request.user, offering)
    except Exception:
        logger.exception(
            "course talk open failed user=%s offering=%s",
            request.user.pk,
            offering_pk,
        )
        return _json_error("save_failed", status=500)

    offering.refresh_from_db()
    return JsonResponse(
        build_course_talk_payload(
            room, offering, request.user, joined_now=joined_now
        )
    )


@login_required
@require_POST
def api_v1_courses_offering_talk_leave(
    request: HttpRequest, offering_pk: int
) -> JsonResponse:
    try:
        offering = get_visible_offering_for_talk(offering_pk)
    except CourseOffering.DoesNotExist:
        return _json_error("not_found", status=404)

    left = leave_course_talk(request.user, offering)
    return JsonResponse({"ok": True, "left": left})


@login_required
@require_GET
def api_v1_courses_talk_room(
    request: HttpRequest, room_pk: int
) -> JsonResponse:
    result = _get_course_room_for_member(room_pk, request.user)
    if isinstance(result, JsonResponse):
        return result
    room, offering = result
    return JsonResponse(
        build_course_talk_payload(room, offering, request.user, joined_now=False)
    )


@login_required
@require_GET
def api_v1_courses_talk_messages(
    request: HttpRequest, room_pk: int
) -> JsonResponse:
    result = _get_course_room_for_member(room_pk, request.user)
    if isinstance(result, JsonResponse):
        return result
    room, offering = result
    return JsonResponse(
        build_course_talk_messages_payload(
            room,
            offering,
            request.user,
            after=request.GET.get("after") or "",
        )
    )


@login_required
@require_POST
def api_v1_courses_talk_send(
    request: HttpRequest, room_pk: int
) -> JsonResponse:
    result = _get_course_room_for_member(room_pk, request.user)
    if isinstance(result, JsonResponse):
        return result
    room, offering = result
    body = _json_body(request)
    try:
        message = send_course_talk_message(
            room, request.user, body.get("body") or ""
        )
    except ValueError as exc:
        code = str(exc)
        status = 403 if code == "forbidden" else 400
        return _json_error(code, status=status)
    except Exception:
        logger.exception(
            "course talk send failed user=%s room=%s", request.user.pk, room_pk
        )
        return _json_error("save_failed", status=500)

    role = enrollment_role_for(request.user, offering)
    return JsonResponse(
        {
            "ok": True,
            "message": serialize_course_talk_message(
                message,
                request.user.pk,
                enrollment_role=role,
            ),
        }
    )
