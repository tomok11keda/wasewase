"""JSON API for linked personal profiles."""

from __future__ import annotations

import json

from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from .account_deletion_services import SuperuserDeletionDenied
from .account_identity_services import (
    AccountIdentityError,
    create_linked_profile,
    delete_current_linked_profile,
    delete_entire_identity,
    serialize_linked_profiles_payload,
    switch_linked_profile,
)
from .auth_api_services import serialize_me


def _json_error(error: str, *, status: int = 400, **extra) -> JsonResponse:
    payload = {"ok": False, "error": error}
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


def _error_response(exc: AccountIdentityError) -> JsonResponse:
    return _json_error(exc.code, status=exc.status, message=exc.message)


@login_required
@require_GET
def api_v1_me_linked_profiles(request: HttpRequest) -> JsonResponse:
    return JsonResponse(serialize_linked_profiles_payload(request.user))


@login_required
@require_POST
def api_v1_me_linked_profiles_create(request: HttpRequest) -> JsonResponse:
    data = _parse_json(request)
    try:
        alt = create_linked_profile(
            request.user,
            username=str(data.get("username") or ""),
            display_name=str(data.get("display_name") or data.get("name") or ""),
        )
        switch_linked_profile(request, alt.pk)
    except AccountIdentityError as exc:
        return _error_response(exc)
    payload = serialize_linked_profiles_payload(request.user)
    payload["me"] = serialize_me(request)
    return JsonResponse(payload)


@login_required
@require_POST
def api_v1_me_linked_profiles_switch(request: HttpRequest) -> JsonResponse:
    data = _parse_json(request)
    try:
        switch_linked_profile(request, data.get("user_id"))
    except AccountIdentityError as exc:
        return _error_response(exc)
    payload = serialize_linked_profiles_payload(request.user)
    payload["me"] = serialize_me(request)
    return JsonResponse(payload)


@login_required
@require_http_methods(["POST", "DELETE"])
def api_v1_me_linked_profiles_delete(request: HttpRequest) -> JsonResponse:
    data = _parse_json(request)
    entire = bool(data.get("entire_identity"))
    try:
        if entire:
            delete_entire_identity(request)
            remaining = None
        else:
            remaining = delete_current_linked_profile(request)
    except SuperuserDeletionDenied:
        return _json_error("superuser", status=403, message="管理者は削除できません。")
    except AccountIdentityError as exc:
        return _error_response(exc)
    if remaining is None:
        logout(request)
        return JsonResponse({"ok": True, "deleted": True, "me": serialize_me(request)})
    payload = serialize_linked_profiles_payload(remaining)
    payload["deleted"] = True
    payload["me"] = serialize_me(request)
    return JsonResponse(payload)
