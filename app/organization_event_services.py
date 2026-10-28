"""学生団体の新歓イベント作成・公開・申込。個人カレンダー CalendarEvent とは独立。"""

from __future__ import annotations

import logging
from datetime import datetime, timezone as dt_timezone
from typing import Any, Callable, Iterable
from zoneinfo import ZoneInfo

from django.contrib.auth.models import AbstractBaseUser
from django.db import IntegrityError, OperationalError, transaction
from django.db.models import Count, Q
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from .models import (
    Organization,
    OrganizationChatShare,
    OrganizationEvent,
    OrganizationEventLottery,
    OrganizationEventRegistration,
)
from .notification_services import create_notification
from .organization_api_services import get_organization_avatar_url
from .organization_services import (
    can_manage_organization,
    can_view_organization_profile,
    is_organization_admin,
)
from .spa_canonical import organization_event_url
from .timeline_api_services import serialize_author

logger = logging.getLogger(__name__)

TOKYO = ZoneInfo("Asia/Tokyo")

TITLE_MAX = OrganizationEvent._meta.get_field("title").max_length
DESCRIPTION_MAX = 5000
VENUE_NAME_MAX = OrganizationEvent._meta.get_field("venue_name").max_length
VENUE_ADDRESS_MAX = OrganizationEvent._meta.get_field("venue_address").max_length

EVENT_LIST_PAGE = 20
REGISTRATION_LIST_PAGE = 30
MY_REGISTRATION_PAGE = 20

IMPORTANT_CHANGE_FIELDS = frozenset(
    {"starts_at", "ends_at", "venue_name", "venue_address"}
)

PUSH_KIND_ORG_EVENT_REGISTERED = "org_event_registered"
PUSH_KIND_ORG_EVENT_CANCELLED = "org_event_cancelled"
PUSH_KIND_ORG_EVENT_UPDATED = "org_event_updated"


class OrganizationEventError(ValueError):
    def __init__(self, code: str, status: int = 400, **extra: Any):
        self.code = code
        self.status = status
        self.extra = extra
        super().__init__(code)


def _authenticated_user(user: AbstractBaseUser | None) -> bool:
    return bool(
        user is not None
        and getattr(user, "pk", None)
        and getattr(user, "is_authenticated", False)
        and getattr(user, "is_active", True)
    )


def organization_allows_event_access(organization: Organization | None) -> bool:
    if organization is None or not getattr(organization, "pk", None):
        return False
    return organization.status != Organization.Status.SUSPENDED


def _run_after_commit(fn: Callable[[], None]) -> None:
    def _runner() -> None:
        try:
            fn()
        except Exception:
            logger.exception("organization event after-commit callback failed")

    transaction.on_commit(_runner)


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    dt = value
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.get_current_timezone())
    return dt.astimezone(dt_timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_datetime(value: Any, *, field: str) -> datetime:
    if isinstance(value, datetime):
        dt = value
    else:
        raw = str(value or "").strip()
        if not raw:
            raise OrganizationEventError(
                "invalid_payload",
                status=400,
                errors={field: "日時を入力してください。"},
            )
        dt = parse_datetime(raw)
        if dt is None:
            raise OrganizationEventError(
                "invalid_payload",
                status=400,
                errors={field: "日時の形式が正しくありません。"},
            )
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, TOKYO)
    return dt.astimezone(dt_timezone.utc)


def _optional_datetime(value: Any, *, field: str) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return None
    return _parse_datetime(value, field=field)


def _clean_text(value: Any, *, field: str, max_length: int, required: bool) -> str:
    if value is None:
        text = ""
    else:
        text = str(value).replace("\x00", "").strip()
    if required and not text:
        raise OrganizationEventError(
            "invalid_payload",
            status=400,
            errors={field: "入力してください。"},
        )
    if len(text) > max_length:
        raise OrganizationEventError(
            "invalid_payload",
            status=400,
            errors={field: f"{max_length}文字以内で入力してください。"},
        )
    return text


def _parse_bool(value: Any, *, default: bool | None = None) -> bool:
    if value is None:
        if default is None:
            raise OrganizationEventError("invalid_payload", status=400)
        return default
    if isinstance(value, bool):
        return value
    raw = str(value).strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    raise OrganizationEventError("invalid_payload", status=400)


def _page_args(offset: int | None, limit: int | None, default: int) -> tuple[int, int]:
    try:
        start = max(0, int(offset or 0))
    except (TypeError, ValueError):
        start = 0
    try:
        size = int(limit if limit is not None else default)
    except (TypeError, ValueError):
        size = default
    size = max(1, min(size, 50))
    return start, size


def registered_count_for(event: OrganizationEvent) -> int:
    return OrganizationEventRegistration.objects.filter(
        event_id=event.pk,
        status=OrganizationEventRegistration.Status.REGISTERED,
    ).count()


