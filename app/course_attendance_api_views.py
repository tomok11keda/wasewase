"""JSON API for course attendance (per-day absence records)."""

from __future__ import annotations

import json
import logging

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_http_methods, require_POST

from .course_attendance_services import (
    build_attendance_payload,
    create_attendance_record,
    delete_attendance_record,
    ensure_course_attendance_record_table,
    serialize_attendance_record,
    user_can_view_attendance,
)
from .course_services import resolve_canonical_offering
from .models import CourseOffering

logger = logging.getLogger(__name__)


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


def _get_offering(offering_pk: int) -> CourseOffering:
    offering = CourseOffering.objects.select_related("course").get(pk=offering_pk)
    try:
        return resolve_canonical_offering(offering)
    except ValueError as err:
        code = str(err)
        if code in {"offering_hidden", "offering_inactive", "offering_merge_cycle"}:
            raise CourseOffering.DoesNotExist from err
        raise


@login_required
@require_http_methods(["GET", "POST"])
def api_v1_courses_offering_attendance(
    request: HttpRequest, offering_pk: int
) -> JsonResponse:
    """GET: 欠席一覧+件数 / POST: 欠席を記録。本人のみ。"""
    ensure_course_attendance_record_table()
    try:
        offering = _get_offering(offering_pk)
    except CourseOffering.DoesNotExist:
        return _json_error("not_found", status=404)

    if request.method == "POST":
        return _create(request, offering)

    if not user_can_view_attendance(request.user, offering):
        return _json_error("forbidden", status=403)

    payload = build_attendance_payload(request.user, offering)
    if payload is None:
        return _json_error("forbidden", status=403)
    return JsonResponse({"ok": True, "attendance": payload})


def _create(request: HttpRequest, offering: CourseOffering) -> JsonResponse:
    data = _parse_json(request)
    try:
        row = create_attendance_record(
            request.user,
            offering_id=offering.pk,
            date_raw=str(data.get("date") or ""),
            status=str(data.get("status") or "absent"),
        )
    except ValueError as err:
        code = str(err) or "create_failed"
        status = 400
        if code in {
            "forbidden",
            "enrollment_required",
            "current_enrollment_required",
        }:
            status = 403
        if code in {"offering_not_found", "offering_hidden", "offering_merged"}:
            status = 404
        return _json_error(code, status=status)
    except Exception:
        logger.exception(
            "attendance create failed user=%s offering=%s",
            request.user.pk,
            offering.pk,
        )
        return _json_error("create_failed", status=500)

    attendance = build_attendance_payload(request.user, offering)
    return JsonResponse(
        {
            "ok": True,
            "record": serialize_attendance_record(row),
            "attendance": attendance,
        },
        status=201,
    )


@login_required
@require_http_methods(["POST", "DELETE"])
def api_v1_courses_attendance_delete(
    request: HttpRequest, record_pk: int
) -> JsonResponse:
    """欠席記録を取り消す。"""
    ensure_course_attendance_record_table()
    try:
        deleted = delete_attendance_record(request.user, record_pk)
    except ValueError as err:
        code = str(err) or "delete_failed"
        if code == "forbidden":
            return _json_error("forbidden", status=403)
        if code == "not_found":
            return _json_error("not_found", status=404)
        return _json_error(code)
    except Exception:
        logger.exception(
            "attendance delete failed user=%s id=%s",
            request.user.pk,
            record_pk,
        )
        return _json_error("delete_failed", status=500)

    offering_id = deleted.get("offering_id")
    attendance = None
    if offering_id:
        try:
            offering = _get_offering(int(offering_id))
            attendance = build_attendance_payload(request.user, offering)
        except CourseOffering.DoesNotExist:
            attendance = None

    return JsonResponse(
        {
            "ok": True,
            "deleted": True,
            "id": record_pk,
            "record": deleted,
            "attendance": attendance,
        }
    )


@login_required
@require_POST
def api_v1_courses_offering_attendance_create(
    request: HttpRequest, offering_pk: int
) -> JsonResponse:
    """後方互換: .../attendance/create/"""
    ensure_course_attendance_record_table()
    try:
        offering = _get_offering(offering_pk)
    except CourseOffering.DoesNotExist:
        return _json_error("not_found", status=404)
    return _create(request, offering)
