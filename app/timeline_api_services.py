"""Timeline JSON API helpers — serialize + thin wrappers over existing services."""

from __future__ import annotations

from typing import Any

from django.contrib.auth.models import AbstractBaseUser
from django.http import HttpRequest

from .ads_services import (
    get_infeed_ad_interval,
    is_ads_disabled,
    should_show_timeline_infeed_ads,
)
from .board_services import (
    TIMELINE_INITIAL_SIZE,
    TIMELINE_LOAD_MORE_SIZE,
    build_timeline_posts_queryset,
    prepare_timeline_post_for_save,
)
from .bookmark_services import prepare_timeline_posts
from .models import Comment, TimelinePost
from .handle_services import public_username
from .services import (
    get_user_avatar_url,
    user_avatar_initial,
    user_display_name,
)
from .ugc_services import filter_visible_comments


def serialize_author(user: AbstractBaseUser | None) -> dict[str, Any] | None:
    if user is None:
        return None
    avatar = get_user_avatar_url(user) or ""
    return {
        "id": user.pk,
        "username": public_username(user),
        "display_name": user_display_name(user),
        "avatar_url": avatar,
        "initial": user_avatar_initial(user),
    }


def serialize_quoted_post(
    post: TimelinePost | None,
    viewer: AbstractBaseUser | None = None,
) -> dict[str, Any] | None:
    if post is None:
        return None
    if getattr(post, "is_removed", False):
        return {
            "id": post.pk,
            "is_removed": True,
            "body": "",
            "author": None,
            "image_url": None,
            "course_name": "",
        }

    from .follow_services import can_view_private_content
    from .ugc_services import is_either_blocked

    author = post.author
    if author is not None and is_either_blocked(viewer, author):
        return {
            "id": post.pk,
            "is_removed": True,
            "body": "",
            "author": None,
            "image_url": None,
            "course_name": "",
        }
    if author is not None and not can_view_private_content(viewer, author):
        # Keep quote shell metadata-safe: no body/image/course for unauthorized viewers.
        return {
            "id": post.pk,
            "is_removed": True,
            "body": "",
            "author": None,
            "image_url": None,
            "course_name": "",
        }

    image_url = None
    if post.image:
        try:
            image_url = post.image.url
        except ValueError:
            image_url = None
    body = post.body or ""
    return {
        "id": post.pk,
        "is_removed": False,
        "body": body[:120],
        "author": serialize_author(author),
        "image_url": image_url,
        "course_name": post.course_name or "",
    }


def serialize_comment(
    comment: Comment,
    viewer: AbstractBaseUser | None,
) -> dict[str, Any]:
    can_delete = bool(
        viewer
        and getattr(viewer, "is_authenticated", False)
        and comment.author_id == viewer.pk
    )
    return {
        "id": comment.pk,
        "body": comment.body,
        "created_at": comment.created_at.isoformat(),
        "can_delete": can_delete,
        "author": serialize_author(comment.author),
    }


def serialize_timeline_post(
    post: TimelinePost,
    viewer: AbstractBaseUser | None,
    *,
    include_comments: bool = True,
) -> dict[str, Any]:
    image_url = None
    if post.image:
        try:
            image_url = post.image.url
        except ValueError:
            image_url = None

    viewer_id = (
        viewer.pk
        if viewer is not None and getattr(viewer, "is_authenticated", False)
        else None
    )
    can_delete = bool(
        viewer_id is not None
        and (post.author_id is None or post.author_id == viewer_id)
    )

    comments_payload: list[dict[str, Any]] = []
    comments_qs = filter_visible_comments(
        post.comments.all(),
        viewer if viewer_id is not None else None,
    ).select_related("author", "author__profile")
    if include_comments:
        comments_list = list(comments_qs)
        comment_count = len(comments_list)
        comments_payload = [serialize_comment(c, viewer) for c in comments_list]
    else:
        comment_count = comments_qs.count()

    quote_count = getattr(post, "quote_count", None)
    if quote_count is None:
        quote_count = post.quotes.filter(is_removed=False).count()

    return {
        "id": post.pk,
        "body": post.body,
        "created_at": post.created_at.isoformat(),
        "course_name": post.course_name or "",
        "professor_name": post.professor_name or "",
        "faculty": post.faculty or "",
        "image_url": image_url,
        "like_count": int(post.like_count or 0),
        "comment_count": comment_count,
        "quote_count": int(quote_count or 0),
        "view_count": int(post.view_count or 0),
        "user_has_liked": bool(getattr(post, "user_has_liked", False)),
        "user_has_bookmarked": bool(getattr(post, "user_has_bookmarked", False)),
        "can_delete": can_delete,
        "author": serialize_author(post.author),
        "quoted_post": serialize_quoted_post(
            post.quoted_post if post.quoted_post_id else None,
            viewer,
        ),
        "comments": comments_payload,
    }


def ads_meta_for_request(request: HttpRequest) -> dict[str, Any]:
    return {
        "show_infeed": bool(should_show_timeline_infeed_ads(request)),
        "interval": int(get_infeed_ad_interval()),
        "disabled": bool(is_ads_disabled()),
    }


def list_timeline_page(
    request: HttpRequest,
    *,
    offset: int | None = None,
) -> dict[str, Any]:
    """
    Classic feed semantics:
    - no offset → first page size TIMELINE_INITIAL_SIZE (25)
    - with offset → TIMELINE_LOAD_MORE_SIZE (15)
    """
    timeline_qs = build_timeline_posts_queryset(request)
    total_count = timeline_qs.count()
    if offset is None:
        start = 0
        page_size = TIMELINE_INITIAL_SIZE
    else:
        start = max(0, offset)
        page_size = TIMELINE_LOAD_MORE_SIZE
    posts = prepare_timeline_posts(
        list(timeline_qs[start : start + page_size]),
        request.user,
    )
    next_offset = start + len(posts)
    viewer = request.user if request.user.is_authenticated else None
    return {
        "posts": [
            serialize_timeline_post(p, viewer) for p in posts
        ],
        "has_more": next_offset < total_count,
        "next_offset": next_offset,
        "total_count": total_count,
        "feed": request.GET.get("feed", "all").strip().lower() or "all",
        "q": request.GET.get("q", "").strip(),
        "faculty": request.GET.get("faculty", "").strip(),
        "tag": request.GET.get("tag", "").strip(),
        "ads": ads_meta_for_request(request),
    }


def save_timeline_post_instance(post: TimelinePost) -> TimelinePost:
    """Same path as views._save_timeline_post (media + prepare + save)."""
    from django.conf import settings

    from .media_services import (
        ensure_local_post_images_dir,
        log_media_storage_status,
        log_media_upload,
        prepare_image_field_for_save,
    )

    log_media_storage_status()
    image = getattr(post, "image", None)
    has_upload = bool(image and getattr(image, "name", None))

    if has_upload and not getattr(settings, "USE_CLOUDINARY", False):
        ensure_local_post_images_dir()
    if has_upload:
        prepare_image_field_for_save(post)
    prepare_timeline_post_for_save(post)
    post.save()
    log_media_upload(
        "TIMELINE API SAVE",
        f"post_id={post.pk} has_image={has_upload}",
    )
    return post