def viewer_registration_status(
    event: OrganizationEvent, viewer: AbstractBaseUser | None
) -> str | None:
    if not _authenticated_user(viewer):
        return None
    return (
        OrganizationEventRegistration.objects.filter(
            event_id=event.pk, user_id=viewer.pk
        )
        .values_list("status", flat=True)
        .first()
    )


def _now() -> datetime:
    return timezone.now()


def event_has_ended(event: OrganizationEvent, *, now: datetime | None = None) -> bool:
    current = now or _now()
    return event.ends_at <= current


def event_deadline_passed(
    event: OrganizationEvent, *, now: datetime | None = None
) -> bool:
    if event.registration_deadline is None:
        return False
    return event.registration_deadline <= (now or _now())


def event_uses_registration(event: OrganizationEvent) -> bool:
    mode = getattr(
        event, "signup_mode", OrganizationEvent.SignupMode.REGISTRATION
    )
    return mode == OrganizationEvent.SignupMode.REGISTRATION


def event_registration_is_closed(
    event: OrganizationEvent, *, now: datetime | None = None
) -> bool:
    if not event_uses_registration(event):
        return True
    if not event.registration_open:
        return True
    return event_deadline_passed(event, now=now)


def _parse_signup_mode(value: Any, *, default: str | None) -> str | None:
    if value is None:
        return default
    raw = str(value).strip().lower()
    if raw not in {
        OrganizationEvent.SignupMode.REGISTRATION,
        OrganizationEvent.SignupMode.ANNOUNCEMENT,
    }:
        raise OrganizationEventError(
            "invalid_payload",
            status=400,
            errors={"signup_mode": "申込方式を選択してください。"},
        )
    return raw


def can_view_organization_event(
    viewer: AbstractBaseUser | None, event: OrganizationEvent | None
) -> bool:
    if event is None or event.deleted_at is not None:
        return False
    organization = event.organization
    if not can_view_organization_profile(viewer, organization):
        return False
    if not organization_allows_event_access(organization):
        return is_organization_admin(viewer, organization)
    if can_manage_organization(viewer, organization):
        return True
    return event.status in {
        OrganizationEvent.Status.PUBLISHED,
        OrganizationEvent.Status.CANCELLED,
    }


def _require_manage(actor: AbstractBaseUser | None, organization: Organization) -> None:
    if not _authenticated_user(actor):
        raise OrganizationEventError("unauthorized", status=401)
    if not can_view_organization_profile(actor, organization):
        raise OrganizationEventError("not_found", status=404)
    if organization.status == Organization.Status.SUSPENDED:
        raise OrganizationEventError("organization_suspended", status=403)
    if not can_manage_organization(actor, organization):
        raise OrganizationEventError("forbidden", status=403)


def _lock_event(event_id: int) -> OrganizationEvent:
    try:
        return (
            OrganizationEvent.objects.select_for_update()
            .select_related("organization")
            .get(pk=event_id)
        )
    except OrganizationEvent.DoesNotExist as exc:
        raise OrganizationEventError("not_found", status=404) from exc


def event_has_completed_lottery(event_id: int) -> bool:
    return OrganizationEventLottery.objects.filter(event_id=event_id).exists()


def get_event_for_organization(
    organization: Organization, event_id: int
) -> OrganizationEvent | None:
    return (
        OrganizationEvent.objects.select_related("organization")
        .filter(pk=event_id, organization_id=organization.pk)
        .first()
    )


def _validate_schedule(
    *,
    starts_at: datetime,
    ends_at: datetime,
    registration_deadline: datetime | None,
) -> None:
    errors: dict[str, str] = {}
    if ends_at <= starts_at:
        errors["ends_at"] = "終了日時は開始日時より後にしてください。"
    if registration_deadline is not None and registration_deadline > starts_at:
        errors["registration_deadline"] = "申込締切は開始日時以前にしてください。"
    if errors:
        raise OrganizationEventError("invalid_payload", status=400, errors=errors)


