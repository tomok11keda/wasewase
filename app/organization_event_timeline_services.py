"""公開イベントを団体名義タイムラインへシェアする。カードはイベントを都度参照する。"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from django.contrib.auth.models import AbstractBaseUser
from django.db import transaction
from django.db.models.signals import pre_delete
from django.dispatch import receiver
from django.utils import timezone

from .models import OrganizationEvent, TimelinePost
from .organization_event_services import (
    OrganizationEventError,
    _iso,
    _lock_event,
    _require_manage,
    event_has_completed_lottery,
    event_has_ended,
    event_registration_is_closed,
    event_uses_registration,
    organization_allows_event_access,
    serialize_organization_event,
)
from .organization_post_services import (
    ORG_POST_VISIBILITY_DRAFT,
    ORG_POST_VISIBILITY_PUBLIC,
)
from .rate_limit_services import allow_timeline_post

EVENT_TIMELINE_SHARE_BODY = "イベントをシェアしました"
EVENT_TIMELINE_SHARE_COOLDOWN = timedelta(minutes=10)
BODY_MAX = 280


def public_event_card_status(
    event: OrganizationEvent, *, now=None
) -> tuple[str, str]:
    if event.deleted_at is not None:
        return ("unavailable", "")
    if event.status == OrganizationEvent.Status.DRAFT:
        return ("unavailable", "")
    if event.status == OrganizationEvent.Status.CANCELLED:
        return ("cancelled", "中止")
    if event_has_ended(event, now=now):
        return ("ended", "終了")
    if not event_uses_registration(event):
        return ("announcement", "告知のみ")
    if event_has_completed_lottery(event.pk):
        return ("lottery_done", "抽選済み")
    if event_registration_is_closed(event, now=now):
        return ("closed", "受付終了")
    return ("open", "申込受付中")


def serialize_shared_organization_event(post: TimelinePost) -> dict[str, Any] | None:
    """Live event card. Draft / deleted events leak nothing."""
    event = getattr(post, "shared_organization_event", None)
    if event is None or getattr(event, "deleted_at", None) is not None:
        return None
    if event.status == OrganizationEvent.Status.DRAFT:
        return None
    organization = getattr(event, "organization", None)
    if organization is None:
        return None
    status, status_label = public_event_card_status(event)
    slug = organization.slug
    return {
        "id": event.pk,
        "organization_id": organization.pk,
        "organization_slug": slug,
        "organization_name": organization.name,
        "title": event.title,
        "starts_at": _iso(event.starts_at),
        "ends_at": _iso(event.ends_at),
        "venue_name": event.venue_name or "",
        "signup_mode": event.signup_mode
        or OrganizationEvent.SignupMode.REGISTRATION,
        "status": status,
        "status_label": status_label,
        "path": f"/organizations/{slug}/events/{event.pk}",
    }


def unlist_organization_event_timeline_shares(event_id: int) -> int:
    """削除後に SET_NULL されても通常投稿として残らないように非公開化する。"""
    return TimelinePost.objects.filter(
        shared_organization_event_id=event_id,
        is_removed=False,
    ).update(organization_visibility=ORG_POST_VISIBILITY_DRAFT)


@receiver(
    pre_delete,
    sender=OrganizationEvent,
    dispatch_uid="wase_organization_event_pre_delete_unlist_shares",
)
def _unlist_shares_before_event_row_delete(sender, instance, **kwargs):
    event_id = getattr(instance, "pk", None)
    if event_id:
        unlist_organization_event_timeline_shares(event_id)


def share_organization_event_to_timeline(
    *,
    event: OrganizationEvent,
    actor: AbstractBaseUser,
    body: str | None = None,
) -> TimelinePost:
    organization = event.organization
    _require_manage(actor, organization)
    if event.deleted_at is not None:
        raise OrganizationEventError("not_found", status=404)
    if event.status != OrganizationEvent.Status.PUBLISHED:
        raise OrganizationEventError("not_published", status=409)
    if not organization_allows_event_access(organization):
        raise OrganizationEventError("organization_suspended", status=403)
    intro = (body or "").replace("\x00", "").strip()
    if not intro:
        intro = EVENT_TIMELINE_SHARE_BODY
    if len(intro) > BODY_MAX:
        raise OrganizationEventError(
            "invalid_payload",
            status=400,
            errors={"body": f"{BODY_MAX}文字以内で入力してください。"},
        )
    if not allow_timeline_post(actor):
        raise OrganizationEventError("rate_limited", status=429)

    cutoff = timezone.now() - EVENT_TIMELINE_SHARE_COOLDOWN
    with transaction.atomic():
        locked = _lock_event(event.pk)
        if locked.deleted_at is not None:
            raise OrganizationEventError("not_found", status=404)
        if locked.status != OrganizationEvent.Status.PUBLISHED:
            raise OrganizationEventError("not_published", status=409)
        recent = (
            TimelinePost.objects.select_for_update()
            .filter(
                organization_id=locked.organization_id,
                shared_organization_event_id=locked.pk,
                is_removed=False,
                created_at__gte=cutoff,
            )
            .exists()
        )
        if recent:
            raise OrganizationEventError("share_cooldown", status=429)
        post = TimelinePost.objects.create(
            author=actor,
            organization=locked.organization,
            organization_visibility=ORG_POST_VISIBILITY_PUBLIC,
            body=intro,
            faculty="",
            shared_organization_event=locked,
        )
    return post


def timeline_share_response_payload(
    event: OrganizationEvent, actor: AbstractBaseUser, post: TimelinePost
) -> dict[str, Any]:
    from .timeline_api_services import serialize_timeline_post

    prepared = post
    return {
        "ok": True,
        "shared": True,
        "post_id": post.pk,
        "event": serialize_organization_event(event, actor),
        "post": serialize_timeline_post(prepared, actor),
        "shared_organization_event": serialize_shared_organization_event(post),
    }
