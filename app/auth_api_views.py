"""JSON API for React auth (Phase 9) — session/CSRF based, no JWT."""

from __future__ import annotations

import json
import logging

from django.http import HttpRequest, JsonResponse
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from . import auth_api_services as svc

logger = logging.getLogger(__name__)


def _parse_json(request: HttpRequest) -> dict:
    if request.content_type and "application/json" in request.content_type:
        try:
            return json.loads(request.body.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            return {}
    # Form-encoded fallback (no password logging)
    return {k: request.POST.get(k) for k in request.POST.keys()}


def _json(payload: dict, status: int = 200) -> JsonResponse:
    return JsonResponse(payload, status=status)


@ensure_csrf_cookie
@require_GET
def api_v1_auth_csrf(request: HttpRequest) -> JsonResponse:
    return _json({"ok": True, "me": svc.serialize_me(request)})


@require_GET
def api_v1_auth_me(request: HttpRequest) -> JsonResponse:
    return _json({"ok": True, "me": svc.serialize_me(request)})


@require_GET
def api_v1_auth_signup_meta(request: HttpRequest) -> JsonResponse:
    return _json(svc.signup_meta())


@require_POST
def api_v1_auth_login(request: HttpRequest) -> JsonResponse:
    data = _parse_json(request)
    # Never log password / email secrets
    logger.info("auth.login attempt")
    payload, status = svc.login_with_form(request, data)
    return _json(payload, status)


@require_POST
def api_v1_auth_logout(request: HttpRequest) -> JsonResponse:
    logger.info("auth.logout")
    return _json(svc.logout_session(request))


@require_POST
def api_v1_auth_browse(request: HttpRequest) -> JsonResponse:
    data = _parse_json(request)
    return _json(svc.enter_browse(request, data.get("next") or request.GET.get("next")))


@require_POST
def api_v1_auth_signup(request: HttpRequest) -> JsonResponse:
    data = _parse_json(request)
    logger.info("auth.signup attempt")
    payload, status = svc.signup_with_form(request, data)
    return _json(payload, status)


@require_http_methods(["GET", "POST"])
def api_v1_auth_verify(request: HttpRequest) -> JsonResponse:
    if request.method == "GET":
        return _json(svc.verify_status(request))
    data = _parse_json(request)
    logger.info("auth.verify_otp attempt")
    payload, status = svc.verify_signup(request, data)
    return _json(payload, status)


@require_POST
def api_v1_auth_verify_resend(request: HttpRequest) -> JsonResponse:
    logger.info("auth.verify_otp_resend")
    payload, status = svc.resend_signup_otp(request)
    return _json(payload, status)


@require_http_methods(["GET", "POST"])
def api_v1_auth_password_reset(request: HttpRequest) -> JsonResponse:
    if request.method == "GET":
        return _json(svc.password_reset_status(request))
    data = _parse_json(request)
    logger.info("auth.password_reset_request")
    payload, status = svc.password_reset_request(request, data)
    return _json(payload, status)


@require_POST
def api_v1_auth_password_reset_verify(request: HttpRequest) -> JsonResponse:
    data = _parse_json(request)
    logger.info("auth.password_reset_verify")
    payload, status = svc.password_reset_verify(request, data)
    return _json(payload, status)


@require_POST
def api_v1_auth_password_reset_resend(request: HttpRequest) -> JsonResponse:
    logger.info("auth.password_reset_resend")
    payload, status = svc.password_reset_resend(request)
    return _json(payload, status)


@require_POST
def api_v1_auth_password_reset_set(request: HttpRequest) -> JsonResponse:
    data = _parse_json(request)
    logger.info("auth.password_reset_set")
    payload, status = svc.password_reset_set(request, data)
    return _json(payload, status)