def _fields_from_payload(payload: dict[str, Any], *, partial: bool) -> dict[str, Any]:
    data: dict[str, Any] = {}
    if not partial or "title" in payload:
        data["title"] = _clean_text(
            payload.get("title"), field="title", max_length=TITLE_MAX, required=True
        )
    if not partial or "description" in payload:
        data["description"] = _clean_text(
            payload.get("description"),
            field="description",
            max_length=DESCRIPTION_MAX,
            required=False,
        )
    if not partial or "venue_name" in payload:
        data["venue_name"] = _clean_text(
            payload.get("venue_name"),
            field="venue_name",
            max_length=VENUE_NAME_MAX,
            required=True,
        )
    if not partial or "venue_address" in payload:
        data["venue_address"] = _clean_text(
            payload.get("venue_address"),
            field="venue_address",
            max_length=VENUE_ADDRESS_MAX,
            required=False,
        )
    if not partial or "starts_at" in payload:
        data["starts_at"] = _parse_datetime(payload.get("starts_at"), field="starts_at")
    if not partial or "ends_at" in payload:
        data["ends_at"] = _parse_datetime(payload.get("ends_at"), field="ends_at")
    if not partial or "registration_deadline" in payload:
        data["registration_deadline"] = _optional_datetime(
            payload.get("registration_deadline"), field="registration_deadline"
        )
    if not partial or "registration_open" in payload:
        data["registration_open"] = _parse_bool(
            payload.get("registration_open"), default=True if not partial else None
        )
    if not partial or "signup_mode" in payload:
        parsed_mode = _parse_signup_mode(
            payload.get("signup_mode"),
            default=(
                OrganizationEvent.SignupMode.REGISTRATION if not partial else None
            ),
        )
        if parsed_mode is not None:
            data["signup_mode"] = parsed_mode
    return data


def serialize_organization_event(
    event: OrganizationEvent,
    viewer: AbstractBaseUser | None,
    *,
    registered_count: int | None = None,
    viewer_status: str | None = None,
    include_manage: bool | None = None,
    lottery: Any | None = None,
    lottery_loaded: bool = False,
    viewer_lottery_result: str | None = None,
    viewer_lottery_loaded: bool = False,
    can_view_lottery: bool | None = None,
) -> dict[str, Any]:
    from .organization_event_lottery_services import (
        can_view_event_lottery_lists,
        lottery_for_event,
        lottery_has_live_share,
        viewer_lottery_results_by_event,
    )

    organization = event.organization
    count = (
        registered_count
        if registered_count is not None
        else registered_count_for(event)
    )
    status = (
        viewer_status
        if viewer_status is not None
        else viewer_registration_status(event, viewer)
    )
    manage = (
        include_manage
        if include_manage is not None
        else can_manage_organization(viewer, organization)
    )
    now = _now()
    ended = event_has_ended(event, now=now)
    deadline = event_deadline_passed(event, now=now)
    published = event.status == OrganizationEvent.Status.PUBLISHED
    cancelled = event.status == OrganizationEvent.Status.CANCELLED
    viewer_registered = status == OrganizationEventRegistration.Status.REGISTERED
    if not lottery_loaded:
        lottery = lottery_for_event(event)
    has_lottery = lottery is not None
    uses_registration = event_uses_registration(event)
    registration_closed = event_registration_is_closed(event, now=now)
    can_register = bool(
        _authenticated_user(viewer)
        and published
        and uses_registration
        and event.registration_open
        and not has_lottery
        and not ended
        and not deadline
        and not viewer_registered
        and event.deleted_at is None
        and organization_allows_event_access(organization)
    )
    can_cancel_registration = bool(
        viewer_registered
        and uses_registration
        and event.deleted_at is None
        and not cancelled
        and organization_allows_event_access(organization)
        and (has_lottery or not registration_closed)
    )
    if (
        not viewer_lottery_loaded
        and viewer_lottery_result is None
        and has_lottery
        and _authenticated_user(viewer)
    ):
        viewer_lottery_result = viewer_lottery_results_by_event(
            [event.pk], viewer
        ).get(event.pk)
    if can_view_lottery is None:
        can_view_lottery = can_view_event_lottery_lists(viewer, organization)
    can_run_lottery = bool(
        manage
        and published
        and uses_registration
        and registration_closed
        and not has_lottery
        and event.deleted_at is None
        and organization_allows_event_access(organization)
    )
    can_share_to_timeline = bool(
        manage
        and published
        and not cancelled
        and event.deleted_at is None
        and organization_allows_event_access(organization)
    )
    shared = bool(has_lottery and lottery_has_live_share(lottery))
    return {
        "id": event.pk,
        "organization_id": organization.pk,
        "organization_slug": organization.slug,
        "organization_name": organization.name,
        "organization_avatar_url": get_organization_avatar_url(organization),
        "title": event.title,
        "description": event.description or "",
        "starts_at": _iso(event.starts_at),
        "ends_at": _iso(event.ends_at),
        "venue_name": event.venue_name,
        "venue_address": event.venue_address or "",
        "registration_deadline": _iso(event.registration_deadline),
        "status": event.status,
        "signup_mode": (
            event.signup_mode
            if event.signup_mode
            else OrganizationEvent.SignupMode.REGISTRATION
        ),
        "registration_open": bool(event.registration_open),
        "registration_closed": registration_closed,
        "registered_count": count,
        "is_ended": ended,
        "is_deadline_passed": deadline,
        "viewer_status": status,
        "viewer_registered": viewer_registered,
        "can_register": can_register,
        "can_cancel_registration": can_cancel_registration,
        "can_manage": manage,
        "has_lottery": has_lottery,
        "lottery_executed_at": _iso(lottery.executed_at) if lottery else None,
        "lottery_applicant_count": lottery.applicant_count if lottery else None,
        "lottery_eligible_count": lottery.eligible_count if lottery else None,
        "lottery_winner_count": lottery.winner_count if lottery else None,
        "lottery_not_selected_count": (
            max(0, int(lottery.eligible_count) - int(lottery.winner_count))
            if lottery
            else None
        ),
        "lottery_excluded_count": lottery.excluded_count if lottery else None,
        "lottery_shared": shared,
        "viewer_lottery_result": viewer_lottery_result,
        "can_run_lottery": can_run_lottery,
        "can_view_lottery": bool(has_lottery and can_view_lottery),
        "can_share_lottery": bool(manage and has_lottery and not shared),
        "can_share_to_timeline": can_share_to_timeline,
        "can_reopen_registration": bool(
            manage
            and uses_registration
            and not has_lottery
            and not cancelled
            and event.deleted_at is None
            and organization_allows_event_access(organization)
        ),
        "created_at": _iso(event.created_at),
        "updated_at": _iso(event.updated_at),
    }


