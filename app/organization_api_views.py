"""JSON API for organization profiles (Phase 1-B)."""

from __future__ import annotations

from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_GET, require_http_methods

from .organization_api_services import (
    OrganizationApiError,
    build_organization_profile_payload,
    get_organization_by_slug,
    list_managed_organizations_payload,
    parse_organization_update_request,
    update_organization_profile,
)
from .organization_services import (
    can_manage_organization,
    can_view_organization_profile,
)
from .rate_limit_services import allow_organization_profile_update


def _json_error(error: str, *, status: int = 400, **extra) -> JsonResponse:
    payload = {"ok": False, "error": error}
    payload.update(extra)
    return JsonResponse(payload, status=status)


def _viewer(request: HttpRequest):
    return request.user if request.user.is_authenticated else None


def _error_response(exc: OrganizationApiError) -> JsonResponse:
    return _json_error(exc.error, status=exc.status, **exc.extra)


@require_GET
def api_v1_me_organizations(request: HttpRequest) -> JsonResponse:
    if not request.user.is_authenticated:
        return _json_error(
            "unauthorized",
            status=401,
            message="authentication_required",
        )
    try:
        payload = list_managed_organizations_payload(request.user)
    except OrganizationApiError as exc:
        return _error_response(exc)
    return JsonResponse(payload)


@require_http_methods(["GET", "PATCH"])
def api_v1_organization_detail(request: HttpRequest, slug: str) -> JsonResponse:
    if request.method == "PATCH":
        return _update_organization_detail(request, slug)
    return _get_organization_detail(request, slug)


def _get_organization_detail(request: HttpRequest, slug: str) -> JsonResponse:
    organization = get_organization_by_slug(slug)
    try:
        payload = build_organization_profile_payload(organization, _viewer(request))
    except OrganizationApiError as exc:
        return _error_response(exc)
    return JsonResponse(payload)


def _update_organization_detail(request: HttpRequest, slug: str) -> JsonResponse:
    if not request.user.is_authenticated:
        return _json_error(
            "unauthorized",
            status=401,
            message="authentication_required",
        )

    organization = get_organization_by_slug(slug)
    if organization is None or not can_view_organization_profile(
        request.user, organization
    ):
        return _json_error("not_found", status=404)
    if not can_manage_organization(request.user, organization):
        return _json_error("forbidden", status=403)
    if not allow_organization_profile_update(request.user):
        return _json_error("rate_limited", status=429)

    try:
        fields = parse_organization_update_request(request)
        payload = update_organization_profile(organization, request.user, fields)
    except OrganizationApiError as exc:
        return _error_response(exc)
    return JsonResponse(payload)
