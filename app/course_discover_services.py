"""Community タブ向け Course Discovery（履修中 / 活発 / 人気）。"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from django.contrib.auth.base_user import AbstractBaseUser
from django.db.models import Avg, Count, Q
from django.utils import timezone

from .course_services import day_label, period_label
from .models import (
    ChatMessage,
    CourseEnrollment,
    CourseOffering,
    CourseReview,
)

logger = logging.getLogger(__name__)

ACTIVE_WINDOW_DAYS = 7
LIMIT_ENROLLED = 20
LIMIT_ACTIVE = 10
LIMIT_POPULAR = 10


def _visible_offerings():
    return (
        CourseOffering.objects.filter(status=CourseOffering.Status.ACTIVE)
        .select_related("course", "chat_room")
        .prefetch_related("meetings")
    )


def _schedule_from_offering(offering: CourseOffering) -> tuple[list[dict], str]:
    meetings = list(offering.meetings.all())
    if not meetings:
        return [], (
            f"{day_label(offering.day_of_week)}"
            f"{period_label(offering.period_kind, offering.period)}"
        )
    rows = [
        {
            "id": m.pk,
            "day_of_week": m.day_of_week,
            "day_label": day_label(m.day_of_week),
            "period_kind": m.period_kind,
            "period": m.period,
            "period_label": period_label(m.period_kind, m.period),
            "slot_key": m.slot_key,
        }
        for m in meetings
    ]
    label = "・".join(f"{r['day_label']}{r['period_label']}" for r in rows)
    return rows, label


def serialize_discover_card(
    offering: CourseOffering,
    *,
    enrollment_count: int = 0,
    review_count: int = 0,
    review_overall: float | None = None,
    talk_recent_count: int = 0,
    talk_today_count: int = 0,
    viewer_enrollment: str | None = None,
) -> dict[str, Any]:
    """公開可能な Discovery カード。欠席等の個人情報は含めない。"""
    meetings, schedule_label = _schedule_from_offering(offering)
    payload: dict[str, Any] = {
        "id": offering.pk,
        "course_id": offering.course_id,
        "title": offering.title,
        "instructor": offering.instructor,
        "academic_year": offering.academic_year,
        "semester": offering.semester,
        "semester_label": offering.get_semester_display(),
        "meetings": meetings,
        "schedule_label": schedule_label,
        "enrollment_count": int(enrollment_count or 0),
        "review_count": int(review_count or 0),
        "review_overall": (
            round(float(review_overall), 1) if review_overall is not None else None
        ),
        "talk_recent_count": int(talk_recent_count or 0),
        "talk_today_count": int(talk_today_count or 0),
    }
    if viewer_enrollment is not None:
        payload["viewer_enrollment"] = viewer_enrollment
    return payload


def _review_stats_map(offering_ids: list[int]) -> dict[int, dict[str, Any]]:
    if not offering_ids:
        return {}
    rows = (
        CourseReview.objects.filter(
            offering_id__in=offering_ids, is_hidden=False
        )
        .values("offering_id")
        .annotate(count=Count("id"), overall=Avg("overall_rating"))
    )
    return {
        int(row["offering_id"]): {
            "count": int(row["count"] or 0),
            "overall": row["overall"],
        }
        for row in rows
    }


def _enrollment_count_map(offering_ids: list[int]) -> dict[int, int]:
    if not offering_ids:
        return {}
    rows = (
        CourseEnrollment.objects.filter(
            offering_id__in=offering_ids,
            role=CourseEnrollment.Role.CURRENT,
        )
        .values("offering_id")
        .annotate(count=Count("id"))
    )
    return {int(r["offering_id"]): int(r["count"] or 0) for r in rows}


def _talk_counts_map(
    offering_ids: list[int], *, since
) -> tuple[dict[int, int], dict[int, int]]:
    """(recent_7d, today) message counts per offering_id."""
    if not offering_ids:
        return {}, {}
    today = timezone.localdate()
    visible = Q(is_hidden=False, deleted_at__isnull=True)
    recent_rows = (
        ChatMessage.objects.filter(
            visible,
            created_at__gte=since,
            room__kind="course",
            room__course_offering__id__in=offering_ids,
        )
        .values("room__course_offering__id")
        .annotate(count=Count("id"))
    )
    recent = {
        int(r["room__course_offering__id"]): int(r["count"] or 0)
        for r in recent_rows
        if r["room__course_offering__id"]
    }
    today_rows = (
        ChatMessage.objects.filter(
            visible,
            created_at__date=today,
            room__kind="course",
            room__course_offering__id__in=offering_ids,
        )
        .values("room__course_offering__id")
        .annotate(count=Count("id"))
    )
    today_map = {
        int(r["room__course_offering__id"]): int(r["count"] or 0)
        for r in today_rows
        if r["room__course_offering__id"]
    }
    return recent, today_map


def _cards_for_offerings(
    offerings: list[CourseOffering],
    *,
    viewer: AbstractBaseUser | None = None,
    talk_recent: dict[int, int] | None = None,
    talk_today: dict[int, int] | None = None,
    enroll_override: dict[int, int] | None = None,
    review_override: dict[int, dict[str, Any]] | None = None,
    viewer_roles: dict[int, str] | None = None,
) -> list[dict[str, Any]]:
    ids = [o.pk for o in offerings]
    enroll_map = enroll_override if enroll_override is not None else _enrollment_count_map(ids)
    review_map = review_override if review_override is not None else _review_stats_map(ids)
    talk_recent = talk_recent or {}
    talk_today = talk_today or {}
    cards = []
    for offering in offerings:
        rev = review_map.get(offering.pk) or {}
        role = None
        if viewer_roles is not None:
            role = viewer_roles.get(offering.pk)
        elif viewer is not None and getattr(viewer, "is_authenticated", False):
            # lazy path unused when map provided
            role = None
        cards.append(
            serialize_discover_card(
                offering,
                enrollment_count=enroll_map.get(offering.pk, 0),
                review_count=int(rev.get("count") or 0),
                review_overall=rev.get("overall"),
                talk_recent_count=talk_recent.get(offering.pk, 0),
                talk_today_count=talk_today.get(offering.pk, 0),
                viewer_enrollment=role,
            )
        )
    return cards


def list_enrolled_for_discover(
    user: AbstractBaseUser | None, *, limit: int = LIMIT_ENROLLED
) -> list[dict[str, Any]]:
    if user is None or not getattr(user, "is_authenticated", False):
        return []
    enrollments = list(
        CourseEnrollment.objects.filter(
            user=user,
            role=CourseEnrollment.Role.CURRENT,
            offering__status=CourseOffering.Status.ACTIVE,
        )
        .select_related("offering", "offering__course", "offering__chat_room")
        .prefetch_related("offering__meetings")
        .order_by("-updated_at", "-pk")[:limit]
    )
    offerings = [e.offering for e in enrollments]
    ids = [o.pk for o in offerings]
    since = timezone.now() - timedelta(days=ACTIVE_WINDOW_DAYS)
    talk_recent, talk_today = _talk_counts_map(ids, since=since)
    roles = {e.offering_id: CourseEnrollment.Role.CURRENT for e in enrollments}
    return _cards_for_offerings(
        offerings,
        talk_recent=talk_recent,
        talk_today=talk_today,
        viewer_roles=roles,
    )


def list_active_for_discover(*, limit: int = LIMIT_ACTIVE) -> list[dict[str, Any]]:
    """直近7日の Course Talk メッセージ数でランキング。"""
    since = timezone.now() - timedelta(days=ACTIVE_WINDOW_DAYS)
    visible_msg = Q(
        chat_room__chat_messages__is_hidden=False,
        chat_room__chat_messages__deleted_at__isnull=True,
        chat_room__chat_messages__created_at__gte=since,
    )
    qs = (
        _visible_offerings()
        .filter(chat_room__isnull=False, chat_room__kind="course")
        .annotate(talk_recent_count=Count("chat_room__chat_messages", filter=visible_msg))
        .filter(talk_recent_count__gt=0)
        .order_by("-talk_recent_count", "-pk")[:limit]
    )
    offerings = list(qs)
    ids = [o.pk for o in offerings]
    talk_recent = {o.pk: int(getattr(o, "talk_recent_count", 0) or 0) for o in offerings}
    _, talk_today = _talk_counts_map(ids, since=since)
    return _cards_for_offerings(
        offerings, talk_recent=talk_recent, talk_today=talk_today
    )


def list_popular_for_discover(*, limit: int = LIMIT_POPULAR) -> list[dict[str, Any]]:
    """履修者数を主、レビュー件数を補助。平均のみでは並べない。"""
    qs = (
        _visible_offerings()
        .annotate(
            enroll_count=Count(
                "enrollments",
                filter=Q(enrollments__role=CourseEnrollment.Role.CURRENT),
                distinct=True,
            ),
            review_count=Count(
                "reviews",
                filter=Q(reviews__is_hidden=False),
                distinct=True,
            ),
            review_overall=Avg(
                "reviews__overall_rating",
                filter=Q(reviews__is_hidden=False),
            ),
        )
        .filter(Q(enroll_count__gt=0) | Q(review_count__gt=0))
        .order_by("-enroll_count", "-review_count", "-pk")[:limit]
    )
    offerings = list(qs)
    enroll_map = {o.pk: int(getattr(o, "enroll_count", 0) or 0) for o in offerings}
    review_map = {
        o.pk: {
            "count": int(getattr(o, "review_count", 0) or 0),
            "overall": getattr(o, "review_overall", None),
        }
        for o in offerings
    }
    ids = [o.pk for o in offerings]
    since = timezone.now() - timedelta(days=ACTIVE_WINDOW_DAYS)
    talk_recent, talk_today = _talk_counts_map(ids, since=since)
    return _cards_for_offerings(
        offerings,
        enroll_override=enroll_map,
        review_override=review_map,
        talk_recent=talk_recent,
        talk_today=talk_today,
    )


def build_course_discover_payload(
    user: AbstractBaseUser | None,
    *,
    enrolled_limit: int = LIMIT_ENROLLED,
    active_limit: int = LIMIT_ACTIVE,
    popular_limit: int = LIMIT_POPULAR,
) -> dict[str, Any]:
    enrolled = list_enrolled_for_discover(user, limit=enrolled_limit)
    active = list_active_for_discover(limit=active_limit)
    popular = list_popular_for_discover(limit=popular_limit)
    return {
        "enrolled": enrolled,
        "active": active,
        "popular": popular,
        "limits": {
            "enrolled": enrolled_limit,
            "active": active_limit,
            "popular": popular_limit,
        },
        "active_window_days": ACTIVE_WINDOW_DAYS,
    }
