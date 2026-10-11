"""運営によるコミュニティスレッド一斉プッシュ。既存 1:1 通知とは別経路。"""

from __future__ import annotations

import logging
import re
from typing import Any

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Count, Q, QuerySet
from django.utils import timezone

from .constants import FACULTY_CHOICES
from .models import (
    CommunityThread,
    DevicePushToken,
    PushCampaign,
    PushCampaignRecipient,
)
from .notification_services import push_payload_link
from .push_services import (
    PushDeliveryOutcome,
    deliver_push_to_user,
    is_likely_apns_device_token,
)

logger = logging.getLogger(__name__)

User = get_user_model()

PUSH_KIND_COMMUNITY_THREAD_BROADCAST = "community_thread_broadcast"

CAMPAIGN_KEY_RE = re.compile(r"^[a-zA-Z0-9_.:-]{3,80}$")
TEST_EMAIL_LOCAL_RE = re.compile(
    r"^(test|qa|dummy)([0-9+._-]|$)",
    re.IGNORECASE,
)

NON_STUDENT_DEPARTMENTS = frozenset({"附属・系属校", "卒業生", "その他", ""})
UNIVERSITY_FACULTY_VALUES = frozenset(
    value
    for value, _label in FACULTY_CHOICES
    if value not in NON_STUDENT_DEPARTMENTS
)

TERMINAL_RECIPIENT_STATUSES = frozenset(
    {
        PushCampaignRecipient.Status.SENT,
        PushCampaignRecipient.Status.UNKNOWN,
    }
)


class BroadcastPushError(ValueError):
    """Invalid campaign arguments or missing permissions."""


def community_thread_push_link(thread: CommunityThread) -> str:
    slug = thread.community.slug
    return push_payload_link(f"/app/communities/{slug}/threads/{thread.pk}")


def is_waseda_student_email(email: str) -> bool:
    host = (email or "").rsplit("@", 1)[-1].strip().lower()
    return host == "waseda.jp" or host.endswith(".waseda.jp")


def is_likely_test_account_email(email: str) -> bool:
    local = (email or "").split("@", 1)[0].strip().lower()
    if not local:
        return True
    if TEST_EMAIL_LOCAL_RE.match(local):
        return True
    if "+test" in local or local.endswith("+qa"):
        return True
    return False


def user_allows_broadcast_push(user) -> bool:
    """Promotional / ops broadcast push.

    No product opt-out exists yet. When UserProfile.broadcast_push_opt_out
    is added, honor it here so callers do not need a second check.
    """
    profile = getattr(user, "profile", None)
    if profile is not None and getattr(profile, "broadcast_push_opt_out", False):
        return False
    return True


def ios_sendable_token_count_for_users(user_ids: list[int]) -> int:
    if not user_ids:
        return 0
    tokens = DevicePushToken.objects.filter(
        user_id__in=user_ids,
        platform=DevicePushToken.Platform.IOS,
    ).values_list("token", flat=True)
    return sum(1 for token in tokens if not is_likely_apns_device_token(token))


def users_with_sendable_ios_tokens(user_ids: list[int]) -> set[int]:
    if not user_ids:
        return set()
    rows = DevicePushToken.objects.filter(
        user_id__in=user_ids,
        platform=DevicePushToken.Platform.IOS,
    ).values_list("user_id", "token")
    eligible: set[int] = set()
    for user_id, token in rows:
        if not is_likely_apns_device_token(token):
            eligible.add(user_id)
    return eligible


def _staff_excluded_qs() -> Q:
    return Q(is_staff=True) | Q(is_superuser=True)


def verified_university_student_qs() -> QuerySet:
    """Strict student audience. Ambiguous faculty/email is excluded."""
    return (
        User.objects.filter(
            is_active=True,
            is_staff=False,
            is_superuser=False,
            profile__department__in=UNIVERSITY_FACULTY_VALUES,
        )
        .filter(Q(email__iendswith="@waseda.jp") | Q(email__iendswith=".waseda.jp"))
        .select_related("profile")
    )


def load_broadcast_recipient_users(*, test_user=None) -> list[Any]:
    if test_user is not None:
        if not getattr(test_user, "pk", None):
            return []
        if not user_allows_broadcast_push(test_user):
            return []
        if test_user.pk not in users_with_sendable_ios_tokens([test_user.pk]):
            return []
        return [test_user]

    candidates = list(verified_university_student_qs())
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


