"""JSON API for React Profile / Search (Phase 7)."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_GET, require_POST

from .profile_api_services import (
    build_profile_payload,
    build_search_page_payload,
    list_profile_bookmarks,
    list_profile_posts,
    list_profile_products,
    toggle_block_for_api,
    toggle_follow_for_api,
)
from .follow_services import FollowForbidden

User = get_user_model()


def _json_error(message: str, *, status: int = 400, **extra) -> JsonResponse:
    payload = {"ok": False, "error": message}
    payload.update(extra)
    return JsonResponse(payload, status=status)


def _viewer(request: HttpRequest):
    return request.user if request.user.is_authenticated else None


@require_GET
def api_v1_profile_detail(request: HttpRequest, pk: int) -> JsonResponse:
    profile_user = get_object_or_404(
        User.objects.select_related("profile"), pk=pk
    )
    return JsonResponse(build_profile_payload(profile_user, _viewer(request)))


@require_GET
def api_v1_profile_posts(request: HttpRequest, pk: int) -> JsonResponse:
    profile_user = get_object_or_404(User, pk=pk)
    return JsonResponse(list_profile_posts(profile_user, _viewer(request)))


@require_GET
def api_v1_profile_products(request: HttpRequest, pk: int) -> JsonResponse:
    profile_user = get_object_or_404(User, pk=pk)
    return JsonResponse(list_profile_products(profile_user, _viewer(request)))


@require_GET
def api_v1_profile_bookmarks(request: HttpRequest, pk: int) -> HttpResponse:
    profile_user = get_object_or_404(User, pk=pk)
    viewer = _viewer(request)
    if viewer is None or viewer.pk != profile_user.pk:
        return _json_error("forbidden", status=403)
    return JsonResponse(list_profile_bookmarks(profile_user, viewer))


@login_required
@require_POST
def api_v1_profile_follow(request: HttpRequest, pk: int) -> JsonResponse:
    target = get_object_or_404(User, pk=pk)
    try:
        payload = toggle_follow_for_api(request.user, target)
    except FollowForbidden as exc:
        return _json_error(exc.code, status=403)
    except ValueError as exc:
        return _json_error(str(exc), status=400)
    return JsonResponse(payload)


@login_required
@require_POST
def api_v1_profile_block(request: HttpRequest, pk: int) -> JsonResponse:
    target = get_object_or_404(User, pk=pk)
    try:
        payload = toggle_block_for_api(request.user, target)
    except ValueError as exc:
        return _json_error(str(exc), status=400)
    return JsonResponse(payload)


@require_GET
def api_v1_search(request: HttpRequest) -> JsonResponse:
    """Classic /search/ tabs as JSON: tab=all|latest|users."""
    return JsonResponse(build_search_page_payload(request))
