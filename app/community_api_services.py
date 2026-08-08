"""Community JSON helpers — serialize + list wrappers over community_services."""

from __future__ import annotations

from typing import Any

from django.contrib.auth.models import AbstractBaseUser
from django.http import HttpRequest

from .community_services import (
    can_delete_community_content,
    can_edit_community_reply,
    get_faculty_tag_choices,
    list_community_threads,
    list_replies_for_thread,
    count_visible_replies_for_thread,
)
from .constants import FACULTY_CHOICES
from .models import Community, CommunityThread, CommunityThreadReply
from .timeline_api_services import serialize_author


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
        "author": serialize_author(thread.author),
        "community": serialize_community(thread.community),
    }


def serialize_reply(
    reply: CommunityThreadReply,
    viewer: AbstractBaseUser | None,
) -> dict[str, Any]:
    return {
        "id": reply.pk,
        "body": "" if reply.is_removed else reply.body,
        "created_at": reply.created_at.isoformat(),
        "is_removed": bool(reply.is_removed),
        "can_delete": (
            can_delete_community_content(viewer, reply.author_id)
            if viewer is not None and not reply.is_removed
            else False
        ),
        "can_edit": can_edit_community_reply(viewer, reply)
        if viewer is not None
        else False,
        "author": None if reply.is_removed else serialize_author(reply.author),
    }


def serialize_thread_detail(
    thread: CommunityThread,
    viewer: AbstractBaseUser | None,
) -> dict[str, Any]:
    replies = list(list_replies_for_thread(thread, include_removed=True))
    return {
        "id": thread.pk,
        "title": thread.title,
        "body": thread.body,
        "created_at": thread.created_at.isoformat(),
        "updated_at": thread.updated_at.isoformat(),
        "can_delete": can_delete_community_content(viewer, thread.author_id)
        if viewer is not None
        else False,
        "author": serialize_author(thread.author),
        "community": serialize_community(thread.community),
        "visible_reply_count": count_visible_replies_for_thread(thread),
        "replies": [serialize_reply(r, viewer) for r in replies],
    }


def list_threads_payload(request: HttpRequest) -> dict[str, Any]:
    faculty_values = {value for value, _ in FACULTY_CHOICES}
    active_tag = request.GET.get("tag", "").strip()
    if active_tag not in faculty_values:
        active_tag = ""
    query = request.GET.get("q", "").strip()
    threads = list(list_community_threads(query=query, faculty=active_tag))
    viewer = request.user if request.user.is_authenticated else None
    return {
        "threads": [serialize_thread_summary(t, viewer) for t in threads],
        "faculty_tabs": get_faculty_tag_choices(),
        "active_tag": active_tag,
        "q": query,
    }