def preview_broadcast_audience(*, test_user=None) -> dict[str, int]:
    active = User.objects.filter(is_active=True)
    staff_excluded = active.filter(_staff_excluded_qs()).count()
    no_faculty = active.filter(is_staff=False, is_superuser=False).exclude(
        profile__department__in=UNIVERSITY_FACULTY_VALUES
    ).count()
    faculty_ok = verified_university_student_qs()
    faculty_ok_ids = list(faculty_ok.values_list("pk", flat=True))
    faculty_ok_users = list(faculty_ok)
    email_excluded = 0
    opt_out_excluded = 0
    email_ok_users = []
    for user in faculty_ok_users:
        email = getattr(user, "email", "") or ""
        if not is_waseda_student_email(email) or is_likely_test_account_email(email):
            email_excluded += 1
            continue
        if not user_allows_broadcast_push(user):
            opt_out_excluded += 1
            continue
        email_ok_users.append(user)
    email_ok_ids = [user.pk for user in email_ok_users]
    ios_ids = users_with_sendable_ios_tokens(email_ok_ids)
    no_ios = len(email_ok_ids) - len(ios_ids)
    recipients = load_broadcast_recipient_users(test_user=test_user)
    recipient_ids = [user.pk for user in recipients]
    return {
        "active_users": active.count(),
        "staff_excluded": staff_excluded,
        "not_university_faculty_excluded": no_faculty,
        "test_or_non_waseda_email_excluded": email_excluded,
        "broadcast_opt_out_excluded": opt_out_excluded,
        "no_ios_token_excluded": no_ios,
        "eligible_users": len(recipient_ids),
        "ios_tokens": ios_sendable_token_count_for_users(recipient_ids),
        "faculty_verified_count": len(faculty_ok_ids),
    }


def validate_campaign_key(campaign_key: str) -> str:
    key = (campaign_key or "").strip()
    if not CAMPAIGN_KEY_RE.fullmatch(key):
        raise BroadcastPushError(
            "campaign_key は 3〜80 文字の英数・._-: のみです。"
        )
    return key


def validate_copy(*, title: str, body: str) -> tuple[str, str]:
    title = (title or "").strip()
    body = (body or "").strip()
    if not title or not body:
        raise BroadcastPushError("title と body は必須です。")
    if len(title) > 80:
        raise BroadcastPushError("title は 80 文字以内です。")
    if len(body) > 200:
        raise BroadcastPushError("body は 200 文字以内です。")
    return title, body


def require_staff_actor(actor) -> None:
    if actor is None or not getattr(actor, "pk", None):
        raise BroadcastPushError("送信者（--actor-email）が必要です。")
    if not (
        getattr(actor, "is_staff", False) or getattr(actor, "is_superuser", False)
    ):
        raise BroadcastPushError("送信者は staff または superuser である必要があります。")
    if not getattr(actor, "is_active", False):
        raise BroadcastPushError("送信者アカウントが無効です。")


def load_visible_thread(thread_id: int) -> CommunityThread:
    thread = (
        CommunityThread.objects.select_related("community")
        .filter(pk=thread_id)
        .first()
    )
    if thread is None:
        raise BroadcastPushError(f"スレッド {thread_id} が見つかりません。")
    if thread.is_removed or not thread.community.is_active:
        raise BroadcastPushError("このスレッドは配信対象にできません。")
    return thread


def get_or_create_campaign(
    *,
    campaign_key: str,
    thread: CommunityThread,
    title: str,
    body: str,
    actor,
    test_user=None,
) -> tuple[PushCampaign, bool]:
    mode = (
        PushCampaign.Mode.TEST
        if test_user is not None
        else PushCampaign.Mode.BROADCAST
    )
    link = community_thread_push_link(thread)
    campaign, created = PushCampaign.objects.get_or_create(
        campaign_key=campaign_key,
        defaults={
            "thread": thread,
            "thread_id_snapshot": thread.pk,
            "community_slug": thread.community.slug,
            "title": title,
            "body": body,
            "link": link,
            "mode": mode,
            "created_by": actor,
        },
    )
    if not created:
        if campaign.mode != mode:
            raise BroadcastPushError(
                "同じ campaign_key が別モード（test/broadcast）で既に存在します。"
            )
        if campaign.thread_id_snapshot != thread.pk:
            raise BroadcastPushError(
                "同じ campaign_key が別スレッドで既に使われています。"
            )
    return campaign, created


def freeze_campaign_recipients(
    campaign: PushCampaign, *, test_user=None
) -> list[PushCampaignRecipient]:
    users = load_broadcast_recipient_users(test_user=test_user)
    rows = [
        PushCampaignRecipient(campaign=campaign, user=user)
        for user in users
    ]
    if rows:
        PushCampaignRecipient.objects.bulk_create(rows, ignore_conflicts=True)
    recipient_ids = list(
        campaign.recipients.values_list("user_id", flat=True)
    )
    campaign.eligible_user_count = len(recipient_ids)
    campaign.token_count = ios_sendable_token_count_for_users(recipient_ids)
    campaign.save(update_fields=["eligible_user_count", "token_count", "updated_at"])
    return list(campaign.recipients.select_related("user"))


def _mark_stale_sending_unknown(campaign: PushCampaign) -> int:
    """Crash / kill leftover. Do not retry; FCM may already have accepted the job."""
    now = timezone.now()
    return campaign.recipients.filter(
        status=PushCampaignRecipient.Status.SENDING
    ).update(
        status=PushCampaignRecipient.Status.UNKNOWN,
        reason="interrupted",
        finished_at=now,
    )


