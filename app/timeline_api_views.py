"""JSON API views for React timeline (Phase 3). Reuses classic board services."""

from __future__ import annotations

import json

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from .board_services import (
    get_quotable_post,
    notify_timeline_post_author,
    timeline_post_link,
)
from .bookmark_services import BookmarkServiceError, toggle_bookmark
from .forms import TimelineCommentForm, TimelinePostForm
from .media_services import compose_save_error_message
from .mention_services import notify_mentions
from .models import Comment, Notification, TimelineLike, TimelinePost
from .services import get_user_faculty
from .timeline_api_services import (
    list_timeline_page,
    save_timeline_post_instance,
    serialize_comment,
    serialize_timeline_post,
)


def _viewer(request: HttpRequest):
    return request.user if request.user.is_authenticated else None


def _json_error(message: str, *, status: int = 400, **extra) -> JsonResponse:
    payload = {"ok": False, "error": message}
    payload.update(extra)
    return JsonResponse(payload, status=status)


def _parse_offset(request: HttpRequest) -> int | None:
    raw = request.GET.get("offset")
    if raw is None or raw == "":
        return None
    try:
        return max(0, int(raw))
    except (TypeError, ValueError):
        return 0


@require_http_methods(["GET", "POST"])
def api_v1_timeline_collection(request: HttpRequest) -> HttpResponse:
    if request.method == "GET":
        return api_v1_timeline_list(request)
    return api_v1_timeline_create(request)


@require_GET
def api_v1_timeline_list(request: HttpRequest) -> JsonResponse:
    """GET /api/v1/timeline/?feed=&q=&faculty=&tag=&offset= """
    offset = _parse_offset(request)
    payload = list_timeline_page(request, offset=offset)
    feed = payload.get("feed", "all")
    payload["feed_following_unauthenticated"] = (
        feed == "following" and not request.user.is_authenticated
    )
    return JsonResponse(payload)


@login_required
@require_POST
def api_v1_timeline_create(request: HttpRequest) -> HttpResponse:
    """POST multipart: body, image?, quoted_post_id?"""
    form = TimelinePostForm(request.POST, request.FILES)
    if not form.is_valid():
        return _json_error(
            "validation_failed",
            status=400,
            errors=form.errors.get_json_data(),
        )
    post = form.save(commit=False)
    post.author = request.user
    faculty = get_user_faculty(request.user)
    if not post.faculty and faculty:
        post.faculty = faculty
    try:
        save_timeline_post_instance(post)
    except Exception as exc:
        return _json_error(compose_save_error_message(exc), status=500)
    link = timeline_post_link(post)
    notify_mentions(body=post.body, actor=request.user, link=link)
    # Re-fetch with relations for serializer
    post = (
        TimelinePost.objects.select_related(
            "author",
            "author__profile",
            "quoted_post",
            "quoted_post__author",
            "quoted_post__author__profile",
        )
        .prefetch_related("comments__author")
        .get(pk=post.pk)
    )
    post.user_has_liked = False
    post.user_has_bookmarked = False
    return JsonResponse(
        {"ok": True, "post": serialize_timeline_post(post, request.user)},
        status=201,
    )


@login_required
@require_POST
def api_v1_timeline_like(request: HttpRequest, pk: int) -> JsonResponse:
    post = get_object_or_404(TimelinePost, pk=pk, is_removed=False)
    like, created = TimelineLike.objects.get_or_create(
        timeline_post=post,
        user=request.user,
    )
    if created:
        post.like_count = int(post.like_count or 0) + 1
        post.save(update_fields=["like_count"])
        notify_timeline_post_author(
            post,
            request.user,
            f"{request.user.username}さんがあなたの投稿にいいねしました",
        )
        liked = True
    else:
        like.delete()
        post.like_count = max(0, int(post.like_count or 0) - 1)
        post.save(update_fields=["like_count"])
        liked = False
    return JsonResponse(
        {"ok": True, "liked": liked, "like_count": post.like_count}
    )


@login_required
@require_POST
def api_v1_timeline_bookmark(request: HttpRequest, pk: int) -> JsonResponse:
    post = get_object_or_404(TimelinePost, pk=pk, is_removed=False)
    try:
        bookmarked = toggle_bookmark(request.user, post.pk)
    except BookmarkServiceError:
        return _json_error("bookmark_unavailable", status=503)
    return JsonResponse({"ok": True, "bookmarked": bookmarked})


@login_required
@require_POST
def api_v1_timeline_comment(request: HttpRequest, pk: int) -> JsonResponse:
    post = get_object_or_404(TimelinePost, pk=pk, is_removed=False)
    if request.content_type and "application/json" in request.content_type:
        try:
            data = json.loads(request.body.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            return _json_error("invalid_json")
        form = TimelineCommentForm(data)
    else:
        form = TimelineCommentForm(request.POST)
    if not form.is_valid():
        return _json_error(
            "validation_failed",
            status=400,
            errors=form.errors.get_json_data(),
        )
    comment = form.save(commit=False)
    comment.timeline_post = post
    comment.author = request.user
    comment.save()
    link = timeline_post_link(post)
    if post.author_id and post.author_id != request.user.id:
        Notification.objects.create(
            recipient=post.author,
            message=(
                f"「{request.user.username}さんが"
                "あなたの投稿にコメントしました」"
            ),
            link=link,
        )
    notify_mentions(
        body=comment.body,
        actor=request.user,
        link=link,
        exclude_user_ids={post.author_id} if post.author_id else None,
    )
    comment_count = post.comments.filter(is_removed=False).count()
    return JsonResponse(
        {
            "ok": True,
            "comment": serialize_comment(comment, request.user),
            "comment_count": comment_count,
        },
        status=201,
    )


@login_required
@require_http_methods(["DELETE", "POST"])
def api_v1_timeline_delete(request: HttpRequest, pk: int) -> JsonResponse:
    post = get_object_or_404(TimelinePost, pk=pk)
    if post.author_id is not None and post.author_id != request.user.id:
        return _json_error("forbidden", status=403)
    post.delete()
    return JsonResponse({"ok": True})


@login_required
@require_http_methods(["DELETE", "POST"])
def api_v1_timeline_comment_delete(request: HttpRequest, pk: int) -> JsonResponse:
    comment = get_object_or_404(
        Comment.objects.select_related("timeline_post"),
        pk=pk,
    )
    if not comment.timeline_post_id:
        return _json_error("not_timeline_comment", status=400)
    if comment.author_id != request.user.id:
        return _json_error("forbidden", status=403)
    post_id = comment.timeline_post_id
    comment.delete()
    comment_count = Comment.objects.filter(
        timeline_post_id=post_id, is_removed=False
    ).count()
    return JsonResponse({"ok": True, "comment_count": comment_count})


@login_required
@require_GET
def api_v1_timeline_quote(request: HttpRequest, pk: int) -> JsonResponse:
    post = get_quotable_post(pk, request.user)
    if not post:
        return _json_error("not_quotable", status=404)
    return JsonResponse(
        {
            "ok": True,
            "quoted_post": serialize_timeline_post(
                post, request.user, include_comments=False
            ),
        }
    )
