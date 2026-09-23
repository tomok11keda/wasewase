"""Community JSON helpers — serialize + list wrappers over community_services."""

from __future__ import annotations

from typing import Any

from django.contrib.auth.models import AbstractBaseUser
from django.http import HttpRequest

from .community_participant_services import (
    CREATOR_NUMBER,
    anonymous_label_for,
    ensure_participants_for_thread,
    participant_numbers,
)
from .community_services import (
    can_delete_community_content,
    can_edit_community_reply,
    count_visible_replies_for_thread,
    get_faculty_tag_choices,
    list_community_threads,
    list_replies_for_thread,
    reply_numbers_for_thread_all,
)
from .constants import FACULTY_CHOICES
from .models import Community, CommunityThread, CommunityThreadReply
from .ugc_services import get_either_blocked_user_ids

COMMUNITY_ANON_HINT = (
    "コミュニティではすべての投稿が匿名です。ユーザー番号はスレッドごとに変わります。"
)


def _anonymous_fields(number: int | None) -> dict[str, Any]:
    label = anonymous_label_for(number)
    payload: dict[str, Any] = {}
    if number:
        payload["anonymous_number"] = int(number)
    if label:
        payload["anonymous_label"] = label
    return payload


def _is_mine(viewer: AbstractBaseUser | None, author_id: int | None) -> bool:
    if viewer is None or not getattr(viewer, "is_authenticated", False):
        return False
    if author_id is None:
        return False
    return viewer.pk == author_id


def _can_report(
    viewer: AbstractBaseUser | None,
    author_id: int | None,
    *,
    is_removed: bool = False,
) -> bool:
    if is_removed:
        return False
    if viewer is None or not getattr(viewer, "is_authenticated", False):
        return False
    if author_id is None:
        return False
    return viewer.pk != author_id


def serialize_community(community: Community) -> dict[str, Any]:
    return {
        "id": community.pk,
        "slug": community.slug,
        "name": community.name,
        "description": community.description or "",
        "faculty": community.faculty or "",
        "category": community.category,
    }


def serialize_thread_summary(
    thread: CommunityThread,
    viewer: AbstractBaseUser | None,
) -> dict[str, Any]:
    replies_count = int(getattr(thread, "replies_count", 0) or 0)
    return {
        "id": thread.pk,
        "title": thread.title,
        "body": thread.body,
        "body_preview": (thread.body or "")[:160],
        "created_at": thread.created_at.isoformat(),
        "updated_at": thread.updated_at.isoformat(),
        "replies_count": replies_count,
        "can_delete": can_delete_community_content(
            viewer, thread.author_id
        )
        if viewer is not None
        else False,
        "is_mine": _is_mine(viewer, thread.author_id),
        "can_report": _can_report(viewer, thread.author_id),
        **_anonymous_fields(CREATOR_NUMBER),
        "community": serialize_community(thread.community),
    }


def serialize_reply_to_preview(
    parent: CommunityThreadReply | None,
    *,
    number_by_id: dict[int, int],
    blocked_author_ids: set[int] | None = None,
    author_numbers: dict[int, int] | None = None,
) -> dict[str, Any] | None:
    if parent is None:
        return None
    number = number_by_id.get(parent.pk)
    hidden_authors = blocked_author_ids or set()
    if (
        parent.is_removed
        or parent.author_id is None
        or parent.author_id in hidden_authors
    ):
        return {
            "id": parent.pk,
            "reply_number": number,
            "is_unavailable": True,
        }
    payload = {
        "id": parent.pk,
        "reply_number": number,
        "is_unavailable": False,
    }
    if parent.author_id and author_numbers:
        payload.update(_anonymous_fields(author_numbers.get(parent.author_id)))
    return payload


