"""Firestore 上の users/{userId}/bookmarks/{postId} によるブックマーク管理。"""

from __future__ import annotations

import logging
from typing import Iterable

from django.contrib.auth.models import AbstractBaseUser
from django.db.models import Exists, OuterRef

from .models import TimelineLike, TimelinePost
from .push_services import get_firebase_app
from .ugc_services import filter_visible_timeline_posts

logger = logging.getLogger(__name__)


class BookmarkServiceError(Exception):
    """Firestore が利用できない等、ブックマーク処理を完了できない場合。"""


def get_firestore_client():
    app = get_firebase_app()
    if app is None:
        return None
    try:
        from firebase_admin import firestore
    except ImportError:
        logger.warning("firebase-admin is not installed; bookmarks disabled.")
        return None
    return firestore.client(app)


def _bookmarks_collection(db, user_id: int):
    return (
        db.collection("users")
        .document(str(user_id))
        .collection("bookmarks")
    )


def get_bookmarked_post_ids(user: AbstractBaseUser) -> set[int]:
    db = get_firestore_client()
    if db is None:
        return set()

    post_ids: set[int] = set()
    try:
        for doc in _bookmarks_collection(db, user.pk).stream():
            data = doc.to_dict() or {}
            raw_id = data.get("postId", doc.id)
            try:
                post_ids.add(int(raw_id))
            except (TypeError, ValueError):
                continue
    except Exception:
        logger.exception("Failed to load bookmarks for user %s", user.pk)
        return set()
    return post_ids


def is_post_bookmarked(user: AbstractBaseUser, post_id: int) -> bool:
    db = get_firestore_client()
    if db is None:
        return False
    try:
        doc = _bookmarks_collection(db, user.pk).document(str(post_id)).get()
        return doc.exists
    except Exception:
        logger.exception("Failed to check bookmark for user %s post %s", user.pk, post_id)
        return False


def toggle_bookmark(user: AbstractBaseUser, post_id: int) -> bool:
    """ブックマークをトグルし、操作後にブックマーク済みなら True を返す。"""
    db = get_firestore_client()
    if db is None:
        raise BookmarkServiceError("Firestore is not configured.")

    from firebase_admin import firestore

    ref = _bookmarks_collection(db, user.pk).document(str(post_id))
    try:
        if ref.get().exists:
            ref.delete()
            return False
        ref.set(
            {
                "postId": post_id,
                "createdAt": firestore.SERVER_TIMESTAMP,
            }
        )
        return True
    except BookmarkServiceError:
        raise
    except Exception as exc:
        logger.exception("Failed to toggle bookmark for user %s post %s", user.pk, post_id)
        raise BookmarkServiceError("Bookmark toggle failed.") from exc


def attach_bookmark_state(posts: Iterable[TimelinePost], viewer: AbstractBaseUser | None) -> None:
    post_list = list(posts)
    if not post_list:
        return

    if viewer is None or not getattr(viewer, "is_authenticated", False):
        for post in post_list:
            post.user_has_bookmarked = False
        return

    bookmarked_ids = get_bookmarked_post_ids(viewer)
    for post in post_list:
        post.user_has_bookmarked = post.pk in bookmarked_ids


def prepare_timeline_posts(posts_or_qs, viewer: AbstractBaseUser | None):
    """表示用に投稿リストへブックマーク状態を付与する。"""
    posts = list(posts_or_qs)
    attach_bookmark_state(posts, viewer)
    return posts


def _timeline_posts_queryset_base():
    return TimelinePost.objects.select_related(
        "author",
        "author__profile",
        "quoted_post",
        "quoted_post__author",
        "quoted_post__author__profile",
    ).prefetch_related("comments__author")


def get_bookmarked_timeline_posts(
    owner: AbstractBaseUser,
    viewer: AbstractBaseUser | None,
):
    post_ids = sorted(get_bookmarked_post_ids(owner), reverse=True)
    if not post_ids:
        return []

    queryset = _timeline_posts_queryset_base().filter(
        pk__in=post_ids,
        is_removed=False,
    )
    queryset = filter_visible_timeline_posts(
        queryset,
        viewer if viewer and viewer.is_authenticated else None,
    )
    if viewer and viewer.is_authenticated:
        queryset = queryset.annotate(
            user_has_liked=Exists(
                TimelineLike.objects.filter(
                    timeline_post_id=OuterRef("pk"),
                    user_id=viewer.id,
                )
            )
        )

    posts_by_id = {post.pk: post for post in queryset}
    ordered_posts = [posts_by_id[post_id] for post_id in post_ids if post_id in posts_by_id]
    for post in ordered_posts:
        post.user_has_bookmarked = True
    return ordered_posts
