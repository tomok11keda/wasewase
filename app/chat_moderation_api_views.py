"""ChatMessage 運営削除への異議申し立て API。"""

from __future__ import annotations

import json

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_POST

from .models import ChatMessage
from .moderation_services import submit_chat_message_appeal


def _json_error(code: str, *, status: int = 400, **extra) -> JsonResponse:
    payload = {"ok": False, "error": code}
    payload.update(extra)
    return JsonResponse(payload, status=status)


def _parse_json(request: HttpRequest) -> dict:
    if request.content_type and "application/json" in request.content_type:
        try:
            data = json.loads(request.body.decode("utf-8") or "{}")
            return data if isinstance(data, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


@login_required
@require_POST
def api_v1_chat_message_appeal(request: HttpRequest, message_pk: int) -> JsonResponse:
    message = get_object_or_404(ChatMessage, pk=message_pk)
    data = _parse_json(request)
    explanation = data.get("explanation") or request.POST.get("explanation") or ""
    try:
        appeal = submit_chat_message_appeal(
            message=message,
            user=request.user,
            explanation=explanation,
        )
    except ValueError as exc:
        code = str(exc)
        status = 403 if code == "forbidden" else 400
        return _json_error(code, status=status)
    return JsonResponse(
        {
            "ok": True,
            "appeal_id": appeal.pk,
            "status": appeal.status,
            "message": "異議申し立てを受け付けました。運営が内容を確認します。",
        },
        status=201,
    )