def _event_link(event: OrganizationEvent) -> str:
    return organization_event_url(event.organization.slug, event.pk)


def _notify_registered(event: OrganizationEvent, user_id: int) -> None:
    org_name = event.organization.name
    create_notification(
        recipient_id=user_id,
        message=(
            f"「{org_name}」のイベント「{event.title}」に申し込みました。"
        ),
        link=_event_link(event),
        actor=None,
        push_kind=PUSH_KIND_ORG_EVENT_REGISTERED,
        push_body="イベントに申し込みました",
    )


def _notify_event_cancelled(event: OrganizationEvent, user_ids: list[int]) -> None:
    org_name = event.organization.name
    link = _event_link(event)
    for user_id in user_ids:
        create_notification(
            recipient_id=user_id,
            message=(
                f"「{org_name}」のイベント「{event.title}」が中止になりました。"
            ),
            link=link,
            actor=None,
            push_kind=PUSH_KIND_ORG_EVENT_CANCELLED,
            push_body="申し込み中のイベントが中止になりました",
        )


def _notify_event_updated(event: OrganizationEvent, user_ids: list[int]) -> None:
    org_name = event.organization.name
    link = _event_link(event)
    for user_id in user_ids:
        create_notification(
            recipient_id=user_id,
            message=(
                f"「{org_name}」のイベント「{event.title}」の日時または会場が"
                "変更されました。"
            ),
            link=link,
            actor=None,
            push_kind=PUSH_KIND_ORG_EVENT_UPDATED,
            push_body="申し込み中のイベントの内容が更新されました",
        )


def _registered_user_ids(event: OrganizationEvent) -> list[int]:
    return list(
        OrganizationEventRegistration.objects.filter(
            event_id=event.pk,
            status=OrganizationEventRegistration.Status.REGISTERED,
        ).values_list("user_id", flat=True)
    )


def create_organization_event(
    *,
    organization: Organization,
    actor: AbstractBaseUser,
    payload: dict[str, Any],
) -> OrganizationEvent:
    _require_manage(actor, organization)
    fields = _fields_from_payload(payload, partial=False)
    if fields.get("signup_mode") == OrganizationEvent.SignupMode.ANNOUNCEMENT:
        fields["registration_open"] = False
        fields["registration_deadline"] = None
    _validate_schedule(
        starts_at=fields["starts_at"],
        ends_at=fields["ends_at"],
        registration_deadline=fields.get("registration_deadline"),
    )
    event = OrganizationEvent.objects.create(
        organization=organization,
        created_by=actor,
        status=OrganizationEvent.Status.DRAFT,
        **fields,
    )
    return event


