"""CourseMeeting helpers + offering schedule sync."""

from __future__ import annotations

import logging
from typing import Any, Iterable

from django.db import connection, transaction
from django.db.utils import OperationalError, ProgrammingError

from .models import CourseMeeting, CourseOffering

logger = logging.getLogger(__name__)


def ensure_course_meeting_table() -> None:
    table = CourseMeeting._meta.db_table
    try:
        with connection.cursor() as cursor:
            if table in connection.introspection.table_names(cursor):
                return
        with connection.schema_editor() as schema_editor:
            schema_editor.create_model(CourseMeeting)
        logger.warning("Created missing %s table on startup", table)
    except (OperationalError, ProgrammingError) as exc:
        message = str(exc).lower()
        if "already exists" in message or "duplicate" in message:
            return
        logger.warning("CourseMeeting table repair failed: %s", exc)
    except Exception as exc:
        logger.warning("CourseMeeting table repair failed: %s", exc)


def meeting_slot_key(day_of_week: int, period: int, period_kind: str) -> str:
    prefix = "od" if period_kind == CourseOffering.PeriodKind.OD else "p"
    return f"{prefix}{period}-d{day_of_week}"


def serialize_meeting(meeting: CourseMeeting) -> dict[str, Any]:
    from .course_services import day_label, period_label

    return {
        "id": meeting.pk,
        "day_of_week": meeting.day_of_week,
        "day_label": day_label(meeting.day_of_week),
        "period_kind": meeting.period_kind,
        "period": meeting.period,
        "period_label": period_label(meeting.period_kind, meeting.period),
        "slot_key": meeting.slot_key,
    }


def list_meetings(offering: CourseOffering) -> list[CourseMeeting]:
    ensure_course_meeting_table()
    try:
        rows = list(
            CourseMeeting.objects.filter(offering=offering).order_by(
                "day_of_week", "period_kind", "period", "pk"
            )
        )
    except (OperationalError, ProgrammingError):
        return []
    if rows:
        return rows
    # Legacy fallback: denormalized fields only
    meeting, _ = CourseMeeting.objects.get_or_create(
        offering=offering,
        day_of_week=offering.day_of_week,
        period_kind=offering.period_kind,
        period=offering.period,
    )
    return [meeting]


def sync_offering_primary_schedule(offering: CourseOffering) -> None:
    """代表曜日時限を最初のミーティングに合わせる。"""
    meeting = (
        CourseMeeting.objects.filter(offering=offering)
        .order_by("day_of_week", "period_kind", "period", "pk")
        .first()
    )
    if meeting is None:
        return
    updates = []
    if offering.day_of_week != meeting.day_of_week:
        offering.day_of_week = meeting.day_of_week
        updates.append("day_of_week")
    if offering.period_kind != meeting.period_kind:
        offering.period_kind = meeting.period_kind
        updates.append("period_kind")
    if offering.period != meeting.period:
        offering.period = meeting.period
        updates.append("period")
    if updates:
        updates.append("updated_at")
        offering.save(update_fields=updates)


def normalize_meeting_specs(
    meetings: Iterable[dict[str, Any]] | None,
    *,
    day_of_week: int | None = None,
    period: int | None = None,
    period_kind: str | None = None,
) -> list[dict[str, Any]]:
    specs: list[dict[str, Any]] = []
    if meetings:
        for raw in meetings:
            specs.append(
                {
                    "day_of_week": int(raw["day_of_week"]),
                    "period": int(raw["period"]),
                    "period_kind": (
                        raw.get("period_kind") or CourseOffering.PeriodKind.PERIOD
                    ),
                }
            )
    elif day_of_week is not None and period is not None:
        specs.append(
            {
                "day_of_week": int(day_of_week),
                "period": int(period),
                "period_kind": period_kind or CourseOffering.PeriodKind.PERIOD,
            }
        )
    # dedupe
    seen: set[tuple] = set()
    unique: list[dict[str, Any]] = []
    for spec in specs:
        key = (spec["day_of_week"], spec["period_kind"], spec["period"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(spec)
    if not unique:
        raise ValueError("meetings_required")
    return unique


@transaction.atomic
def ensure_meetings_for_offering(
    offering: CourseOffering,
    specs: list[dict[str, Any]],
) -> list[CourseMeeting]:
    ensure_course_meeting_table()
    created: list[CourseMeeting] = []
    for spec in specs:
        meeting, _ = CourseMeeting.objects.get_or_create(
            offering=offering,
            day_of_week=spec["day_of_week"],
            period_kind=spec["period_kind"],
            period=spec["period"],
        )
        created.append(meeting)
    sync_offering_primary_schedule(offering)
    return list_meetings(offering)


def find_meeting_for_slot_key(
    offering: CourseOffering, slot_key: str
) -> CourseMeeting | None:
    for meeting in list_meetings(offering):
        if meeting.slot_key == slot_key:
            return meeting
    return None


def find_meeting_for_weekday(
    offering: CourseOffering, weekday: int
) -> CourseMeeting | None:
    if weekday > 5:
        return None
    return (
        CourseMeeting.objects.filter(offering=offering, day_of_week=weekday)
        .order_by("period_kind", "period", "pk")
        .first()
    )
