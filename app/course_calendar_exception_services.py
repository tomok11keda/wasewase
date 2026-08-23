"""授業カレンダー例外（特定日の時間割予定スキップ / 復元）。"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

from django.contrib.auth.base_user import AbstractBaseUser
from django.db import IntegrityError, connection, transaction
from django.db.utils import OperationalError, ProgrammingError

from .calendar_services import parse_date
from .models import (
    CourseCalendarException,
    CourseEnrollment,
    CourseOffering,
)

logger = logging.getLogger(__name__)


def ensure_course_calendar_exception_table() -> None:
    """本番で migration 前にテーブルが無い場合の修復。"""
    table = CourseCalendarException._meta.db_table
    try:
        with connection.cursor() as cursor:
            if table in connection.introspection.table_names(cursor):
                return
        with connection.schema_editor() as schema_editor:
            schema_editor.create_model(CourseCalendarException)
        logger.warning("Created missing %s table on startup", table)
    except (OperationalError, ProgrammingError) as exc:
        message = str(exc).lower()
        if "already exists" in message or "duplicate" in message:
            return
        logger.warning("CourseCalendarException table repair failed: %s", exc)
    except Exception as exc:
        logger.warning("CourseCalendarException table repair failed: %s", exc)


def serialize_course_calendar_exception(
    exc: CourseCalendarException,
) -> dict[str, Any]:
    offering = exc.offering
    return {
        "id": exc.pk,
        "offering_id": exc.offering_id,
        "date": exc.date.isoformat(),
        "status": exc.status,
        "offering_title": offering.title if offering else "",
        "instructor": offering.instructor if offering else "",
        "created_at": exc.created_at.isoformat() if exc.created_at else "",
        "updated_at": exc.updated_at.isoformat() if exc.updated_at else "",
    }


def _require_active_current_offering(
    user: AbstractBaseUser, offering_id: int
) -> CourseOffering:
    try:
        offering = CourseOffering.objects.select_related("course").get(
            pk=offering_id
        )
    except CourseOffering.DoesNotExist as exc:
        raise ValueError("offering_not_found") from exc

    if offering.status == CourseOffering.Status.HIDDEN:
        raise ValueError("offering_hidden")
    if offering.status == CourseOffering.Status.MERGED:
        raise ValueError("offering_merged")
    if offering.status != CourseOffering.Status.ACTIVE:
        raise ValueError("offering_inactive")

    enrolled = CourseEnrollment.objects.filter(
        user=user,
        offering=offering,
        role=CourseEnrollment.Role.CURRENT,
    ).exists()
    if not enrolled:
        raise ValueError("enrollment_required")
    return offering


def list_course_calendar_exceptions(
    user: AbstractBaseUser,
    *,
    year: int | None = None,
    month: int | None = None,
    status: str | None = None,
) -> list[CourseCalendarException]:
    ensure_course_calendar_exception_table()
    try:
        qs = CourseCalendarException.objects.filter(user=user).select_related(
            "offering"
        )
        if status:
            qs = qs.filter(status=status)
        else:
            qs = qs.filter(status=CourseCalendarException.Status.SKIPPED)
        if year is not None and month is not None:
            qs = qs.filter(date__year=year, date__month=month)
        return list(qs.order_by("-date", "-pk"))
    except (OperationalError, ProgrammingError) as exc:
        logger.warning("list_course_calendar_exceptions failed: %s", exc)
        return []


def list_skipped_for_month(
    user: AbstractBaseUser, year: int, month: int
) -> list[dict[str, Any]]:
    rows = list_course_calendar_exceptions(
        user,
        year=year,
        month=month,
        status=CourseCalendarException.Status.SKIPPED,
    )
    return [serialize_course_calendar_exception(row) for row in rows]


@transaction.atomic
def create_course_calendar_exception(
    user: AbstractBaseUser,
    *,
    offering_id: int,
    date_raw: str,
    status: str = CourseCalendarException.Status.SKIPPED,
) -> CourseCalendarException:
    ensure_course_calendar_exception_table()
    offering = _require_active_current_offering(user, int(offering_id))
    day = parse_date(date_raw)
    if day is None:
        raise ValueError("date_invalid")
    # Asia/Tokyo の calendar date として扱う（DateField、時刻なし）
    if day.year < 2000 or day.year > 2100:
        raise ValueError("date_invalid")

    status_value = (status or "").strip().lower() or CourseCalendarException.Status.SKIPPED
    if status_value != CourseCalendarException.Status.SKIPPED:
        raise ValueError("status_invalid")

    try:
        exc, created = CourseCalendarException.objects.get_or_create(
            user=user,
            offering=offering,
            date=day,
            defaults={"status": status_value},
        )
    except IntegrityError as err:
        raise ValueError("duplicate_exception") from err

    if not created:
        if exc.status != status_value:
            exc.status = status_value
            exc.save(update_fields=["status", "updated_at"])
        # idempotent: already skipped
        return exc
    return exc


@transaction.atomic
def delete_course_calendar_exception(
    user: AbstractBaseUser, exception_id: int
) -> dict[str, Any]:
    ensure_course_calendar_exception_table()
    try:
        exc = CourseCalendarException.objects.select_related("offering").get(
            pk=exception_id
        )
    except CourseCalendarException.DoesNotExist as err:
        raise ValueError("not_found") from err
    if exc.user_id != user.pk:
        raise ValueError("forbidden")
    payload = serialize_course_calendar_exception(exc)
    exc.delete()
    return payload
