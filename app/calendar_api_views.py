"""JSON API for calendar events (timetable tab calendar view)."""

from __future__ import annotations

import json

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from .calendar_services import (
    build_month_payload,
    create_event,
    ensure_calendar_event_table,
    serialize_calendar_event,
    update_event,
)
from .models import CalendarEvent


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


def _parse_year_month(request: HttpRequest) -> tuple[int, int] | JsonResponse:
    try:
        year = int(request.GET.get("year") or 0)
        month = int(request.GET.get("month") or 0)
    except (TypeError, ValueError):
        return _json_error("year_month_invalid")
    if year < 2000 or year > 2100 or month < 1 or month > 12:
        return _json_error("year_month_invalid")
    return year, month


@login_required
@require_GET
def api_v1_calendar_events(request: HttpRequest) -> JsonResponse:
    ensure_calendar_event_table()
    parsed = _parse_year_month(request)
    if isinstance(parsed, JsonResponse):
        return parsed
    year, month = parsed
    return JsonResponse(build_month_payload(request.user, year, month))


@login_required
@require_POST
def api_v1_calendar_event_create(request: HttpRequest) -> JsonResponse:
    ensure_calendar_event_table()
    data = _parse_json(request)
    try:
        event = create_event(request.user, data)
    except ValueError as exc:
        return _json_error(str(exc) or "create_failed")
    except Exception:
        return _json_error("create_failed", status=500)
    return JsonResponse(
        {"ok": True, "event": serialize_calendar_event(event)}, status=201
    )


@login_required
@require_http_methods(["POST", "PATCH"])
def api_v1_calendar_event_update(
    request: HttpRequest, event_pk: int
) -> JsonResponse:
    ensure_calendar_event_table()
    event = get_object_or_404(CalendarEvent, pk=event_pk, user=request.user)
    data = _parse_json(request)
    try:
        event = update_event(event, data)
    except ValueError as exc:
        return _json_error(str(exc) or "update_failed")
    except Exception:
        return _json_error("update_failed", status=500)
    return JsonResponse({"ok": True, "event": serialize_calendar_event(event)})


@login_required
@require_http_methods(["POST", "DELETE"])
def api_v1_calendar_event_delete(
    request: HttpRequest, event_pk: int
) -> JsonResponse:
    ensure_calendar_event_table()
    event = get_object_or_404(CalendarEvent, pk=event_pk, user=request.user)
    event.delete()
    return JsonResponse({"ok": True, "deleted": True, "id": event_pk})