def serialize_reply(
    reply: CommunityThreadReply,
    viewer: AbstractBaseUser | None,
    *,
    reply_number: int | None = None,
    number_by_id: dict[int, int] | None = None,
    blocked_author_ids: set[int] | None = None,
    author_numbers: dict[int, int] | None = None,
) -> dict[str, Any]:
    numbers = number_by_id or {}
    number = reply_number if reply_number is not None else numbers.get(reply.pk)
    parent = None
    if reply.reply_to_id:
        parent = getattr(reply, "reply_to", None)
    hidden_authors = (
        blocked_author_ids
        if blocked_author_ids is not None
        else get_either_blocked_user_ids(viewer)
    )
    author_map = author_numbers or {}
    payload = {
        "id": reply.pk,
        "body": "" if reply.is_removed else reply.body,
        "created_at": reply.created_at.isoformat(),
        "is_removed": bool(reply.is_removed),
        "reply_number": number,
        "reply_to": serialize_reply_to_preview(
            parent,
            number_by_id=numbers,
            blocked_author_ids=hidden_authors,
            author_numbers=author_map,
        ),
        "can_delete": (
            can_delete_community_content(viewer, reply.author_id)
            if viewer is not None and not reply.is_removed
            else False
        ),
        "can_edit": can_edit_community_reply(viewer, reply)
        if viewer is not None
        else False,
        "is_mine": _is_mine(viewer, reply.author_id) and not reply.is_removed,
        "can_report": _can_report(
            viewer, reply.author_id, is_removed=bool(reply.is_removed)
        ),
    }
    if not reply.is_removed:
        payload.update(_anonymous_fields(author_map.get(reply.author_id)))
    return payload


def serialize_thread_detail(
    thread: CommunityThread,
    viewer: AbstractBaseUser | None,
) -> dict[str, Any]:
    blocked_ids = get_either_blocked_user_ids(viewer)
    replies = list(
        list_replies_for_thread(
            thread, include_removed=True, blocked_ids=blocked_ids
        )
    )
    number_by_id = reply_numbers_for_thread_all(thread)
    author_numbers = ensure_participants_for_thread(thread)
    return {
        "id": thread.pk,
        "title": thread.title,
        "body": thread.body,
        "created_at": thread.created_at.isoformat(),
        "updated_at": thread.updated_at.isoformat(),
        "can_delete": can_delete_community_content(viewer, thread.author_id)
        if viewer is not None
        else False,
        "is_mine": _is_mine(viewer, thread.author_id),
        "can_report": _can_report(viewer, thread.author_id),
        **_anonymous_fields(
            author_numbers.get(thread.author_id, CREATOR_NUMBER)
            if thread.author_id
            else CREATOR_NUMBER
        ),
        "community": serialize_community(thread.community),
        "anonymous_hint": COMMUNITY_ANON_HINT,
        "visible_reply_count": count_visible_replies_for_thread(
            thread, blocked_ids=blocked_ids
        ),
        "replies": [
            serialize_reply(
                r,
                viewer,
                reply_number=number_by_id[r.pk],
                number_by_id=number_by_id,
                blocked_author_ids=blocked_ids,
                author_numbers=author_numbers,
            )
            for r in replies
        ],
    }


def list_threads_payload(request: HttpRequest) -> dict[str, Any]:
    from .feed_ranking import (
        COMMUNITY_SORT_LATEST,
        parse_community_sort,
        rank_community_threads,
    )

    faculty_values = {value for value, _ in FACULTY_CHOICES}
    active_tag = request.GET.get("tag", "").strip()
    if active_tag not in faculty_values:
        active_tag = ""
    query = request.GET.get("q", "").strip()
    sort = parse_community_sort(request.GET.get("sort"))
    viewer = request.user if request.user.is_authenticated else None
    thread_qs = list_community_threads(
        query=query, faculty=active_tag, viewer=viewer
    )
    if sort == COMMUNITY_SORT_LATEST:
        threads = list(thread_qs)
    else:
        threads = rank_community_threads(list(thread_qs), viewer=viewer)
    return {
        "threads": [serialize_thread_summary(t, viewer) for t in threads],
        "faculty_tabs": get_faculty_tag_choices(),
        "active_tag": active_tag,
        "q": query,
        "sort": sort,
        "anonymous_hint": COMMUNITY_ANON_HINT,
    }
