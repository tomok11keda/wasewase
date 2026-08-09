"""Feed ranking for timeline (X-style) and communities (BBS-style).

Kept separate on purpose — do not share one formula across both surfaces.
Search TOP/LATEST scoring stays in profile_api_services.
"""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any, Iterable, Sequence

from django.contrib.auth.models import AbstractBaseUser
from django.db.models import Count, Q, QuerySet
from django.http import HttpRequest
from django.utils import timezone

from .models import TimelinePost
from .services import get_following_user_ids, get_user_faculty

TIMELINE_SORT_RECOMMENDED = "recommended"
TIMELINE_SORT_LATEST = "latest"
TIMELINE_SORT_CHOICES = (TIMELINE_SORT_RECOMMENDED, TIMELINE_SORT_LATEST)

COMMUNITY_SORT_RECOMMENDED = "recommended"
COMMUNITY_SORT_LATEST = "latest"
COMMUNITY_SORT_CHOICES = (COMMUNITY_SORT_RECOMMENDED, COMMUNITY_SORT_LATEST)

# Cap candidate pool so ranking stays cheap under pagination.
TIMELINE_CANDIDATE_LIMIT = 250
TIMELINE_SEEN_SESSION_KEY = "tl_rec_seen_ids"
TIMELINE_RANK_SESSION_KEY = "tl_rec_rank_v1"
TIMELINE_SEEN_MAX = 120
TIMELINE_CLIENT_SEEN_MAX = 80


def parse_timeline_sort(raw: str | None) -> str:
    value = (raw or "").strip().lower()
    if value in ("latest", "new", "recent"):
        return TIMELINE_SORT_LATEST
    # Default: X-style recommended feed
    return TIMELINE_SORT_RECOMMENDED


def parse_community_sort(raw: str | None) -> str:
    value = (raw or "").strip().lower()
    if value in ("latest", "new", "recent"):
        return COMMUNITY_SORT_LATEST
    return COMMUNITY_SORT_RECOMMENDED


def _viewer_profile_bits(user: AbstractBaseUser | None) -> tuple[str, str]:
    if user is None or not getattr(user, "is_authenticated", False):
        return "", ""
    profile = getattr(user, "profile", None)
    if profile is None:
        return get_user_faculty(user), ""
    return (profile.department or ""), (profile.grade or "")


def _parse_seen_ids(raw: str | None, *, limit: int) -> list[int]:
    if not raw:
        return []
    out: list[int] = []
    seen: set[int] = set()
    for part in raw.replace(" ", "").split(","):
        if not part:
            continue
        try:
            pk = int(part)
        except ValueError:
            continue
        if pk <= 0 or pk in seen:
            continue
        seen.add(pk)
        out.append(pk)
        if len(out) >= limit:
            break
    return out


def _session_seen_ids(request: HttpRequest) -> list[int]:
    raw = request.session.get(TIMELINE_SEEN_SESSION_KEY) or []
    if not isinstance(raw, list):
        return []
    out: list[int] = []
    for item in raw:
        try:
            pk = int(item)
        except (TypeError, ValueError):
            continue
        if pk > 0:
            out.append(pk)
    return out[:TIMELINE_SEEN_MAX]


def _merge_seen_ids(*groups: Iterable[int]) -> set[int]:
    merged: set[int] = set()
    for group in groups:
        for pk in group:
            try:
                value = int(pk)
            except (TypeError, ValueError):
                continue
            if value > 0:
                merged.add(value)
    return merged


def timeline_recommend_score(
    post: TimelinePost,
    *,
    now: datetime,
    following_ids: set[int],
    viewer_dept: str,
    viewer_grade: str,
    seen_ids: set[int],
) -> float:
    """X-style: engagement + freshness + light personalization + seen demotion."""
    created = post.created_at or now
    age_hours = max((now - created).total_seconds() / 3600.0, 0.0)

    likes = int(post.like_count or 0)
    comments = int(getattr(post, "feed_comment_count", 0) or 0)
    quotes = int(getattr(post, "quote_count", 0) or 0)
    views = int(post.view_count or 0)

    engagement = likes * 4.0 + comments * 3.0 + quotes * 3.0
    # Only use view_count when real impressions exist (avoid 0-stub noise).
    if views > 0:
        engagement += math.log1p(views) * 1.5

    # ~36h half-life style decay for freshness
    recency = 48.0 / (48.0 + age_hours)
    score = engagement * 2.0 + recency * 28.0
    # Burst / activity relative to age
    score += engagement / (1.0 + age_hours / 6.0)

    author_id = getattr(post, "author_id", None)
    if author_id and author_id in following_ids:
        score += 18.0

    profile = getattr(getattr(post, "author", None), "profile", None)
    author_dept = (getattr(profile, "department", None) or "") if profile else ""
    author_grade = (getattr(profile, "grade", None) or "") if profile else ""
    if viewer_dept and author_dept == viewer_dept:
        score += 10.0
    if viewer_grade and author_grade == viewer_grade:
        score += 4.0

    if post.pk in seen_ids:
        # Demote recently shown/viewed posts; do not hide high-signal items fully.
        score *= 0.42

    return score


