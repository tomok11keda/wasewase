"""授業欠席記録（日付単位）。Offering 単位で共通。"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any

from django.contrib.auth.base_user import AbstractBaseUser
from django.db import IntegrityError, connection, transaction
from django.db.utils import OperationalError, ProgrammingError
from django.utils import timezone

from .calendar_services import parse_date
from .course_meeting_services import (
    find_meeting_for_weekday,
    list_meetings,
    serialize_meeting,
)
from .models import (
    CourseAttendanceRecord,
    CourseCalendarException,
    CourseEnrollment,
    CourseOffering,
)

logger = logging.getLogger(__name__)

_SUGGEST_WEEKS = 16


def ensure_course_attendance_record_table() -> None:
    table = CourseAttendanceRecord._meta.db_table
    try:
        with connection.cursor() as cursor:
            if table in connection.introspection.table_names(cursor):
                return
        with connection.schema_editor() as schema_editor:
            schema_editor.create_model(CourseAttendanceRecord)
        logger.warning("Created missing %s table on startup", table)
    except (OperationalError, ProgrammingError) as exc:
        message = str(exc).lower()
        if "already exists" in message or "duplicate" in message:
            return
        logger.warning("CourseAttendanceRecord table repair failed: %s", exc)
    except Exception as exc:
        logger.warning("CourseAttendanceRecord table repair failed: %s", exc)


def serialize_attendance_record(row: CourseAttendanceRecord) -> dict[str, Any]:
    from .course_services import day_label, period_label

    offering = row.offering
    meeting = find_meeting_for_weekday(offering, row.date.weekday()) if offering else None
    return {
        "id": row.pk,
        "offering_id": row.offering_id,
        "date": row.date.isoformat(),
        "status": row.status,
        "offering_title": offering.title if offering else "",
        "day_of_week": meeting.day_of_week if meeting else None,
        "day_label": day_label(meeting.day_of_week) if meeting else "",
        "period_label": period_label(meeting.period_kind, meeting.period)
        if meeting
        else "",
        "created_at": row.created_at.isoformat() if row.created_at else "",
        "updated_at": row.updated_at.isoformat() if row.updated_at else "",
    }


def user_can_view_attendance(
    user: AbstractBaseUser, offering: CourseOffering
) -> bool:
    return CourseEnrollment.objects.filter(
        user=user, offering=offering
    ).exists()


def user_can_record_attendance(
    user: AbstractBaseUser, offering: CourseOffering
) -> bool:
    return CourseEnrollment.objects.filter(
        user=user,
        offering=offering,
        role=CourseEnrollment.Role.CURRENT,
    ).exists()


def _calendar_skipped(
    user: AbstractBaseUser, offering: CourseOffering, day: date
) -> bool:
    try:
        return CourseCalendarException.objects.filter(
            user=user,
            offering=offering,
            date=day,
            status=CourseCalendarException.Status.SKIPPED,
        ).exists()
    except (OperationalError, ProgrammingError):
        return False


def list_attendance_records(
    user: AbstractBaseUser, offering: CourseOffering
) -> list[CourseAttendanceRecord]:
    ensure_course_attendance_record_table()
    if not user_can_view_attendance(user, offering):
        return []
    try:
        return list(
            CourseAttendanceRecord.objects.filter(
                user=user,
                offering=offering,
                status=CourseAttendanceRecord.Status.ABSENT,
            )
            .select_related("offering")
            .order_by("-date", "-pk")
        )
    except (OperationalError, ProgrammingError) as exc:
        logger.warning("list_attendance_records failed: %s", exc)
        return []


def absence_count(user: AbstractBaseUser, offering: CourseOffering) -> int:
    return len(list_attendance_records(user, offering))


def suggest_meeting_dates(
    user: AbstractBaseUser | None,
    offering: CourseOffering,
    *,
    today: date | None = None,
    weeks: int = _SUGGEST_WEEKS,
) -> list[str]:
    today = today or timezone.localdate()
    weekdays = sorted({m.day_of_week for m in list_meetings(offering)})
    if not weekdays:
        weekdays = [offering.day_of_week]
    skipped: set[str] = set()
    if user is not None:
        try:
            skipped = {
                row.date.isoformat()
                for row in CourseCalendarException.objects.filter(
                    user=user,
                    offering=offering,
                    status=CourseCalendarException.Status.SKIPPED,
                    date__gte=today - timedelta(weeks=weeks),
                    date__lte=today,
                ).only("date")
            }
        except (OperationalError, ProgrammingError):
            skipped = set()
    start = today - timedelta(weeks=weeks)
    candidates: list[str] = []
    cursor = today
    while cursor >= start:
        if cursor.weekday() in weekdays:
            key = cursor.isoformat()
            if key not in skipped:
                candidates.append(key)
        cursor -= timedelta(days=1)
    return candidates


def build_attendance_payload(
    user: AbstractBaseUser, offering: CourseOffering
) -> dict[str, Any] | None:
    ensure_course_attendance_record_table()
    if not user_can_view_attendance(user, offering):
        return None
    rows = list_attendance_records(user, offering)
    can_record = user_can_record_attendance(user, offering)
    return {
        "absence_count": len(rows),
        "can_record": can_record,
        "records": [serialize_attendance_record(r) for r in rows],
        "meeting_dates": suggest_meeting_dates(user, offering)
        if can_record
        else [],
        "meetings": [serialize_meeting(m) for m in list_meetings(offering)],
    }


@transaction.atomic
def create_attendance_record(
    user: AbstractBaseUser,
    *,
    offering_id: int,
    date_raw: str,
    status: str = CourseAttendanceRecord.Status.ABSENT,
) -> CourseAttendanceRecord:
    ensure_course_attendance_record_table()
    try:
        offering = CourseOffering.objects.select_related("course").get(
            pk=int(offering_id)
        )
    except CourseOffering.DoesNotExist as exc:
        raise ValueError("offering_not_found") from exc

    if offering.status == CourseOffering.Status.HIDDEN:
        raise ValueError("offering_hidden")
    if offering.status == CourseOffering.Status.MERGED:
        raise ValueError("offering_merged")
    if offering.status != CourseOffering.Status.ACTIVE:
        raise ValueError("offering_inactive")

    day = parse_date(date_raw)
    if day is None:
        raise ValueError("date_invalid")
    if day.year < 2000 or day.year > 2100:
        raise ValueError("date_invalid")
    today = timezone.localdate()
    if day > today:
        raise ValueError("date_in_future")

    meeting = find_meeting_for_weekday(offering, day.weekday())
    if meeting is None:
        raise ValueError("date_not_meeting_day")

    if not user_can_record_attendance(user, offering):
        if user_can_view_attendance(user, offering):
            raise ValueError("current_enrollment_required")
        raise ValueError("enrollment_required")

    if _calendar_skipped(user, offering, day):
        raise ValueError("date_calendar_skipped")

    status_value = (
        (status or "").strip().lower() or CourseAttendanceRecord.Status.ABSENT
    )
    if status_value != CourseAttendanceRecord.Status.ABSENT:
        raise ValueError("status_invalid")

    try:
        row, _created = CourseAttendanceRecord.objects.get_or_create(
            user=user,
            offering=offering,
            date=day,
            defaults={"status": status_value},
        )
    except IntegrityError as err:
        raise ValueError("duplicate_attendance") from err
    return row


@transaction.atomic
def delete_attendance_record(
    user: AbstractBaseUser, record_id: int
) -> dict[str, Any]:
    ensure_course_attendance_record_table()
    try:
        row = CourseAttendanceRecord.objects.select_related("offering").get(
            pk=record_id
        )
    except CourseAttendanceRecord.DoesNotExist as err:
        raise ValueError("not_found") from err
    if row.user_id != user.pk:
        raise ValueError("forbidden")
    payload = serialize_attendance_record(row)
    row.delete()
    return payload
