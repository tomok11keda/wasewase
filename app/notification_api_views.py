"""JSON API for React notifications (Phase 9)."""

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_GET, require_POST

from .notification_api_services import build_notifications_payload
from .notification_services import (
    get_unread_notification_count,
    mark_all_notifications_read,
)


@login_required
@require_GET
def api_v1_notifications_list(request: HttpRequest) -> JsonResponse:
    mark = request.GET.get("mark_read", "1") not in ("0", "false", "False")
    return JsonResponse(build_notifications_payload(request.user, mark_read=mark))


@login_required
@require_GET
def api_v1_notifications_unread(request: HttpRequest) -> JsonResponse:
    return JsonResponse(
        {"ok": True, "unread_count": get_unread_notification_count(request.user)}
    )


@login_required
@require_POST
def api_v1_notifications_mark_read(request: HttpRequest) -> JsonResponse:
    marked = mark_all_notifications_read(request.user)
    return JsonResponse(
        {"ok": True, "unread_count": 0, "marked_count": marked}
    )
