"""授業マスタ / 履修 / レビュー API（production hardening）。"""
from __future__ import annotations

import json
import logging

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from .constants import COURSE_CAMPUS_CHOICES, COURSE_SEMESTER_CHOICES, FACULTY_CHOICES
from .course_services import (
    CREATE_OFFERING_RATE_LIMIT,
    CREATE_OFFERING_RATE_WINDOW,
    MAX_QUERY_LEN,
    REVIEW_RATE_LIMIT,
    REVIEW_RATE_WINDOW,
    check_rate_limit,
    create_offering,
    current_academic_year,
    current_semester,
    enroll_user_in_offering,
    enrollment_counts_for,
    find_duplicate_candidates,
    remove_offering_from_timetable,
    resolve_canonical_offering,
    review_averages,
    sanitize_plain_text,
    search_offerings,
    serialize_offering,
    serialize_review,
    upsert_review,
    user_can_review,
    validate_academic_year,
    viewer_states_for,
)
from .models import CourseOffering, CourseReview
from .timetable_services import parse_slot_key, slot_to_payload

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


def _json_error(code: str, status: int = 400) -> JsonResponse:
    return JsonResponse({"ok": False, "error": code}, status=status)


def _parse_int(value, default=None):
    if value is None or value == "":
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _get_visible_offering(offering_pk: int) -> CourseOffering:
    offering = get_object_or_404(
        CourseOffering.objects.select_related("course"),
        pk=offering_pk,
    )
    if offering.status == CourseOffering.Status.HIDDEN:
        raise CourseOffering.DoesNotExist()
    try:
        return resolve_canonical_offering(offering)
    except ValueError as exc:
        if str(exc) in {"offering_hidden", "offering_inactive", "offering_merge_cycle"}:
            raise CourseOffering.DoesNotExist() from exc
        raise


@require_GET
def api_v1_courses_meta(_request: HttpRequest) -> JsonResponse:
    year = current_academic_year()
    return JsonResponse(
        {
            "ok": True,
            "academic_year": year,
            "semester": current_semester(),
            "academic_year_min": year - 1,
            "academic_year_max": year + 1,
            "semesters": [
                {"value": v, "label": label} for v, label in COURSE_SEMESTER_CHOICES
            ],
            "faculties": [
                {"value": v, "label": label} for v, label in FACULTY_CHOICES if v
            ],
            "campuses": [
                {"value": v, "label": label} for v, label in COURSE_CAMPUS_CHOICES
            ],
        }
    )


@require_GET
def api_v1_courses_search(request: HttpRequest) -> JsonResponse:
    q = sanitize_plain_text(request.GET.get("q") or "", max_len=MAX_QUERY_LEN)
    day = _parse_int(request.GET.get("day"))
    period = _parse_int(request.GET.get("period"))
    period_kind = (request.GET.get("period_kind") or "").strip() or None
    if period_kind and period_kind not in CourseOffering.PeriodKind.values:
        return _json_error("invalid_period_kind")
    semester = (request.GET.get("semester") or "").strip() or None
    if semester and semester not in CourseOffering.Semester.values:
        return _json_error("invalid_semester")

    year_raw = request.GET.get("year")
    year = None
    if year_raw not in (None, ""):
        year = _parse_int(year_raw)
        if year is None:
            return _json_error("invalid_academic_year")
        try:
            year = validate_academic_year(year)
        except ValueError:
            return _json_error("invalid_academic_year")

    limit = min(_parse_int(request.GET.get("limit"), 30) or 30, 50)

    try:
        offerings = search_offerings(
            q=q,
            day_of_week=day,
            period_kind=period_kind,
            period=period,
            semester=semester,
            academic_year=year,
            limit=limit,
        )
    except Exception:
        logger.exception("course search failed")
        return _json_error("search_failed", status=500)

    ids = [o.pk for o in offerings]
    counts = enrollment_counts_for(ids)
    viewer = request.user if request.user.is_authenticated else None
    enroll_map, review_ids = viewer_states_for(viewer, ids)
    return JsonResponse(
        {
            "ok": True,
            "results": [
                serialize_offering(
                    o,
                    enrollment_count=counts.get(o.pk, 0),
                    viewer=viewer,
                    viewer_enrollment=enroll_map.get(o.pk),
                    viewer_has_review=o.pk in review_ids,
                )
                for o in offerings
            ],
        }
    )