_CLAIMABLE_STATUSES = (
    PushCampaignRecipient.Status.PENDING,
    PushCampaignRecipient.Status.FAILED,
)


def claim_recipient(recipient: PushCampaignRecipient) -> bool:
    """Claim pending or failed rows. Never claim sent/unknown/sending."""
    now = timezone.now()
    updated = PushCampaignRecipient.objects.filter(
        pk=recipient.pk,
        status__in=_CLAIMABLE_STATUSES,
    ).update(
        status=PushCampaignRecipient.Status.SENDING,
        claimed_at=now,
        finished_at=None,
        reason="",
    )
    return updated == 1


def _finalize_recipient(
    recipient: PushCampaignRecipient,
    result,
) -> str:
    now = timezone.now()
    if result.outcome == PushDeliveryOutcome.SENT:
        status = PushCampaignRecipient.Status.SENT
    elif result.outcome == PushDeliveryOutcome.UNKNOWN:
        status = PushCampaignRecipient.Status.UNKNOWN
    elif result.outcome == PushDeliveryOutcome.SKIPPED:
        status = PushCampaignRecipient.Status.FAILED
    else:
        status = PushCampaignRecipient.Status.FAILED
    PushCampaignRecipient.objects.filter(
        pk=recipient.pk,
        status=PushCampaignRecipient.Status.SENDING,
    ).update(
        status=status,
        success_count=result.success_count,
        reason=(result.reason or "")[:64],
        finished_at=now,
    )
    return status


def send_frozen_campaign(campaign: PushCampaign) -> dict[str, int]:
    stale = _mark_stale_sending_unknown(campaign)
    if campaign.status != PushCampaign.Status.COMPLETED:
        campaign.status = PushCampaign.Status.SENDING
        if campaign.started_at is None:
            campaign.started_at = timezone.now()
        campaign.save(update_fields=["status", "started_at", "updated_at"])

    counts = {
        "claimed": 0,
        "sent": 0,
        "failed": 0,
        "unknown": 0,
        "skipped_locked": 0,
        "already_terminal": 0,
        "stale_sending_to_unknown": stale,
    }
    recipients = list(
        campaign.recipients.select_related("user").order_by("pk")
    )
    for recipient in recipients:
        if recipient.status in TERMINAL_RECIPIENT_STATUSES:
            counts["already_terminal"] += 1
            continue
        if recipient.status not in _CLAIMABLE_STATUSES:
            counts["skipped_locked"] += 1
            continue
        if not claim_recipient(recipient):
            counts["skipped_locked"] += 1
            continue
        counts["claimed"] += 1
        result = deliver_push_to_user(
            recipient.user,
            title=campaign.title,
            body=campaign.body,
            link=campaign.link,
            notification_id="",
            notification_type=PUSH_KIND_COMMUNITY_THREAD_BROADCAST,
        )
        status = _finalize_recipient(recipient, result)
        if status == PushCampaignRecipient.Status.SENT:
            counts["sent"] += 1
        elif status == PushCampaignRecipient.Status.UNKNOWN:
            counts["unknown"] += 1
        else:
            counts["failed"] += 1

    remaining_pending = campaign.recipients.filter(
        status=PushCampaignRecipient.Status.PENDING
    ).exists()
    remaining_sending = campaign.recipients.filter(
        status=PushCampaignRecipient.Status.SENDING
    ).exists()
    if not remaining_pending and not remaining_sending:
        campaign.status = PushCampaign.Status.COMPLETED
        campaign.finished_at = timezone.now()
        campaign.save(update_fields=["status", "finished_at", "updated_at"])
    return counts


def execute_community_thread_push(
    *,
    thread: CommunityThread,
    title: str,
    body: str,
    campaign_key: str,
    actor,
    test_user=None,
) -> dict[str, Any]:
    require_staff_actor(actor)
    title, body = validate_copy(title=title, body=body)
    campaign_key = validate_campaign_key(campaign_key)
    with transaction.atomic():
        campaign, created = get_or_create_campaign(
            campaign_key=campaign_key,
            thread=thread,
            title=title,
            body=body,
            actor=actor,
            test_user=test_user,
        )
        if not campaign.recipients.exists():
            freeze_campaign_recipients(campaign, test_user=test_user)
    send_counts = send_frozen_campaign(campaign)
    campaign.refresh_from_db()
    status_counts = {
        row["status"]: row["n"]
        for row in campaign.recipients.values("status").annotate(n=Count("id"))
    }
    return {
        "created": created,
        "campaign_key": campaign.campaign_key,
        "mode": campaign.mode,
        "status": campaign.status,
        "link": campaign.link,
        "eligible_users": campaign.eligible_user_count,
        "ios_tokens": campaign.token_count,
        "recipient_status": status_counts,
        "send": send_counts,
        "in_app_notifications_created": 0,
    }
