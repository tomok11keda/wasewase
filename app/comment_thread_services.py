"""Timeline comment threading: parent validation, order, tombstone delete."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from django.db.models import Prefetch

from .models import Comment, TimelinePost

TOMBSTONE_BODY = "削除されたコメント"


class CommentThreadError(ValueError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def timeline_comments_prefetch() -> Prefetch:
    return Prefetch(
        "comments",
        queryset=Comment.objects.select_related(
            "author",
            "author__profile",
            "parent_comment",
            "parent_comment__author",
            "parent_comment__author__profile",
        ).order_by("created_at", "pk"),
    )


def parse_parent_comment_id(raw: Any) -> int | None:
    if raw is None or raw == "":
        return None
    if isinstance(raw, bool):
        raise CommentThreadError("invalid_parent")
    if isinstance(raw, int):
        if raw <= 0:
            raise CommentThreadError("invalid_parent")
        return raw
    if isinstance(raw, str) and raw.isdigit():
        value = int(raw)
        if value <= 0:
            raise CommentThreadError("invalid_parent")
        return value
    raise CommentThreadError("invalid_parent")


def resolve_parent_comment(
    *,
    post: TimelinePost,
    parent_comment_id: int | None,
) -> Comment | None:
    if parent_comment_id is None:
        return None
    parent = (
        Comment.objects.select_related("author")
        .filter(pk=parent_comment_id)
        .first()
    )
    if parent is None:
        raise CommentThreadError("parent_not_found")
    if parent.timeline_post_id != post.pk:
        raise CommentThreadError("parent_wrong_post")
    if parent.is_removed or parent.is_author_deleted:
        raise CommentThreadError("parent_unavailable")
    return parent


def order_comments_for_thread(comments: list[Comment]) -> list[Comment]:
    """Depth-first: each parent, then its replies by created_at, then the next parent."""
    visible_ids = {comment.pk for comment in comments}
    by_parent: dict[int | None, list[Comment]] = defaultdict(list)
    for comment in sorted(comments, key=lambda row: (row.created_at, row.pk)):
        parent_id = comment.parent_comment_id
        if parent_id not in visible_ids:
            parent_id = None
        by_parent[parent_id].append(comment)

    ordered: list[Comment] = []
    seen: set[int] = set()

    def walk(parent_id: int | None) -> None:
        for child in by_parent.get(parent_id, []):
            if child.pk in seen:
                continue
            seen.add(child.pk)
            ordered.append(child)
            walk(child.pk)

    walk(None)
    for comment in comments:
        if comment.pk not in seen:
            ordered.append(comment)
    return ordered


def visible_timeline_comment_count(post_id: int) -> int:
    return Comment.objects.filter(
        timeline_post_id=post_id,
        is_removed=False,
        is_author_deleted=False,
    ).count()


def delete_or_tombstone_timeline_comment(comment: Comment) -> Comment | None:
    """Keep a placeholder when replies exist. Return the row if kept, else None."""
    has_child = comment.replies.filter(is_removed=False).exists()
    if has_child:
        comment.is_author_deleted = True
        comment.body = ""
        comment.save(update_fields=["is_author_deleted", "body"])
        return comment

    post_id = comment.timeline_post_id
    parent_id = comment.parent_comment_id
    comment.delete()
    while parent_id:
        parent = Comment.objects.filter(
            pk=parent_id,
            timeline_post_id=post_id,
        ).first()
        if parent is None or not parent.is_author_deleted:
            break
        if parent.replies.filter(is_removed=False).exists():
            break
        next_parent_id = parent.parent_comment_id
        parent.delete()
        parent_id = next_parent_id
    return None