@require_GET
def api_v1_courses_duplicates(request: HttpRequest) -> JsonResponse:
    title = sanitize_plain_text(request.GET.get("title") or "", max_len=120)
    instructor = sanitize_plain_text(
        request.GET.get("instructor") or "", max_len=120
    )
    day = _parse_int(request.GET.get("day"))
    period = _parse_int(request.GET.get("period"))
    period_kind = (
        request.GET.get("period_kind") or CourseOffering.PeriodKind.PERIOD
    ).strip()
    semester = (request.GET.get("semester") or current_semester()).strip()
    year = _parse_int(request.GET.get("year"), current_academic_year())
    if not title or day is None or period is None:
        return _json_error("missing_fields")
    try:
        year = validate_academic_year(year or current_academic_year())
    except ValueError:
        return _json_error("invalid_academic_year")
    if period_kind not in CourseOffering.PeriodKind.values:
        return _json_error("invalid_period_kind")
    if semester not in CourseOffering.Semester.values:
        return _json_error("invalid_semester")

    dups = find_duplicate_candidates(
        title=title,
        instructor=instructor,
        day_of_week=day,
        period=period,
        period_kind=period_kind,
        semester=semester,
        academic_year=year,
    )
    counts = enrollment_counts_for([o.pk for o in dups])
    return JsonResponse(
        {
            "ok": True,
            "duplicates": [
                serialize_offering(o, enrollment_count=counts.get(o.pk, 0))
                for o in dups
            ],
        }
    )


@login_required
@require_POST
def api_v1_courses_offerings_create(request: HttpRequest) -> JsonResponse:
    rate_key = f"course:create:{request.user.pk}"
    if not check_rate_limit(
        rate_key,
        limit=CREATE_OFFERING_RATE_LIMIT,
        window=CREATE_OFFERING_RATE_WINDOW,
    ):
        return _json_error("rate_limited", status=429)

    body = _json_body(request)
    force_create = bool(body.get("force_create"))
    day = _parse_int(body.get("day_of_week"))
    period = _parse_int(body.get("period"))
    period_kind = (
        body.get("period_kind") or CourseOffering.PeriodKind.PERIOD
    ).strip()
    year = _parse_int(body.get("academic_year"), current_academic_year())
    semester = (body.get("semester") or current_semester()).strip()
    slot_key = (body.get("slot_key") or "").strip() or None

    # 空きセルから来た場合は slot_key を曜時限の正とする（FE の meta レース対策）
    if slot_key:
        parsed = parse_slot_key(slot_key)
        if parsed is None:
            return _json_error("invalid_slot_key")
        day = parsed["day_index"]
        period = parsed["number"]
        period_kind = parsed["kind"]

    if day is None or period is None:
        return _json_error("missing_schedule")

    try:
        offering, duplicates = create_offering(
            user=request.user,
            title=body.get("title") or "",
            instructor=body.get("instructor") or "",
            academic_year=year or current_academic_year(),
            semester=semester,
            day_of_week=day,
            period=period,
            period_kind=period_kind,
            school=body.get("school") or "",
            campus=body.get("campus") or "",
            room=body.get("room") or "",
            credits=body.get("credits") or "",
            force_create=force_create,
        )
    except ValueError as exc:
        return _json_error(str(exc))
    except Exception:
        logger.exception(
            "course offering create failed user=%s", request.user.pk
        )
        return _json_error("save_failed", status=500)

    if duplicates:
        counts = enrollment_counts_for([o.pk for o in duplicates])
        return JsonResponse(
            {
                "ok": False,
                "error": "duplicate_candidates",
                "duplicates": [
                    serialize_offering(o, enrollment_count=counts.get(o.pk, 0))
                    for o in duplicates
                ],
            },
            status=409,
        )

    enroll = bool(body.get("enroll", True))
    slot_payload = None
    if enroll:
        try:
            # Prefer aligned slot_key; fall back to offering.slot_key
            try:
                _enrollment, slot = enroll_user_in_offering(
                    request.user,
                    offering,
                    slot_key=slot_key,
                )
            except ValueError as exc:
                if str(exc) == "slot_mismatch" and slot_key:
                    logger.warning(
                        "course enroll slot_mismatch; retry with offering slot "
                        "user=%s offering=%s requested=%s",
                        request.user.pk,
                        offering.pk,
                        slot_key,
                    )
                    _enrollment, slot = enroll_user_in_offering(
                        request.user,
                        offering,
                        slot_key=None,
                    )
                else:
                    raise
            slot_payload = slot_to_payload(slot)
        except ValueError as exc:
            logger.warning(
                "course enroll-after-create rejected user=%s offering=%s code=%s",
                request.user.pk,
                offering.pk,
                exc,
            )
            # Offering is already persisted; return it so the client can recover
            counts = enrollment_counts_for([offering.pk])
            return JsonResponse(
                {
                    "ok": False,
                    "error": str(exc),
                    "created": True,
                    "offering": serialize_offering(
                        offering,
                        enrollment_count=counts.get(offering.pk, 0),
                        viewer=request.user,
                    ),
                    "slot": None,
                },
                status=400,
            )
        except Exception:
            logger.exception(
                "course enroll-after-create failed user=%s offering=%s",
                request.user.pk,
                offering.pk,
            )
            counts = enrollment_counts_for([offering.pk])
            return JsonResponse(
                {
                    "ok": False,
                    "error": "enroll_failed",
                    "created": True,
                    "offering": serialize_offering(
                        offering,
                        enrollment_count=counts.get(offering.pk, 0),
                        viewer=request.user,
                    ),
                    "slot": None,
                },
                status=500,
            )

    counts = enrollment_counts_for([offering.pk])
    return JsonResponse(
        {
            "ok": True,
            "created": True,
            "offering": serialize_offering(
                offering,
                enrollment_count=counts.get(offering.pk, 0),
                viewer=request.user,
            ),
            "slot": slot_payload,
        }
    )


