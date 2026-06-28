"""Firestore 上の users/{userId}/bookmarks/{postId} によるブックマーク管理。"""

from __future__ import annotations

import logging
from typing import Any, Iterable

from django.contrib.auth.models import AbstractBaseUser
from django.db.models import Exists, OuterRef

from .models import TimelineLike, TimelinePost
from .push_services import get_firebase_app
from .ugc_services import filter_visible_timeline_posts

logger = logging.getLogger(__name__)


class BookmarkServiceError(Exception):
    """Firestore が利用できない等、ブックマーク処理を完了できない場合。"""


def _bookmark_user_id(user: AbstractBaseUser) -> str:
    return str(user.pk)


def _bookmarks_path(user: AbstractBaseUser) -> str:
    return f"users/{_bookmark_user_id(user)}/bookmarks"


def _log_bookmark(message: str, user_pk: int, *, level: str = "info") -> None:
    full = f"[WASE BOOKMARK user={user_pk}] {message}"
    print(full, flush=True)
    if level == "error":
        logger.error(full)
    elif level == "warning":
        logger.warning(full)
    else:
        logger.info(full)


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


def _bookmarks_collection(db, user: AbstractBaseUser):
    return (
        db.collection("users")
        .document(_bookmark_user_id(user))
        .collection("bookmarks")
    )


def _parse_post_id_from_doc(doc) -> int | None:
    """ドキュメント ID (= postId) を優先して post ID を取り出す。"""
    data = doc.to_dict() or {}
    candidates = [doc.id]
    for key in ("postId", "post_id", "id"):
        if key in data:
            candidates.append(data[key])
    for raw_id in candidates:
        if raw_id is None:
            continue
        try:
            return int(raw_id)
        except (TypeError, ValueError):
            continue
    return None


def _fetch_bookmarks_from_firestore(user: AbstractBaseUser) -> tuple[list[int], dict[str, Any]]:
    path = _bookmarks_path(user)
    meta: dict[str, Any] = {
        "firestore_path": path,
        "firestore_count": 0,
        "firestore_post_ids": [],
        "displayed_count": 0,
        "missing_post_ids": [],
        "error": None,
    }

    db = get_firestore_client()
    if db is None:
        meta["error"] = "Firestore client unavailable"
        _log_bookmark(
            f"Firestore client unavailable; cannot read {path}",
            user.pk,
            level="warning",
        )
        return [], meta

    entries: list[tuple[int, Any, str]] = []
    try:
        docs = list(_bookmarks_collection(db, user).stream())
        meta["firestore_count"] = len(docs)
        _log_bookmark(f"Reading {path}: raw document count={len(docs)}", user.pk)

        for doc in docs:
            post_id = _parse_post_id_from_doc(doc)
            if post_id is None:
                _log_bookmark(
                    f"Skipping document {doc.id!r}: could not parse postId",
                    user.pk,
                    level="warning",
                )
                continue
            data = doc.to_dict() or {}
            entries.append((post_id, data.get("createdAt"), doc.id))

        def sort_key(entry: tuple[int, Any, str]):
            _, created_at, doc_id = entry
            if created_at is not None:
                return (0, created_at)
            try:
                return (1, int(doc_id))
            except (TypeError, ValueError):
                return (1, 0)

        entries.sort(key=sort_key, reverse=True)
        post_ids = [entry[0] for entry in entries]
        meta["firestore_post_ids"] = post_ids
        _log_bookmark(
            f"Parsed {len(post_ids)} bookmark post ID(s) from {path}: {post_ids}",
            user.pk,
        )
        return post_ids, meta
    except Exception as exc:
        meta["error"] = str(exc)
        _log_bookmark(f"Failed to read {path}: {exc}", user.pk, level="error")
        logger.exception("Failed to load bookmarks for user %s at %s", user.pk, path)
        return [], meta


def get_bookmarked_post_ids(user: AbstractBaseUser) -> set[int]:
    post_ids, _meta = _fetch_bookmarks_from_firestore(user)
    return set(post_ids)


def is_post_bookmarked(user: AbstractBaseUser, post_id: int) -> bool:
    db = get_firestore_client()
    if db is None:
        return False
    path = f"{_bookmarks_path(user)}/{post_id}"
    try:
        doc = _bookmarks_collection(db, user).document(str(post_id)).get()
        exists = doc.exists
        _log_bookmark(f"Check {path}: exists={exists}", user.pk)
        return exists
    except Exception:
        _log_bookmark(f"Failed to check {path}", user.pk, level="error")
        logger.exception("Failed to check bookmark for user %s post %s", user.pk, post_id)
        return False


def toggle_bookmark(user: AbstractBaseUser, post_id: int) -> bool:
    """ブックマークをトグルし、操作後にブックマーク済みなら True を返す。"""
    db = get_firestore_client()
    if db is None:
        raise BookmarkServiceError("Firestore is not configured.")

    from firebase_admin import firestore

    path = f"{_bookmarks_path(user)}/{post_id}"
    ref = _bookmarks_collection(db, user).document(str(post_id))
    try:
        if ref.get().exists:
            ref.delete()
            _log_bookmark(f"Deleted bookmark at {path}", user.pk)
            return False
        ref.set(
            {
                "postId": post_id,
                "createdAt": firestore.SERVER_TIMESTAMP,
            }
        )
        _log_bookmark(f"Created bookmark at {path}", user.pk)
        return True
    except BookmarkServiceError:
        raise
    except Exception as exc:
        _log_bookmark(f"Toggle failed at {path}: {exc}", user.pk, level="error")
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
    post_ids, meta = _fetch_bookmarks_from_firestore(owner)
    path = meta["firestore_path"]

    if not post_ids:
        if meta["firestore_count"] > 0 and not meta["error"]:
            meta["error"] = "Firestore documents found but no valid post IDs could be parsed"
            _log_bookmark(meta["error"], owner.pk, level="warning")
        _log_bookmark(
            f"Timeline fetch from {path}: firestore={meta['firestore_count']}, displayed=0",
            owner.pk,
        )
        return [], meta

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
    missing_post_ids = [post_id for post_id in post_ids if post_id not in posts_by_id]
    meta["missing_post_ids"] = missing_post_ids
    meta["displayed_count"] = len(ordered_posts)

    for post in ordered_posts:
        post.user_has_bookmarked = True

    _log_bookmark(
        (
            f"Timeline fetch from {path}: firestore={meta['firestore_count']}, "
            f"parsed_ids={len(post_ids)}, django_matched={len(posts_by_id)}, "
            f"displayed={meta['displayed_count']}, missing={missing_post_ids}"
        ),
        owner.pk,
        level="warning" if missing_post_ids else "info",
    )
    return ordered_posts, meta
