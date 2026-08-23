"""JSON API for course calendar exceptions (per-day skip / restore)."""

from __future__ import annotations

import json
import logging

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_http_methods, require_POST

from .course_calendar_exception_services import (
    create_course_calendar_exception,
    delete_course_calendar_exception,
    ensure_course_calendar_exception_table,
    list_course_calendar_exceptions,
    serialize_course_calendar_exception,
)

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


@login_required
@require_http_methods(["GET", "POST"])
def api_v1_calendar_course_exceptions(request: HttpRequest) -> JsonResponse:
    """GET: 非表示一覧 / POST: この日の授業予定を非表示。"""
    ensure_course_calendar_exception_table()
    if request.method == "POST":
        return _create_exception(request)

    year = month = None
    year_raw = (request.GET.get("year") or "").strip()
    month_raw = (request.GET.get("month") or "").strip()
    if year_raw or month_raw:
        try:
            year = int(year_raw)
            month = int(month_raw)
        except (TypeError, ValueError):
            return _json_error("year_month_invalid")
        if year < 2000 or year > 2100 or month < 1 or month > 12:
            return _json_error("year_month_invalid")
    rows = list_course_calendar_exceptions(
        request.user, year=year, month=month
    )
    return JsonResponse(
        {
            "ok": True,
            "exceptions": [serialize_course_calendar_exception(r) for r in rows],
            "count": len(rows),
        }
    )


def _create_exception(request: HttpRequest) -> JsonResponse:
    data = _parse_json(request)
    offering_raw = data.get("offering_id")
    try:
        offering_id = int(offering_raw)
    except (TypeError, ValueError):
        return _json_error("offering_id_invalid")
    try:
        exc = create_course_calendar_exception(
            request.user,
            offering_id=offering_id,
            date_raw=str(data.get("date") or ""),
            status=str(data.get("status") or "skipped"),
        )
    except ValueError as err:
        code = str(err) or "create_failed"
        status = 403 if code in {"forbidden", "enrollment_required"} else 400
        if code in {"offering_not_found", "offering_hidden", "offering_merged"}:
            status = 404
        return _json_error(code, status=status)
    except Exception:
        logger.exception(
            "course calendar exception create failed user=%s", request.user.pk
        )
        return _json_error("create_failed", status=500)
    return JsonResponse(
        {"ok": True, "exception": serialize_course_calendar_exception(exc)},
        status=201,
    )


@login_required
@require_POST
def api_v1_calendar_course_exception_create(
    request: HttpRequest,
) -> JsonResponse:
    """後方互換: /create/ でも作成できる。"""
    ensure_course_calendar_exception_table()
    return _create_exception(request)


@login_required
@require_http_methods(["POST", "DELETE"])
def api_v1_calendar_course_exception_delete(
    request: HttpRequest, exception_pk: int
) -> JsonResponse:
    """非表示を解除してカレンダーへ復元。"""
    ensure_course_calendar_exception_table()
    try:
        deleted_payload = delete_course_calendar_exception(
            request.user, exception_pk
        )
    except ValueError as err:
        code = str(err) or "delete_failed"
        if code == "forbidden":
            return _json_error("forbidden", status=403)
        if code == "not_found":
            return _json_error("not_found", status=404)
        return _json_error(code)
    except Exception:
        logger.exception(
            "course calendar exception delete failed user=%s id=%s",
            request.user.pk,
            exception_pk,
        )
        return _json_error("delete_failed", status=500)
    return JsonResponse(
        {
            "ok": True,
            "deleted": True,
            "id": exception_pk,
            "exception": deleted_payload,
        }
    )