def update_organization_event(
    *,
    event: OrganizationEvent,
    actor: AbstractBaseUser,
    payload: dict[str, Any],
) -> OrganizationEvent:
    organization = event.organization
    _require_manage(actor, organization)
    if event.deleted_at is not None:
        raise OrganizationEventError("not_found", status=404)
    forbidden = {
        "id",
        "pk",
        "organization",
        "organization_id",
        "created_by",
        "created_at",
        "updated_at",
        "deleted_at",
        "status",
    }
    if forbidden.intersection(payload.keys()):
        raise OrganizationEventError("forbidden_field", status=400)

    fields = _fields_from_payload(payload, partial=True)
    starts_at = fields.get("starts_at", event.starts_at)
    ends_at = fields.get("ends_at", event.ends_at)
    deadline = (
        fields["registration_deadline"]
        if "registration_deadline" in fields
        else event.registration_deadline
    )
    _validate_schedule(
        starts_at=starts_at, ends_at=ends_at, registration_deadline=deadline
    )

    with transaction.atomic():
        locked = _lock_event(event.pk)
        if locked.deleted_at is not None:
            raise OrganizationEventError("not_found", status=404)
        next_mode = fields.get("signup_mode", locked.signup_mode)
        has_lottery = event_has_completed_lottery(locked.pk)
        if has_lottery and (
            "signup_mode" in fields and fields["signup_mode"] != locked.signup_mode
        ):
            raise OrganizationEventError("lottery_closed", status=409)
        if (
            next_mode == OrganizationEvent.SignupMode.ANNOUNCEMENT
            and locked.signup_mode != OrganizationEvent.SignupMode.ANNOUNCEMENT
        ):
            if has_lottery:
                raise OrganizationEventError("lottery_closed", status=409)
            if OrganizationEventRegistration.objects.filter(
                event_id=locked.pk,
                status=OrganizationEventRegistration.Status.REGISTERED,
            ).exists():
                raise OrganizationEventError("has_registrations", status=409)
        if fields.get("registration_open") is True and has_lottery:
            raise OrganizationEventError("lottery_closed", status=409)
        if next_mode == OrganizationEvent.SignupMode.ANNOUNCEMENT:
            fields["registration_open"] = False
            if "registration_deadline" not in fields:
                fields["registration_deadline"] = None
        changed_important = False
        for key, value in fields.items():
            if key in IMPORTANT_CHANGE_FIELDS and getattr(locked, key) != value:
                changed_important = True
            setattr(locked, key, value)
        locked.save()
        notify_ids: list[int] = []
        if (
            changed_important
            and locked.status == OrganizationEvent.Status.PUBLISHED
        ):
            notify_ids = _registered_user_ids(locked)
        event_id = locked.pk

    if notify_ids:
        _run_after_commit(
            lambda: _notify_event_updated(
                OrganizationEvent.objects.select_related("organization").get(
                    pk=event_id
                ),
                notify_ids,
            )
        )
    return (
        OrganizationEvent.objects.select_related("organization").get(pk=event.pk)
    )


def publish_organization_event(
    *, event: OrganizationEvent, actor: AbstractBaseUser
) -> OrganizationEvent:
    _require_manage(actor, event.organization)
    with transaction.atomic():
        locked = _lock_event(event.pk)
        if locked.deleted_at is not None:
            raise OrganizationEventError("not_found", status=404)
        if locked.status == OrganizationEvent.Status.CANCELLED:
            raise OrganizationEventError("cancelled", status=409)
        locked.status = OrganizationEvent.Status.PUBLISHED
        locked.save(update_fields=["status", "updated_at"])
        return locked


def unpublish_organization_event(
    *, event: OrganizationEvent, actor: AbstractBaseUser
) -> OrganizationEvent:
    _require_manage(actor, event.organization)
    with transaction.atomic():
        locked = _lock_event(event.pk)
        if locked.deleted_at is not None:
            raise OrganizationEventError("not_found", status=404)
        if locked.status == OrganizationEvent.Status.CANCELLED:
            raise OrganizationEventError("cancelled", status=409)
        locked.status = OrganizationEvent.Status.DRAFT
        locked.save(update_fields=["status", "updated_at"])
        return locked


def cancel_organization_event(
    *, event: OrganizationEvent, actor: AbstractBaseUser
) -> OrganizationEvent:
    _require_manage(actor, event.organization)
    with transaction.atomic():
        locked = _lock_event(event.pk)
        if locked.deleted_at is not None:
            raise OrganizationEventError("not_found", status=404)
        already = locked.status == OrganizationEvent.Status.CANCELLED
        notify_ids = [] if already else _registered_user_ids(locked)
        locked.status = OrganizationEvent.Status.CANCELLED
        locked.registration_open = False
        locked.save(update_fields=["status", "registration_open", "updated_at"])
        event_id = locked.pk
    if notify_ids:
        _run_after_commit(
            lambda: _notify_event_cancelled(
                OrganizationEvent.objects.select_related("organization").get(
                    pk=event_id
                ),
                notify_ids,
            )
        )
    return OrganizationEvent.objects.select_related("organization").get(pk=event.pk)


def delete_organization_event(
    *, event: OrganizationEvent, actor: AbstractBaseUser
) -> None:
    _require_manage(actor, event.organization)
    with transaction.atomic():
        locked = _lock_event(event.pk)
        if locked.deleted_at is not None:
            return
        notify_ids: list[int] = []
        if locked.status != OrganizationEvent.Status.CANCELLED:
            notify_ids = _registered_user_ids(locked)
            locked.status = OrganizationEvent.Status.CANCELLED
            locked.registration_open = False
        locked.deleted_at = timezone.now()
        locked.save(
            update_fields=["status", "registration_open", "deleted_at", "updated_at"]
        )
        from .organization_event_timeline_services import (
            unlist_organization_event_timeline_shares,
        )

        unlist_organization_event_timeline_shares(locked.pk)
        event_id = locked.pk
    if notify_ids:
        _run_after_commit(
            lambda: _notify_event_cancelled(
                OrganizationEvent.objects.select_related("organization").get(
                    pk=event_id
                ),
                notify_ids,
            )
        )


