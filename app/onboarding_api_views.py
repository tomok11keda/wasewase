"""JSON API for post-OTP onboarding."""

from __future__ import annotations

import json

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_GET, require_POST

from . import onboarding_services as svc


def _json_error(message: str, *, status: int = 400, **extra) -> JsonResponse:
    payload = {"ok": False, "error": message}
    payload.update(extra)
    return JsonResponse(payload, status=status)


def _parse_json(request: HttpRequest) -> dict:
    if not request.body:
        return {}
    try:
        data = json.loads(request.body.decode("utf-8"))
    except (TypeError, ValueError, UnicodeDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


@login_required
@require_GET
def api_v1_onboarding(request: HttpRequest) -> JsonResponse:
    return JsonResponse(svc.onboarding_payload(request.user))


@login_required
@require_POST
def api_v1_onboarding_profile(request: HttpRequest) -> JsonResponse:
    if request.content_type and "multipart/form-data" in request.content_type:
        name = request.POST.get("name") or ""
        username = request.POST.get("username") or ""
        department = request.POST.get("department") or request.POST.get("faculty") or ""
        avatar = request.FILES.get("avatar")
    else:
        data = _parse_json(request)
        name = data.get("name") or ""
        username = data.get("username") or ""
        department = data.get("department") or data.get("faculty") or ""
        avatar = request.FILES.get("avatar")
    payload = svc.save_onboarding_profile(
        request.user,
        name=str(name),
        username=str(username),
        department=str(department),
        avatar=avatar,
    )
    status = 200 if payload.get("ok") else 400
    return JsonResponse(payload, status=status)


@login_required
@require_GET
def api_v1_onboarding_suggestions(request: HttpRequest) -> JsonResponse:
    if not svc.needs_onboarding(request.user):
        return JsonResponse(svc.list_onboarding_suggestions(request.user))
    profile = svc.get_or_create_profile(request.user)
    if profile.onboarding_step == svc.ONBOARDING_STEP_PROFILE:
        return _json_error("profile_incomplete", status=400, step=profile.onboarding_step)
    return JsonResponse(svc.list_onboarding_suggestions(request.user))


@login_required
@require_POST
def api_v1_onboarding_follow_step(request: HttpRequest) -> JsonResponse:
    payload = svc.advance_follow_step(request.user)
    status = 200 if payload.get("ok") else 400
    return JsonResponse(payload, status=status)


@login_required
@require_POST
def api_v1_onboarding_complete(request: HttpRequest) -> JsonResponse:
    payload = svc.complete_onboarding(request.user)
    status = 200 if payload.get("ok") else 400
    return JsonResponse(payload, status=status)