@require_GET
def api_v1_courses_offering_detail(
    request: HttpRequest, offering_pk: int
) -> JsonResponse:
    try:
        offering = _get_visible_offering(offering_pk)
    except CourseOffering.DoesNotExist:
        return _json_error("not_found", status=404)

    viewer = request.user if request.user.is_authenticated else None
    counts = enrollment_counts_for([offering.pk])
    averages = review_averages(offering)
    payload = {
        "ok": True,
        "offering": serialize_offering(
            offering,
            enrollment_count=counts.get(offering.pk, 0),
            viewer=viewer,
        ),
        "review_summary": averages,
    }
    if viewer is not None and viewer.is_authenticated:
        payload["can_review"] = user_can_review(viewer, offering)
    return JsonResponse(payload)


@login_required
@require_POST
def api_v1_courses_offering_enroll(
    request: HttpRequest, offering_pk: int
) -> JsonResponse:
    try:
        offering = _get_visible_offering(offering_pk)
    except CourseOffering.DoesNotExist:
        return _json_error("not_found", status=404)

    body = _json_body(request)
    slot_key = (body.get("slot_key") or "").strip() or None
    try:
        _enrollment, slot = enroll_user_in_offering(
            request.user, offering, slot_key=slot_key
        )
    except ValueError as exc:
        return _json_error(str(exc))
    except Exception:
        logger.exception(
            "course enroll failed user=%s offering=%s",
            request.user.pk,
            offering_pk,
        )
        return _json_error("save_failed", status=500)

    counts = enrollment_counts_for([offering.pk])
    return JsonResponse(
        {
            "ok": True,
            "offering": serialize_offering(
                offering,
                enrollment_count=counts.get(offering.pk, 0),
                viewer=request.user,
            ),
            "slot": slot_to_payload(slot),
        }
    )


@login_required
@require_POST
def api_v1_courses_offering_unenroll(
    request: HttpRequest, offering_pk: int
) -> JsonResponse:
    offering = get_object_or_404(CourseOffering, pk=offering_pk)
    try:
        remove_offering_from_timetable(request.user, offering)
    except Exception:
        logger.exception(
            "course unenroll failed user=%s offering=%s",
            request.user.pk,
            offering_pk,
        )
        return _json_error("save_failed", status=500)

    try:
        canonical = resolve_canonical_offering(offering)
    except ValueError:
        canonical = offering
    counts = enrollment_counts_for([canonical.pk])
    return JsonResponse(
        {
            "ok": True,
            "offering": serialize_offering(
                canonical,
                enrollment_count=counts.get(canonical.pk, 0),
                viewer=request.user,
            ),
        }
    )


@require_http_methods(["GET", "POST"])
def api_v1_courses_offering_reviews(
    request: HttpRequest, offering_pk: int
) -> JsonResponse:
    try:
        offering = _get_visible_offering(offering_pk)
    except CourseOffering.DoesNotExist:
        return _json_error("not_found", status=404)

    if request.method == "GET":
        reviews = list(
            CourseReview.objects.filter(offering=offering, is_hidden=False)
            .order_by("-updated_at")[:50]
        )
        viewer_id = (
            request.user.pk if request.user.is_authenticated else None
        )
        items = []
        for review in reviews:
            data = serialize_review(review)
            data["is_own"] = viewer_id is not None and review.user_id == viewer_id
            items.append(data)
        return JsonResponse(
            {
                "ok": True,
                "summary": review_averages(offering),
                "reviews": items,
            }
        )

    if not request.user.is_authenticated:
        return _json_error("authentication_required", status=401)

    rate_key = f"course:review:{request.user.pk}"
    if not check_rate_limit(
        rate_key,
        limit=REVIEW_RATE_LIMIT,
        window=REVIEW_RATE_WINDOW,
    ):
        return _json_error("rate_limited", status=429)

    body = _json_body(request)
    try:
        review = upsert_review(
            user=request.user,
            offering=offering,
            overall_rating=int(body.get("overall_rating") or 0),
            difficulty_rating=int(body.get("difficulty_rating") or 0),
            workload_rating=int(body.get("workload_rating") or 0),
            attendance_rating=int(body.get("attendance_rating") or 0),
            exam_rating=int(body.get("exam_rating") or 0),
            comment=body.get("comment") or "",
        )
    except ValueError as exc:
        code = str(exc)
        status = 403 if code == "enrollment_required" else 400
        return _json_error(code, status=status)
    except Exception:
        logger.exception(
            "course review failed user=%s offering=%s",
            request.user.pk,
            offering_pk,
        )
        return _json_error("save_failed", status=500)

    data = serialize_review(review)
    data["is_own"] = True
    return JsonResponse(
        {
            "ok": True,
            "review": data,
            "summary": review_averages(offering),
        }
    )