def _assert_can_register(event: OrganizationEvent, user: AbstractBaseUser) -> None:
    if not _authenticated_user(user):
        raise OrganizationEventError("unauthorized", status=401)
    organization = event.organization
    if event.deleted_at is not None:
        raise OrganizationEventError("not_found", status=404)
    if not can_view_organization_profile(user, organization):
        raise OrganizationEventError("not_found", status=404)
    if not organization_allows_event_access(organization):
        raise OrganizationEventError("organization_suspended", status=403)
    if event.status == OrganizationEvent.Status.CANCELLED:
        raise OrganizationEventError("cancelled", status=409)
    if event.status != OrganizationEvent.Status.PUBLISHED:
        raise OrganizationEventError("not_found", status=404)
    if not event_uses_registration(event):
        raise OrganizationEventError("announcement_only", status=409)
    if event_has_completed_lottery(event.pk):
        raise OrganizationEventError("lottery_closed", status=409)
    if not event.registration_open:
        raise OrganizationEventError("registration_closed", status=409)
    if event_has_ended(event):
        raise OrganizationEventError("ended", status=409)
    if event_deadline_passed(event):
        raise OrganizationEventError("deadline_passed", status=409)


def register_organization_event(
    *, event: OrganizationEvent, user: AbstractBaseUser
) -> OrganizationEventRegistration:
    if not _authenticated_user(user):
        raise OrganizationEventError("unauthorized", status=401)
    _assert_can_register(event, user)

    with transaction.atomic():
        locked = _lock_event(event.pk)
        _assert_can_register(locked, user)
        existing = (
            OrganizationEventRegistration.objects.select_for_update()
            .filter(event_id=locked.pk, user_id=user.pk)
            .first()
        )
        if (
            existing
            and existing.status == OrganizationEventRegistration.Status.REGISTERED
        ):
            return existing
        if existing is None:
            try:
                with transaction.atomic():
                    registration = OrganizationEventRegistration.objects.create(
                        event=locked,
                        user=user,
                        status=OrganizationEventRegistration.Status.REGISTERED,
                    )
            except IntegrityError:
                registration = (
                    OrganizationEventRegistration.objects.select_for_update()
                    .filter(event_id=locked.pk, user_id=user.pk)
                    .first()
                )
                if registration is None:
                    raise OrganizationEventError("busy", status=409)
                if (
                    registration.status
                    == OrganizationEventRegistration.Status.REGISTERED
                ):
                    return registration
                registration.status = OrganizationEventRegistration.Status.REGISTERED
                registration.save(update_fields=["status", "updated_at"])
        else:
            existing.status = OrganizationEventRegistration.Status.REGISTERED
            existing.save(update_fields=["status", "updated_at"])
            registration = existing
        event_id = locked.pk
        user_id = user.pk

    _run_after_commit(
        lambda: _notify_registered(
            OrganizationEvent.objects.select_related("organization").get(pk=event_id),
            user_id,
        )
    )
    return registration


def unregister_organization_event(
    *, event: OrganizationEvent, user: AbstractBaseUser
) -> OrganizationEventRegistration:
    if not _authenticated_user(user):
        raise OrganizationEventError("unauthorized", status=401)
    organization = event.organization
    if event.deleted_at is not None or not can_view_organization_profile(
        user, organization
    ):
        raise OrganizationEventError("not_found", status=404)
    if not organization_allows_event_access(organization):
        raise OrganizationEventError("organization_suspended", status=403)

    with transaction.atomic():
        locked = _lock_event(event.pk)
        if locked.deleted_at is not None:
            raise OrganizationEventError("not_found", status=404)
        if not event_uses_registration(locked):
            raise OrganizationEventError("announcement_only", status=409)
        if locked.status == OrganizationEvent.Status.CANCELLED:
            raise OrganizationEventError("cancelled", status=409)
        has_lottery = event_has_completed_lottery(locked.pk)
        if not has_lottery and event_registration_is_closed(locked):
            raise OrganizationEventError("registration_closed", status=409)
        row = (
            OrganizationEventRegistration.objects.select_for_update()
            .filter(event_id=locked.pk, user_id=user.pk)
            .first()
        )
        if row is None or row.status != OrganizationEventRegistration.Status.REGISTERED:
            raise OrganizationEventError("not_registered", status=409)
        row.status = OrganizationEventRegistration.Status.CANCELLED
        row.save(update_fields=["status", "updated_at"])
        return row


