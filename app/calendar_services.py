"""カレンダー予定の永続化・シリアライズ。"""

from __future__ import annotations

import logging
from datetime import date, datetime, time
from typing import Any

from django.contrib.auth.models import AbstractBaseUser
from django.db import connection
from django.db.utils import OperationalError, ProgrammingError

from .models import CalendarEvent

logger = logging.getLogger(__name__)

CATEGORY_LABELS = {choice.value: choice.label for choice in CalendarEvent.Category}

VALID_CATEGORIES = set(CATEGORY_LABELS)


def ensure_calendar_event_table() -> None:
    """本番 DB にカレンダー予定表が無い場合に作成する。"""
    table = CalendarEvent._meta.db_table
    try:
        with connection.cursor() as cursor:
            if table in connection.introspection.table_names(cursor):
                return
        with connection.schema_editor() as schema_editor:
            schema_editor.create_model(CalendarEvent)
        logger.warning("Created missing %s table on startup", table)
    except (OperationalError, ProgrammingError) as exc:
        message = str(exc).lower()
        if "already exists" in message or "duplicate" in message:
            return
        logger.warning("CalendarEvent table repair failed: %s", exc)
    except Exception as exc:
        logger.warning("CalendarEvent table repair failed: %s", exc)


def _time_to_str(value: time | None) -> str:
    if value is None:
        return ""
    return value.strftime("%H:%M")


def serialize_calendar_event(event: CalendarEvent) -> dict[str, Any]:
    return {
        "id": event.pk,
        "title": event.title,
        "date": event.date.isoformat(),
        "start_time": _time_to_str(event.start_time),
        "end_time": _time_to_str(event.end_time),
        "memo": event.memo or "",
        "category": event.category,
        "category_label": CATEGORY_LABELS.get(
            event.category, "その他"
        ),
        "updated_at": event.updated_at.isoformat() if event.updated_at else "",
    }


def parse_date(raw: str | None) -> date | None:
    text = (raw or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def parse_time(raw: str | None) -> time | None:
    text = (raw or "").strip()
    if not text:
        return None
    for fmt in ("%H:%M", "%H:%M:%S"):
        try:
            return datetime.strptime(text, fmt).time()
        except ValueError:
            continue
    return None


def normalize_category(raw: str | None) -> str:
    value = (raw or "").strip().lower()
    if value in VALID_CATEGORIES:
        return value
    return CalendarEvent.Category.OTHER


def list_events_for_month(
    user: AbstractBaseUser, year: int, month: int
) -> list[CalendarEvent]:
    try:
        return list(
            CalendarEvent.objects.filter(
                user=user, date__year=year, date__month=month
            ).order_by("date", "start_time", "pk")
        )
    except (OperationalError, ProgrammingError) as exc:
        logger.warning("list_events_for_month failed: %s", exc)
        return []


def list_events_for_date(
    user: AbstractBaseUser, day: date
) -> list[CalendarEvent]:
    try:
        return list(
            CalendarEvent.objects.filter(user=user, date=day).order_by(
                "start_time", "pk"
            )
        )
    except (OperationalError, ProgrammingError) as exc:
        logger.warning("list_events_for_date failed: %s", exc)
        return []


def build_month_payload(
    user: AbstractBaseUser, year: int, month: int
) -> dict[str, Any]:
    events = list_events_for_month(user, year, month)
    by_date: dict[str, list[dict[str, Any]]] = {}
    for event in events:
        key = event.date.isoformat()
        by_date.setdefault(key, []).append(serialize_calendar_event(event))
    dots: dict[str, dict[str, Any]] = {}
    for key, rows in by_date.items():
        titles = [r["title"] for r in rows[:2]]
        dots[key] = {
            "count": len(rows),
            "titles": titles,
            "extra": max(0, len(rows) - len(titles)),
        }
    return {
        "ok": True,
        "year": year,
        "month": month,
        "events": [serialize_calendar_event(e) for e in events],
        "by_date": by_date,
        "dots": dots,
        "categories": [
            {"value": value, "label": label}
            for value, label in CATEGORY_LABELS.items()
        ],
    }


def create_event(
    user: AbstractBaseUser, data: dict[str, Any]
) -> CalendarEvent:
    title = (data.get("title") or "").strip()
    if not title:
        raise ValueError("title_required")
    day = parse_date(data.get("date"))
    if day is None:
        raise ValueError("date_invalid")
    start = parse_time(data.get("start_time"))
    end = parse_time(data.get("end_time"))
    if start and end and end < start:
        raise ValueError("time_range_invalid")
    return CalendarEvent.objects.create(
        user=user,
        title=title[:120],
        date=day,
        start_time=start,
        end_time=end,
        memo=(data.get("memo") or "").strip()[:2000],
        category=normalize_category(data.get("category")),
    )


def update_event(
    event: CalendarEvent, data: dict[str, Any]
) -> CalendarEvent:
    if "title" in data:
        title = (data.get("title") or "").strip()
        if not title:
            raise ValueError("title_required")
        event.title = title[:120]
    if "date" in data:
        day = parse_date(data.get("date"))
        if day is None:
            raise ValueError("date_invalid")
        event.date = day
    if "start_time" in data:
        event.start_time = parse_time(data.get("start_time"))
    if "end_time" in data:
        event.end_time = parse_time(data.get("end_time"))
    if event.start_time and event.end_time and event.end_time < event.start_time:
        raise ValueError("time_range_invalid")
    if "memo" in data:
        event.memo = (data.get("memo") or "").strip()[:2000]
    if "category" in data:
        event.category = normalize_category(data.get("category"))
    event.save()
    return event
