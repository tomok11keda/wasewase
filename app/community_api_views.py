"""JSON API for React communities (Phase 4). Reuses community_services."""

from __future__ import annotations

import json

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from .community_api_services import (
    list_threads_payload,
    serialize_reply,
    serialize_thread_detail,
    serialize_thread_summary,
)
from .community_services import (
    can_delete_community_content,
    can_edit_community_reply,
    create_community_thread,
    create_thread_reply,
    get_community_for_new_thread,
    get_community_reply,
    get_community_thread,
    soft_remove_community_reply,
    soft_remove_community_thread,
    update_community_reply,
)
from .constants import FACULTY_CHOICES
from .forms import CommunityThreadForm, CommunityThreadReplyForm
from .models import Community


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


@require_http_methods(["GET", "POST"])
def api_v1_community_threads(request: HttpRequest) -> HttpResponse:
    if request.method == "GET":
        return JsonResponse(list_threads_payload(request))
    return api_v1_community_thread_create(request)


@login_required
@require_POST
def api_v1_community_thread_create(request: HttpRequest) -> HttpResponse:
    data = _parse_json(request)
    faculty_values = {value for value, _ in FACULTY_CHOICES}
    active_tag = (
        data.get("tag")
        or request.POST.get("tag", "")
        or request.GET.get("tag", "")
    )
    active_tag = str(active_tag).strip()
    if active_tag not in faculty_values:
        active_tag = ""

    community = get_community_for_new_thread(faculty=active_tag)
    if community is None:
        return _json_error("no_community", status=400)

    form = CommunityThreadForm(data if data else request.POST)
    if not form.is_valid():
        return _json_error(
            "validation_failed",
            status=400,
            errors=form.errors.get_json_data(),
        )

    thread = create_community_thread(
        community,
        request.user,
        form.cleaned_data["title"],
        form.cleaned_data["body"],
    )
    from django.db.models import Count, Q

    from .models import CommunityThread

    thread = (
        CommunityThread.objects.select_related(
            "author", "author__profile", "community"
        )
        .annotate(
            replies_count=Count(
                "replies",
                filter=Q(replies__is_removed=False),
                distinct=True,
            )
        )
        .get(pk=thread.pk)
    )
    return JsonResponse(
        {
            "ok": True,
            "thread": serialize_thread_summary(thread, request.user),
        },
        status=201,
    )


@require_GET
def api_v1_community_thread_detail(
    request: HttpRequest, slug: str, thread_pk: int
) -> JsonResponse:
    community = get_object_or_404(Community, slug=slug, is_active=True)
    thread = get_community_thread(community, thread_pk)
    viewer = request.user if request.user.is_authenticated else None
    return JsonResponse(
        {"ok": True, "thread": serialize_thread_detail(thread, viewer)}
    )


@login_required
@require_POST
def api_v1_community_thread_reply(
    request: HttpRequest, slug: str, thread_pk: int
) -> JsonResponse:
    community = get_object_or_404(Community, slug=slug, is_active=True)
    thread = get_community_thread(community, thread_pk)
    data = _parse_json(request)
    form = CommunityThreadReplyForm(data if data else request.POST)
    if not form.is_valid():
        return _json_error(
            "validation_failed",
            status=400,
            errors=form.errors.get_json_data(),
        )
    reply = create_thread_reply(
        thread, request.user, form.cleaned_data["body"]
    )
    reply = type(reply).objects.select_related(
        "author", "author__profile"
    ).get(pk=reply.pk)
    return JsonResponse(
        {
            "ok": True,
            "reply": serialize_reply(reply, request.user),
            "visible_reply_count": thread.replies.filter(is_removed=False).count(),
        },
        status=201,
    )


@login_required
@require_http_methods(["DELETE", "POST"])
def api_v1_community_thread_delete(
    request: HttpRequest, slug: str, thread_pk: int
) -> JsonResponse:
    community = get_object_or_404(Community, slug=slug, is_active=True)
    thread = get_community_thread(community, thread_pk)
    if not can_delete_community_content(request.user, thread.author_id):
        return _json_error("forbidden", status=403)
    soft_remove_community_thread(thread)
    return JsonResponse({"ok": True})


@login_required
@require_http_methods(["DELETE", "POST"])
def api_v1_community_reply_delete(
    request: HttpRequest, slug: str, thread_pk: int, reply_pk: int
) -> JsonResponse:
    community = get_object_or_404(Community, slug=slug, is_active=True)
    reply = get_community_reply(community, thread_pk, reply_pk)
    if reply.is_removed:
        return JsonResponse({"ok": True, "already_removed": True})
    if not can_delete_community_content(request.user, reply.author_id):
        return _json_error("forbidden", status=403)
    soft_remove_community_reply(reply)
    return JsonResponse({"ok": True})


@login_required
@require_http_methods(["POST", "PATCH"])
def api_v1_community_reply_edit(
    request: HttpRequest, slug: str, thread_pk: int, reply_pk: int
) -> JsonResponse:
    community = get_object_or_404(Community, slug=slug, is_active=True)
    reply = get_community_reply(community, thread_pk, reply_pk)
    if not can_edit_community_reply(request.user, reply):
        return _json_error("forbidden", status=403)
    data = _parse_json(request)
    form = CommunityThreadReplyForm(data if data else request.POST)
    if not form.is_valid():
        return _json_error(
            "validation_failed",
            status=400,
            errors=form.errors.get_json_data(),
        )
    update_community_reply(reply, form.cleaned_data["body"])
    reply.refresh_from_db()
    return JsonResponse(
        {"ok": True, "reply": serialize_reply(reply, request.user)}
    )