def list_organization_events_payload(
    organization: Organization,
    viewer: AbstractBaseUser | None,
    *,
    offset: int = 0,
    limit: int | None = None,
    manage: bool = False,
) -> dict[str, Any]:
    if not can_view_organization_profile(viewer, organization):
        raise OrganizationEventError("not_found", status=404)
    start, page_size = _page_args(offset, limit, EVENT_LIST_PAGE)
    queryset = OrganizationEvent.objects.filter(
        organization=organization, deleted_at__isnull=True
    )
    is_manager = can_manage_organization(viewer, organization)
    if manage:
        if not is_manager:
            raise OrganizationEventError("forbidden", status=403)
    else:
        queryset = queryset.filter(
            status__in=[
                OrganizationEvent.Status.PUBLISHED,
                OrganizationEvent.Status.CANCELLED,
            ]
        )
    queryset = queryset.annotate(
        _registered_count=Count(
            "registrations",
            filter=Q(
                registrations__status=OrganizationEventRegistration.Status.REGISTERED
            ),
        )
    ).order_by("starts_at", "pk")
    total = queryset.count()
    page = list(queryset[start : start + page_size])
    viewer_map: dict[int, str] = {}
    lottery_map: dict[int, Any] = {}
    viewer_lottery_map: dict[int, str] = {}
    page_ids = [row.pk for row in page]
    if page:
        from .organization_event_lottery_services import (
            can_view_event_lottery_lists,
            lotteries_by_event_ids,
            viewer_lottery_results_by_event,
        )

        lottery_map = lotteries_by_event_ids(page_ids)
        if _authenticated_user(viewer):
            viewer_lottery_map = viewer_lottery_results_by_event(page_ids, viewer)
        can_view_lottery = can_view_event_lottery_lists(viewer, organization)
    else:
        can_view_lottery = False
    if _authenticated_user(viewer) and page:
        viewer_map = {
            event_id: status
            for event_id, status in OrganizationEventRegistration.objects.filter(
                event_id__in=page_ids, user_id=viewer.pk
            ).values_list("event_id", "status")
        }
    events = [
        serialize_organization_event(
            row,
            viewer,
            registered_count=getattr(row, "_registered_count", None),
            viewer_status=viewer_map.get(row.pk),
            include_manage=is_manager,
            lottery=lottery_map.get(row.pk),
            lottery_loaded=True,
            viewer_lottery_result=viewer_lottery_map.get(row.pk),
            viewer_lottery_loaded=True,
            can_view_lottery=can_view_lottery,
        )
        for row in page
    ]
    next_offset = start + len(events)
    return {
        "ok": True,
        "events": events,
        "has_more": next_offset < total,
        "next_offset": next_offset,
        "can_manage": is_manager,
    }


def get_organization_event_payload(
    organization: Organization,
    event_id: int,
    viewer: AbstractBaseUser | None,
) -> dict[str, Any]:
    event = get_event_for_organization(organization, event_id)
    if event is None or not can_view_organization_event(viewer, event):
        raise OrganizationEventError("not_found", status=404)
    return {
        "ok": True,
        "event": serialize_organization_event(event, viewer),
    }


def list_event_registrations_payload(
    *,
    event: OrganizationEvent,
    actor: AbstractBaseUser,
    offset: int = 0,
    limit: int | None = None,
) -> dict[str, Any]:
    _require_manage(actor, event.organization)
    if event.deleted_at is not None:
        raise OrganizationEventError("not_found", status=404)
    start, page_size = _page_args(offset, limit, REGISTRATION_LIST_PAGE)
    queryset = (
        OrganizationEventRegistration.objects.filter(
            event=event, status=OrganizationEventRegistration.Status.REGISTERED
        )
        .select_related("user", "user__profile")
        .order_by("created_at", "pk")
    )
    total = queryset.count()
    page = list(queryset[start : start + page_size])
    registrations = []
    for row in page:
        author = serialize_author(row.user) or {}
        registrations.append(
            {
                "id": row.pk,
                "status": row.status,
                "created_at": _iso(row.created_at),
                "user": {
                    "id": author.get("id"),
                    "username": author.get("username") or "",
                    "display_name": author.get("display_name") or "",
                    "avatar_url": author.get("avatar_url") or "",
                    "initial": author.get("initial") or "",
                },
            }
        )
    next_offset = start + len(registrations)
    return {
        "ok": True,
        "event": serialize_organization_event(event, actor),
        "registrations": registrations,
        "has_more": next_offset < total,
        "next_offset": next_offset,
        "total": total,
    }