def _diversify_timeline(scored: list[TimelinePost], *, fresh_slots: int = 5) -> list[TimelinePost]:
    """Keep new posts from being buried under evergreen popular posts."""
    if len(scored) <= 15 or fresh_slots <= 0:
        return scored

    head_n = max(len(scored) // 5, 12)
    head = scored[:head_n]
    head_ids = {p.pk for p in head}
    rest = [p for p in scored if p.pk not in head_ids]
    newest_rest = sorted(
        rest,
        key=lambda p: p.created_at or timezone.now(),
        reverse=True,
    )[:fresh_slots]

    result = list(head)
    for i, post in enumerate(newest_rest):
        pos = min(2 + i * 3, len(result))
        result.insert(pos, post)

    used = {p.pk for p in result}
    result.extend(p for p in scored if p.pk not in used)
    return result


def _annotate_timeline_for_ranking(queryset: QuerySet) -> QuerySet:
    return queryset.annotate(
        feed_comment_count=Count(
            "comments",
            filter=Q(comments__is_removed=False),
            distinct=True,
        )
    )


def _fingerprint_timeline(request: HttpRequest, sort: str) -> str:
    user_id = (
        request.user.pk
        if getattr(request.user, "is_authenticated", False)
        else 0
    )
    return "|".join(
        [
            str(user_id),
            sort,
            request.GET.get("feed", "all").strip().lower() or "all",
            request.GET.get("faculty", "").strip(),
            request.GET.get("tag", "").strip(),
            request.GET.get("q", "").strip(),
        ]
    )


def _posts_by_ids_preserving_order(
    base_qs: QuerySet,
    ids: Sequence[int],
) -> list[TimelinePost]:
    if not ids:
        return []
    found = {
        p.pk: p
        for p in base_qs.filter(pk__in=ids).select_related(
            "author",
            "author__profile",
            "quoted_post",
            "quoted_post__author",
            "quoted_post__author__profile",
        )
    }
    return [found[pk] for pk in ids if pk in found]


def rank_timeline_page(
    request: HttpRequest,
    queryset: QuerySet,
    *,
    offset: int,
    page_size: int,
) -> tuple[list[TimelinePost], int]:
    """
    Rank a candidate window and paginate.
    Session caches rank order so load-more stays consistent within a session.
    """
    fingerprint = _fingerprint_timeline(request, TIMELINE_SORT_RECOMMENDED)
    start = max(0, offset)
    cached = request.session.get(TIMELINE_RANK_SESSION_KEY)
    if (
        start > 0
        and isinstance(cached, dict)
        and cached.get("fp") == fingerprint
        and isinstance(cached.get("ids"), list)
    ):
        ids: list[int] = []
        for item in cached["ids"]:
            try:
                pk = int(item)
            except (TypeError, ValueError):
                continue
            if pk > 0:
                ids.append(pk)
        page_ids = ids[start : start + page_size]
        return _posts_by_ids_preserving_order(queryset, page_ids), len(ids)

    ranked_qs = _annotate_timeline_for_ranking(queryset).order_by("-created_at")
    candidates = list(ranked_qs[:TIMELINE_CANDIDATE_LIMIT])

    viewer = request.user if getattr(request.user, "is_authenticated", False) else None
    following_ids: set[int] = set()
    if viewer is not None:
        following_ids = set(get_following_user_ids(viewer))
    viewer_dept, viewer_grade = _viewer_profile_bits(viewer)

    session_seen = _session_seen_ids(request)
    client_seen = _parse_seen_ids(
        request.GET.get("seen"),
        limit=TIMELINE_CLIENT_SEEN_MAX,
    )
    seen_ids = _merge_seen_ids(session_seen, client_seen)

    now = timezone.now()
    scored = sorted(
        candidates,
        key=lambda post: timeline_recommend_score(
            post,
            now=now,
            following_ids=following_ids,
            viewer_dept=viewer_dept,
            viewer_grade=viewer_grade,
            seen_ids=seen_ids,
        ),
        reverse=True,
    )
    ranked = _diversify_timeline(scored)
    ids = [p.pk for p in ranked]
    request.session[TIMELINE_RANK_SESSION_KEY] = {"fp": fingerprint, "ids": ids}

    page = ranked[start : start + page_size]
    page_ids = [p.pk for p in page]
    merged_seen = list(dict.fromkeys([*page_ids, *session_seen]))[:TIMELINE_SEEN_MAX]
    request.session[TIMELINE_SEEN_SESSION_KEY] = merged_seen
    # Touch session so anonymous browsers also persist demotion when possible.
    request.session.modified = True

    return page, len(ids)


def community_recommend_score(
    thread: Any,
    *,
    now: datetime,
    viewer_faculty: str,
) -> float:
    """BBS-style: activity + replies, with explicit boost for new quiet threads."""
    created = getattr(thread, "created_at", None) or now
    updated = getattr(thread, "updated_at", None) or created
    age_hours = max((now - created).total_seconds() / 3600.0, 0.0)
    idle_hours = max((now - updated).total_seconds() / 3600.0, 0.0)
    replies = int(getattr(thread, "replies_count", 0) or 0)

    score = replies * 5.0
    # Recent discussion activity
    score += 32.0 / (1.0 + idle_hours / 12.0)
    # Base freshness so new threads are not forever buried
    score += 14.0 / (1.0 + age_hours / 48.0)

    # New-thread exposure: stronger when still few replies
    if age_hours < 36:
        score += max(0.0, 16.0 - min(replies, 6) * 2.0)

    community = getattr(thread, "community", None)
    thread_faculty = (getattr(community, "faculty", None) or "") if community else ""
    if viewer_faculty and thread_faculty == viewer_faculty:
        score += 6.0

    return score


def rank_community_threads(
    threads: Sequence[Any],
    *,
    viewer: AbstractBaseUser | None,
) -> list[Any]:
    now = timezone.now()
    viewer_faculty = ""
    if viewer is not None and getattr(viewer, "is_authenticated", False):
        viewer_faculty = get_user_faculty(viewer)
    return sorted(
        list(threads),
        key=lambda thread: community_recommend_score(
            thread,
            now=now,
            viewer_faculty=viewer_faculty,
        ),
        reverse=True,
    )
