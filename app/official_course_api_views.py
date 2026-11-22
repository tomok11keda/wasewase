"""Student-facing OfficialClass search / enroll API (Option B)."""

from __future__ import annotations

import json
import logging

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_GET, require_POST

from .course_services import (
    enrollment_counts_for,
    sanitize_plain_text,
    serialize_offering,
    validate_academic_year,
)
from .models import CourseOffering
from .official_course_services import (
    ALLOWED_SEMESTER_CODES,
    CanonicalOfferingRequired,
    MAX_OFFICIAL_QUERY_LEN,
    MAX_OFFICIAL_SEARCH_LIMIT,
    MultipleOfferingsForOfficial,
    enroll_user_from_official,
    official_pilot_schools,
    official_student_ui_enabled,
    search_official_classes,
    serialize_official_class,
    student_visible_official_classes,
)
from .timetable_services import slot_to_payload

logger = logging.getLogger(__name__)


def _json_body(request: HttpRequest) -> dict:
    try:
        raw = request.body.decode("utf-8") or "{}"
        if len(raw) > 32_000:
            return {}
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {}


def _json_error(code: str, status: int = 400, **extra) -> JsonResponse:
    payload = {"ok": False, "error": code, **extra}
    return JsonResponse(payload, status=status)


def _parse_int(value, default=None):
    if value is None or value == "":
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _require_feature() -> JsonResponse | None:
    if not official_student_ui_enabled():
        return _json_error("feature_disabled", status=404)
    return None


@require_GET
def api_v1_courses_official_search(request: HttpRequest) -> JsonResponse:
    blocked = _require_feature()
    if blocked:
        return blocked

    q = sanitize_plain_text(request.GET.get("q") or "", max_len=MAX_OFFICIAL_QUERY_LEN)
    school = sanitize_plain_text(request.GET.get("school") or "", max_len=50) or None
    semester = (request.GET.get("semester") or request.GET.get("semester_code") or "").strip()
    if semester and semester not in ALLOWED_SEMESTER_CODES and semester not in CourseOffering.Semester.values:
        return _json_error("invalid_semester")
    # Map CourseOffering semester → official semester_code when needed
    semester_code = semester or None

    day = _parse_int(request.GET.get("day"))
    period = _parse_int(request.GET.get("period"))
    period_kind = (request.GET.get("period_kind") or "").strip() or None
    if period_kind and period_kind not in CourseOffering.PeriodKind.values:
        return _json_error("invalid_period_kind")
    if day is not None and (day < 0 or day > 6):
        return _json_error("invalid_day")
    if period is not None and (period < 1 or period > 7):
        return _json_error("invalid_period")

    year = None
    year_raw = request.GET.get("year")
    if year_raw not in (None, ""):
        year = _parse_int(year_raw)
        if year is None:
            return _json_error("invalid_academic_year")
        try:
            year = validate_academic_year(year)
        except ValueError:
            return _json_error("invalid_academic_year")

    limit = min(
        _parse_int(request.GET.get("limit"), 30) or 30,
        MAX_OFFICIAL_SEARCH_LIMIT,
    )
    offset = max(_parse_int(request.GET.get("offset"), 0) or 0, 0)

    if school:
        pilots = official_pilot_schools()
        if pilots and school not in pilots:
            return JsonResponse(
                {
                    "ok": True,
                    "results": [],
                    "total": 0,
                    "limit": limit,
                    "offset": offset,
                    "has_more": False,
                }
            )

    try:
        rows, total = search_official_classes(
            q=q,
            academic_year=year,
            semester_code=semester_code,
            school=school,
            day_of_week=day,
            period=period,
            period_kind=period_kind,
            limit=limit,
            offset=offset,
        )
    except Exception:
        logger.exception("official class search failed")
        return _json_error("search_failed", status=500)

    viewer = request.user if request.user.is_authenticated else None
    return JsonResponse(
        {
            "ok": True,
            "results": [serialize_official_class(o, viewer=viewer) for o in rows],
            "total": total,
            "limit": limit,
            "offset": offset,
            "has_more": offset + len(rows) < total,
        }
    )


@login_required
@require_POST
def api_v1_courses_official_enroll(
    request: HttpRequest, official_pk: int
) -> JsonResponse:
    blocked = _require_feature()
    if blocked:
        return blocked

    official = student_visible_official_classes().filter(pk=official_pk).first()
    if official is None:
        # research_only / cancelled / other school → not found (no leak)
        return _json_error("not_found", status=404)

    body = _json_body(request)
    slot_key = (body.get("slot_key") or "").strip() or None
    add_meeting = bool(body.get("add_meeting"))

    try:
        _enrollment, slot, offering = enroll_user_from_official(
            request.user,
            official,
            slot_key=slot_key,
            add_meeting_if_missing=add_meeting,
        )
    except CanonicalOfferingRequired as exc:
        return _json_error(
            exc.reason or "pending_canonical",
            status=409,
            message="この公式授業はまだ共通時間割の準備中です。しばらくしてから再度お試しください。",
            official_class_id=official.pk,
        )
    except MultipleOfferingsForOfficial as exc:
        return _json_error(
            "conflict",
            status=409,
            message="この公式授業には複数の登録先があり、管理者の確認が必要です。",
            official_class_id=official.pk,
            offering_ids=exc.offering_ids,
        )
    except ValueError as exc:
        code = str(exc) or "enroll_failed"
        status = 409 if code in {"slot_conflict", "slot_mismatch"} else 400
        return _json_error(code, status=status)
    except Exception:
        logger.exception(
            "official enroll failed user=%s official=%s",
            request.user.pk,
            official_pk,
        )
        return _json_error("save_failed", status=500)

    counts = enrollment_counts_for([offering.pk])
    return JsonResponse(
        {
            "ok": True,
            "official_class": serialize_official_class(
                official, viewer=request.user
            ),
            "offering": serialize_offering(
                offering,
                enrollment_count=counts.get(offering.pk, 0),
                viewer=request.user,
            ),
            "slot": slot_to_payload(slot),
        }
    )