def list_my_event_registrations_payload(
    viewer: AbstractBaseUser | None,
    *,
    offset: int = 0,
    limit: int | None = None,
) -> dict[str, Any]:
    if not _authenticated_user(viewer):
        raise OrganizationEventError("unauthorized", status=401)
    start, page_size = _page_args(offset, limit, MY_REGISTRATION_PAGE)
    queryset = (
        OrganizationEventRegistration.objects.filter(
            user=viewer,
            status=OrganizationEventRegistration.Status.REGISTERED,
            event__deleted_at__isnull=True,
        )
        .select_related("event", "event__organization")
        .order_by("event__starts_at", "pk")
    )
    visible = []
    for row in queryset:
        if can_view_organization_event(viewer, row.event):
            visible.append(row)
    total = len(visible)
    page = visible[start : start + page_size]
    events = [
        serialize_organization_event(
            row.event,
            viewer,
            viewer_status=row.status,
        )
        for row in page
    ]
    next_offset = start + len(events)
    return {
        "ok": True,
        "events": events,
        "has_more": next_offset < total,
        "next_offset": next_offset,
    }


def is_write_contention(exc: BaseException) -> bool:
    text = str(exc).lower()
    return "locked" in text or "deadlock" in text or isinstance(exc, OperationalError)


EVENT_SHARE_BODY = "イベントを共有しました"


def serialize_event_share(event: OrganizationEvent) -> dict[str, Any]:
    from .organization_event_timeline_services import public_event_card_status

    slug = event.organization.slug
    _status, status_label = public_event_card_status(event)
    return {
        "type": "org_event",
        "id": event.pk,
        "available": True,
        "content": {
            "event_id": event.pk,
            "organization_slug": slug,
            "title": event.title,
            "starts_at": _iso(event.starts_at),
            "ends_at": _iso(event.ends_at),
            "venue_name": event.venue_name,
            "status_label": status_label,
            "path": f"/organizations/{slug}/events/{event.pk}",
        },
    }


def share_organization_event_to_chat(
    *,
    event: OrganizationEvent,
    actor: AbstractBaseUser,
    chat_id: int,
    share_type: str = OrganizationChatShare.ShareType.EVENT,
    body: str = EVENT_SHARE_BODY,
) -> OrganizationChatShare:
    from .chat_message_services import create_chat_message
    from .organization_recruiting_chat_services import (
        _ensure_membership,
        assert_can_manage_recruiting_chat,
        get_organization_chat,
    )

    organization = event.organization
    _require_manage(actor, organization)
    if event.deleted_at is not None:
        raise OrganizationEventError("not_found", status=404)
    chat = get_organization_chat(organization, chat_id)
    if chat is None or not chat.is_active:
        raise OrganizationEventError("no_recruiting_chat", status=409)
    assert_can_manage_recruiting_chat(actor, chat)
    with transaction.atomic():
        existing = (
            OrganizationChatShare.objects.select_for_update()
            .filter(
                event=event,
                recruiting_chat=chat,
                share_type=share_type,
            )
            .select_related("message")
            .first()
        )
        if (
            existing is not None
            and existing.message_id
            and existing.message.deleted_at is None
            and not existing.message.is_hidden
        ):
            raise OrganizationEventError("already_shared", status=409)
        _ensure_membership(chat.room, actor)
        message = create_chat_message(chat.room, actor, body)
        if existing is not None:
            existing.message = message
            existing.save(update_fields=["message"])
            share = existing
        else:
            share = OrganizationChatShare.objects.create(
                event=event,
                recruiting_chat=chat,
                message=message,
                share_type=share_type,
            )
    return share


def event_share_extras_for_messages(
    messages: Iterable,
) -> dict[int, dict[str, Any]]:
    ids = [
        row.pk
        for row in messages
        if getattr(row, "pk", None)
        and row.deleted_at is None
        and not row.is_hidden
    ]
    if not ids:
        return {}
    extras: dict[int, dict[str, Any]] = {}
    shares = OrganizationChatShare.objects.filter(
        message_id__in=ids,
        share_type=OrganizationChatShare.ShareType.EVENT,
    ).select_related("event", "event__organization")
    for share in shares:
        extras[share.message_id] = {
            "message_kind": "share",
            "share": serialize_event_share(share.event),
        }
    return extras


def duplicate_organization_event(
    *,
    event: OrganizationEvent,
    actor: AbstractBaseUser,
    payload: dict[str, Any] | None = None,
) -> OrganizationEvent:
    """日時などを差し替えて下書き複製する。抽選・申込はコピーしない。"""
    organization = event.organization
    _require_manage(actor, organization)
    if event.deleted_at is not None:
        raise OrganizationEventError("not_found", status=404)
    data = {
        "title": event.title,
        "description": event.description,
        "starts_at": event.starts_at.isoformat(),
        "ends_at": event.ends_at.isoformat(),
        "venue_name": event.venue_name,
        "venue_address": event.venue_address,
        "registration_deadline": (
            event.registration_deadline.isoformat()
            if event.registration_deadline
            else None
        ),
        "registration_open": event.signup_mode
        != OrganizationEvent.SignupMode.ANNOUNCEMENT,
        "signup_mode": event.signup_mode
        or OrganizationEvent.SignupMode.REGISTRATION,
    }
    if payload:
        data.update(payload)
    return create_organization_event(
        organization=organization, actor=actor, payload=data
    )
