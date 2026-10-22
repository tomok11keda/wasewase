"""Inactive-user retention push (popular timeline posts).

Does not use create_notification / notify_user_push.
Does not change 1:1, community broadcast, or course-talk push-off behavior.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AbstractBaseUser
from django.db import transaction
from django.db.models import Q, QuerySet
from django.utils import timezone

from .board_services import annotate_timeline_quote_count
from .broadcast_push_services import (
    is_likely_test_account_email,
    is_waseda_student_email,
    user_allows_broadcast_push,
    users_with_sendable_ios_tokens,
    verified_university_student_qs,
)
from .feed_ranking import _annotate_timeline_for_ranking, timeline_recommend_score
from .models import RetentionPushSend, TimelinePost, UserProfile
from .push_services import PushDeliveryOutcome, deliver_push_to_user
from .spa_canonical import app_absolute

logger = logging.getLogger(__name__)

RETENTION_KIND_POPULAR_POST = RetentionPushSend.Kind.POPULAR_POST
RETENTION_PUSH_TITLE = "わせわせ"
RETENTION_PUSH_BODY = "わせわせで話題の投稿があります"
RETENTION_QUERY_PARAM = "rp"

INACTIVE_HOURS = 72
FREQUENCY_CAP_HOURS = 72
CANDIDATE_MIN_AGE_HOURS = 24
CANDIDATE_MAX_AGE_HOURS = 48
MIN_ENGAGEMENT = 1
CANDIDATE_POOL_LIMIT = 80

_CAP_STATUSES = (
    RetentionPushSend.Status.SENDING,
    RetentionPushSend.Status.SENT,
    RetentionPushSend.Status.UNKNOWN,
)


class RetentionPushError(ValueError):
    """Invalid retention push arguments."""


def tokyo_local_date(now=None):
    when = now or timezone.now()
    return timezone.localtime(when).date()


def popular_post_push_link(post_id: int) -> str:
    path = app_absolute(f"/posts/{int(post_id)}")
    sep = "&" if "?" in path else "?"
    return f"{path}{sep}{RETENTION_QUERY_PARAM}={RETENTION_KIND_POPULAR_POST}"


def _engagement_count(post: TimelinePost) -> int:
    likes = int(post.like_count or 0)
    comments = int(getattr(post, "feed_comment_count", 0) or 0)
    quotes = int(getattr(post, "quote_count", 0) or 0)
    return likes + comments + quotes


def _score_post(post: TimelinePost, now) -> float:
    return timeline_recommend_score(
        post,
        now=now,
        following_ids=set(),
        viewer_dept="",
        viewer_grade="",
        seen_ids=set(),
    )


def load_popular_post_candidates(*, now=None) -> list[TimelinePost]:
    """Public timeline posts from 24–48 hours ago with some engagement."""
    when = now or timezone.now()
    newest = when - timedelta(hours=CANDIDATE_MIN_AGE_HOURS)
    oldest = when - timedelta(hours=CANDIDATE_MAX_AGE_HOURS)
    qs: QuerySet[TimelinePost] = TimelinePost.objects.filter(
        is_removed=False,
        created_at__gte=oldest,
        created_at__lte=newest,
    ).filter(
        Q(author__profile__is_private=False) | Q(author__profile__isnull=True)
    )
    qs = annotate_timeline_quote_count(_annotate_timeline_for_ranking(qs))
    qs = qs.select_related("author", "author__profile")
    scored: list[tuple[float, TimelinePost]] = []
    for post in qs:
        if _engagement_count(post) < MIN_ENGAGEMENT:
            continue
        scored.append((_score_post(post, when), post))
    scored.sort(key=lambda item: (-item[0], -int(item[1].pk)))
    return [post for _score, post in scored[:CANDIDATE_POOL_LIMIT]]


def _recent_retention_cutoff(*, now=None):
    when = now or timezone.now()
    return when - timedelta(hours=FREQUENCY_CAP_HOURS)


def user_has_recent_retention_send(user, *, now=None) -> bool:
    if user is None or not getattr(user, "pk", None):
        return True
    return RetentionPushSend.objects.filter(
        user_id=user.pk,
        status__in=_CAP_STATUSES,
        created_at__gte=_recent_retention_cutoff(now=now),
    ).exists()


def sent_popular_post_ids_for_user(user) -> set[str]:
    if user is None or not getattr(user, "pk", None):
        return set()
    return set(
        RetentionPushSend.objects.filter(
            user_id=user.pk,
            kind=RETENTION_KIND_POPULAR_POST,
            status__in=_CAP_STATUSES,
        )
        .exclude(object_id="")
        .values_list("object_id", flat=True)
    )


def pick_popular_post_for_user(
    user,
    candidates: list[TimelinePost],
) -> TimelinePost | None:
    if not candidates:
        return None
    sent_ids = sent_popular_post_ids_for_user(user)
    user_id = getattr(user, "pk", None)
    for post in candidates:
        if user_id and post.author_id == user_id:
            continue
        if str(post.pk) in sent_ids:
            continue
        return post
    return None


def load_inactive_retention_users(*, now=None) -> list[Any]:
    when = now or timezone.now()
    cutoff = when - timedelta(hours=INACTIVE_HOURS)
    candidates = list(
        verified_university_student_qs().filter(
            profile__last_seen_at__isnull=False,
            profile__last_seen_at__lte=cutoff,
        )
    )
    filtered = []
    for user in candidates:
        email = getattr(user, "email", "") or ""
        if not is_waseda_student_email(email) or is_likely_test_account_email(email):
            continue
        if not user_allows_broadcast_push(user):
            continue
        filtered.append(user)
    eligible_ids = users_with_sendable_ios_tokens([user.pk for user in filtered])
    return [user for user in filtered if user.pk in eligible_ids]


def resolve_retention_test_user(*, email: str = "", user_id: int | None = None):
    """Resolve exactly one user for test-user mode. Production path never calls this."""
    email_value = (email or "").strip()
    if not email_value and user_id is None:
        return None
    User = get_user_model()
    by_id = None
    if user_id is not None:
        by_id = User.objects.filter(pk=int(user_id)).select_related("profile").first()
    by_email = None
    if email_value:
        by_email = (
            User.objects.filter(email__iexact=email_value)
            .select_related("profile")
            .first()
        )
    if email_value and user_id is not None:
        if by_id is None or by_email is None or by_id.pk != by_email.pk:
            raise RetentionPushError(
                "test-email と test-user-id が同じユーザーを指していません。"
            )
        return by_id
    user = by_id or by_email
    if user is None:
        raise RetentionPushError("指定したテストユーザーが見つかりません。")
    return user


def _user_is_inactive(user, *, now=None) -> bool:
    when = now or timezone.now()
    cutoff = when - timedelta(hours=INACTIVE_HOURS)
    profile = UserProfile.objects.filter(user_id=user.pk).first()
    last_seen = getattr(profile, "last_seen_at", None)
    if last_seen is None:
        return False
    return last_seen <= cutoff


def load_test_retention_users(
    user,
    *,
    now=None,
    ignore_inactivity: bool = False,
) -> list[Any]:
    """Audience for --test-email/--test-user-id: that user only, never others."""
    if user is None or not getattr(user, "pk", None):
        return []
    if not ignore_inactivity and not _user_is_inactive(user, now=now):
        return []
    if user.pk not in users_with_sendable_ios_tokens([user.pk]):
        return []
    return [user]


def load_retention_audience(
    *,
    now=None,
    test_user=None,
    ignore_inactivity: bool = False,
) -> list[Any]:
    if test_user is not None:
        return load_test_retention_users(
            test_user, now=now, ignore_inactivity=ignore_inactivity
        )
    if ignore_inactivity:
        raise RetentionPushError(
            "ignore_inactivity は test_user 指定時のみ使えます。"
        )
    return load_inactive_retention_users(now=now)


def preview_popular_post_retention(
    *,
    now=None,
    test_user=None,
    ignore_inactivity: bool = False,
) -> dict[str, int]:
    when = now or timezone.now()
    users = load_retention_audience(
        now=when, test_user=test_user, ignore_inactivity=ignore_inactivity
    )
    posts = load_popular_post_candidates(now=when)
    planned = 0
    skipped_cap = 0
    skipped_no_post = 0
    for user in users:
        if user_has_recent_retention_send(user, now=when):
            skipped_cap += 1
            continue
        if pick_popular_post_for_user(user, posts) is None:
            skipped_no_post += 1
            continue
        planned += 1
    return {
        "inactive_eligible_users": len(users),
        "popular_candidates": len(posts),
        "planned_sends": planned,
        "skipped_frequency_cap": skipped_cap,
        "skipped_no_post": skipped_no_post,
    }


def _finalize_send(row: RetentionPushSend, result) -> str:
    now = timezone.now()
    if result.outcome == PushDeliveryOutcome.SENT:
        status = RetentionPushSend.Status.SENT
        sent_at = now
    elif result.outcome == PushDeliveryOutcome.UNKNOWN:
        status = RetentionPushSend.Status.UNKNOWN
        sent_at = now
    else:
        status = RetentionPushSend.Status.FAILED
        sent_at = None
    RetentionPushSend.objects.filter(
        pk=row.pk,
        status=RetentionPushSend.Status.SENDING,
    ).update(
        status=status,
        success_count=int(getattr(result, "success_count", 0) or 0),
        reason=(result.reason or "")[:64],
        sent_at=sent_at,
    )
    return status


def send_popular_post_to_user(
    user: AbstractBaseUser,
    post: TimelinePost,
    *,
    now=None,
) -> dict[str, Any]:
    """Claim a send row then deliver via deliver_push_to_user only."""
    when = now or timezone.now()
    link = popular_post_push_link(post.pk)
    with transaction.atomic():
        UserProfile.objects.select_for_update().filter(user_id=user.pk).first()
        if user_has_recent_retention_send(user, now=when):
            return {"status": "skipped_cap", "post_id": post.pk}
        row = RetentionPushSend.objects.create(
            user=user,
            kind=RETENTION_KIND_POPULAR_POST,
            object_id=str(post.pk),
            status=RetentionPushSend.Status.SENDING,
            local_date=tokyo_local_date(when),
            link=link,
        )

    result = deliver_push_to_user(
        user,
        title=RETENTION_PUSH_TITLE,
        body=RETENTION_PUSH_BODY,
        link=link,
        notification_id="",
        notification_type=RETENTION_KIND_POPULAR_POST,
    )
    status = _finalize_send(row, result)
    return {
        "status": status,
        "post_id": post.pk,
        "reason": result.reason,
        "success_count": result.success_count,
    }


def execute_popular_post_retention(
    *,
    send: bool,
    limit: int | None = None,
    now=None,
    test_user=None,
    ignore_inactivity: bool = False,
) -> dict[str, Any]:
    when = now or timezone.now()
    users = load_retention_audience(
        now=when, test_user=test_user, ignore_inactivity=ignore_inactivity
    )
    posts = load_popular_post_candidates(now=when)
    preview = preview_popular_post_retention(
        now=when, test_user=test_user, ignore_inactivity=ignore_inactivity
    )
    counts = {
        "sent": 0,
        "failed": 0,
        "unknown": 0,
        "skipped_cap": 0,
        "skipped_no_post": 0,
        "planned": 0,
    }
    in_app_created = 0
    deliveries: list[dict[str, Any]] = []
    remaining = None if limit is None else max(0, int(limit))

    for user in users:
        if remaining is not None and remaining <= 0:
            break
        if user_has_recent_retention_send(user, now=when):
            counts["skipped_cap"] += 1
            continue
        post = pick_popular_post_for_user(user, posts)
        if post is None:
            counts["skipped_no_post"] += 1
            continue
        counts["planned"] += 1
        if not send:
            deliveries.append(
                {
                    "user_id": user.pk,
                    "post_id": post.pk,
                    "status": "dry_run",
                }
            )
            if remaining is not None:
                remaining -= 1
            continue
        result = send_popular_post_to_user(user, post, now=when)
        status = result["status"]
        if status == RetentionPushSend.Status.SENT:
            counts["sent"] += 1
        elif status == RetentionPushSend.Status.UNKNOWN:
            counts["unknown"] += 1
        elif status == "skipped_cap":
            counts["skipped_cap"] += 1
            counts["planned"] -= 1
        else:
            counts["failed"] += 1
        deliveries.append({"user_id": user.pk, **result})
        if remaining is not None:
            remaining -= 1

    return {
        "send": send,
        "kind": RETENTION_KIND_POPULAR_POST,
        "title": RETENTION_PUSH_TITLE,
        "body": RETENTION_PUSH_BODY,
        "audience": "test" if test_user is not None else "production",
        "test_user_id": getattr(test_user, "pk", None) if test_user is not None else None,
        "ignore_inactivity": bool(ignore_inactivity) if test_user is not None else False,
        "preview": preview,
        "counts": counts,
        "deliveries": deliveries,
        "in_app_notifications_created": in_app_created,
        "deliver_function": "deliver_push_to_user",
    }
