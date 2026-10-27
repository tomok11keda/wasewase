"""Optional organization-event lottery. Events themselves have no lottery mode."""

from __future__ import annotations

import logging
import secrets
from typing import Any, Iterable

from django.contrib.auth.models import AbstractBaseUser
from django.db import IntegrityError, transaction
from django.utils import timezone

from .models import (
    ChatMessage,
    Organization,
    OrganizationChatShare,
    OrganizationEvent,
    OrganizationEventLottery,
    OrganizationEventLotteryEntry,
    OrganizationEventRegistration,
)
from .notification_services import create_notification
from .organization_event_services import (
    OrganizationEventError,
    _authenticated_user,
    _iso,
    _lock_event,
    _require_manage,
    _run_after_commit,
    can_view_organization_event,
    get_event_for_organization,
    organization_allows_event_access,
    serialize_organization_event,
)
from .organization_recruiting_chat_services import (
    get_active_recruiting_chat,
    get_organization_chat,
    is_recruiting_participant,
    list_active_recruiting_chats,
)
from .organization_services import can_manage_organization
from .spa_canonical import organization_event_lottery_url
from .timeline_api_services import serialize_author

logger = logging.getLogger(__name__)

EXCLUSION_NOTE_MAX = 100
LOTTERY_SHARE_BODY = "抽選結果を共有しました"

PUSH_KIND_ORG_EVENT_LOTTERY_SELECTED = "org_event_lottery_selected"
PUSH_KIND_ORG_EVENT_LOTTERY_NOT_SELECTED = "org_event_lottery_not_selected"
PUSH_KIND_ORG_EVENT_LOTTERY_EXCLUDED = "org_event_lottery_excluded"


def can_view_event_lottery_lists(
    viewer: AbstractBaseUser | None, organization: Organization
) -> bool:
    if not _authenticated_user(viewer):
        return False
    if not organization_allows_event_access(organization):
        return can_manage_organization(viewer, organization)
    if can_manage_organization(viewer, organization):
        return True
    for chat in list_active_recruiting_chats(organization):
        if is_recruiting_participant(chat.room, viewer):
            return True
    return False


def lottery_has_live_share(
    lottery: OrganizationEventLottery | None,
    *,
    chat_id: int | None = None,
) -> bool:
    """現存する（未削除・非hidden）共有メッセージがあるか。"""
    if lottery is None:
        return False
    shares = OrganizationChatShare.objects.filter(
        event_id=lottery.event_id,
        share_type=OrganizationChatShare.ShareType.LOTTERY,
    ).select_related("message")
    if chat_id:
        shares = shares.filter(recruiting_chat_id=chat_id)
    for share in shares:
        message = share.message
        if message and message.deleted_at is None and not message.is_hidden:
            return True
    if not lottery.shared_message_id:
        return False
    message = getattr(lottery, "shared_message", None)
    if message is None or getattr(message, "pk", None) != lottery.shared_message_id:
        message = ChatMessage.objects.filter(pk=lottery.shared_message_id).only(
            "pk", "deleted_at", "is_hidden"
        ).first()
    if message is None:
        return False
    return message.deleted_at is None and not message.is_hidden


def lottery_for_event(event: OrganizationEvent) -> OrganizationEventLottery | None:
    return (
        OrganizationEventLottery.objects.filter(event_id=event.pk)
        .select_related("event", "event__organization", "shared_message")
        .first()
    )


def lotteries_by_event_ids(
    event_ids: Iterable[int],
) -> dict[int, OrganizationEventLottery]:
    ids = [int(pk) for pk in event_ids]
    if not ids:
        return {}
    return {
        row.event_id: row
        for row in OrganizationEventLottery.objects.filter(event_id__in=ids).select_related(
            "shared_message"
        )
    }


def viewer_lottery_results_by_event(
    event_ids: Iterable[int], viewer: AbstractBaseUser | None
) -> dict[int, str]:
    if not _authenticated_user(viewer):
        return {}
    ids = [int(pk) for pk in event_ids]
    if not ids:
        return {}
    return {
        event_id: result
        for event_id, result in OrganizationEventLotteryEntry.objects.filter(
            lottery__event_id__in=ids, user_id=viewer.pk
        ).values_list("lottery__event_id", "result")
    }


def _parse_winner_count(value: Any) -> int:
    if isinstance(value, bool) or value is None or value == "":
        raise OrganizationEventError(
            "invalid_payload",
            status=400,
            errors={"winner_count": "当選人数を入力してください。"},
        )
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        raise OrganizationEventError(
            "invalid_payload",
            status=400,
            errors={"winner_count": "当選人数は0以上の整数で指定してください。"},
        ) from None
    if parsed < 0:
        raise OrganizationEventError(
            "invalid_payload",
            status=400,
            errors={"winner_count": "当選人数は0以上の整数で指定してください。"},
        )
    return parsed


def _clean_exclusion_note(value: Any) -> str:
    text = "" if value is None else str(value).replace("\x00", "").strip()
    if len(text) > EXCLUSION_NOTE_MAX:
        raise OrganizationEventError(
            "invalid_payload",
            status=400,
            errors={
                "exclusion_note": f"備考は{EXCLUSION_NOTE_MAX}文字以内で入力してください。"
            },
        )
    return text


def _parse_applicant_ids(value: Any) -> set[int]:
    if not isinstance(value, list):
        raise OrganizationEventError(
            "invalid_payload",
            status=400,
            errors={"applicant_ids": "申込者一覧を再確認してください。"},
        )
    ids: set[int] = set()
    for raw in value:
        try:
            user_id = int(raw)
        except (TypeError, ValueError):
            raise OrganizationEventError(
                "invalid_payload",
                status=400,
                errors={"applicant_ids": "申込者一覧を再確認してください。"},
            ) from None
        if user_id <= 0:
            raise OrganizationEventError(
                "invalid_payload",
                status=400,
                errors={"applicant_ids": "申込者一覧を再確認してください。"},
            )
        ids.add(user_id)
    return ids


def _parse_excluded(value: Any) -> dict[int, str]:
    if value is None:
        return {}
    if not isinstance(value, list):
        raise OrganizationEventError(
            "invalid_payload",
            status=400,
            errors={"excluded": "除外者の形式が正しくありません。"},
        )
    excluded: dict[int, str] = {}
    for item in value:
        if isinstance(item, dict):
            raw_id = item.get("user_id", item.get("id"))
            note = _clean_exclusion_note(item.get("note", item.get("exclusion_note")))
        else:
            raw_id = item
            note = ""
        try:
            user_id = int(raw_id)
        except (TypeError, ValueError):
            raise OrganizationEventError(
                "invalid_payload",
                status=400,
                errors={"excluded": "除外者の指定が正しくありません。"},
            ) from None
        if user_id <= 0:
            raise OrganizationEventError(
                "invalid_payload",
                status=400,
                errors={"excluded": "除外者の指定が正しくありません。"},
            )
        excluded[user_id] = note
    return excluded


def _entry_user_payload(entry: OrganizationEventLotteryEntry) -> dict[str, Any]:
    live = serialize_author(entry.user) if entry.user_id else None
    if live:
        return {
            "id": live.get("id"),
            "username": live.get("username") or "",
            "display_name": live.get("display_name") or entry.display_name_snapshot,
            "avatar_url": live.get("avatar_url") or "",
            "initial": live.get("initial") or entry.initial_snapshot or "?",
        }
    return {
        "id": entry.user_id,
        "username": entry.username_snapshot or "",
        "display_name": entry.display_name_snapshot or "ユーザー",
        "avatar_url": entry.avatar_url_snapshot or "",
        "initial": entry.initial_snapshot or "?",
    }


def _serialize_entry(entry: OrganizationEventLotteryEntry) -> dict[str, Any]:
    payload = {
        "id": entry.pk,
        "result": entry.result,
        "user": _entry_user_payload(entry),
    }
    if entry.result == OrganizationEventLotteryEntry.Result.EXCLUDED:
        payload["exclusion_note"] = entry.exclusion_note or ""
    return payload


def serialize_lottery_share(lottery: OrganizationEventLottery) -> dict[str, Any]:
    event = lottery.event
    not_selected = max(0, int(lottery.eligible_count) - int(lottery.winner_count))
    slug = event.organization.slug
    path = f"/organizations/{slug}/events/{event.pk}/lottery"
    return {
        "type": "org_event_lottery",
        "id": lottery.pk,
        "available": True,
        "content": {
            "event_id": event.pk,
            "organization_slug": slug,
            "title": event.title,
            "applicant_count": lottery.applicant_count,
            "eligible_count": lottery.eligible_count,
            "winner_count": lottery.winner_count,
            "not_selected_count": not_selected,
            "excluded_count": lottery.excluded_count,
            "path": path,
        },
    }


def serialize_organization_event_lottery(
    lottery: OrganizationEventLottery,
    viewer: AbstractBaseUser | None,
    *,
    include_entries: bool = True,
) -> dict[str, Any]:
    event = lottery.event
    organization = event.organization
    manage = can_manage_organization(viewer, organization)
    can_view = can_view_event_lottery_lists(viewer, organization)
    not_selected = max(0, int(lottery.eligible_count) - int(lottery.winner_count))
    shared = lottery_has_live_share(lottery)
    chats = list_active_recruiting_chats(organization)
    payload: dict[str, Any] = {
        "id": lottery.pk,
        "event_id": event.pk,
        "status": lottery.status,
        "executed_at": _iso(lottery.executed_at),
        "applicant_count": lottery.applicant_count,
        "eligible_count": lottery.eligible_count,
        "excluded_count": lottery.excluded_count,
        "winner_count": lottery.winner_count,
        "not_selected_count": not_selected,
        "shared": shared,
        "shared_at": _iso(lottery.shared_at),
        "can_share": bool(
            manage
            and any(
                not lottery_has_live_share(lottery, chat_id=chat.pk) for chat in chats
            )
        ),
        "can_manage": manage,
        "can_view": can_view,
        "lists_visible": bool(can_view and include_entries),
        "viewer_entry": None,
    }
    viewer_entry = None
    if _authenticated_user(viewer):
        viewer_entry = (
            lottery.entries.select_related("user", "user__profile")
            .filter(user_id=viewer.pk)
            .first()
        )
        if viewer_entry is not None:
            payload["viewer_entry"] = _serialize_entry(viewer_entry)
    if include_entries and can_view:
        grouped = {"selected": [], "not_selected": [], "excluded": []}
        entries = lottery.entries.select_related("user", "user__profile").order_by(
            "pk"
        )
        for entry in entries:
            grouped[entry.result].append(_serialize_entry(entry))
        payload["selected"] = grouped["selected"]
        payload["not_selected"] = grouped["not_selected"]
        payload["excluded"] = grouped["excluded"]
    return payload


def get_organization_event_lottery_payload(
    organization: Organization,
    event_id: int,
    viewer: AbstractBaseUser | None,
) -> dict[str, Any]:
    if not _authenticated_user(viewer):
        raise OrganizationEventError("unauthorized", status=401)
    event = get_event_for_organization(organization, event_id)
    if event is None or not can_view_organization_event(viewer, event):
        raise OrganizationEventError("not_found", status=404)
    lottery = lottery_for_event(event)
    if lottery is None:
        raise OrganizationEventError("no_lottery", status=404)
    can_lists = can_view_event_lottery_lists(viewer, organization)
    has_own_entry = lottery.entries.filter(user_id=viewer.pk).exists()
    if not can_lists and not has_own_entry:
        raise OrganizationEventError("forbidden", status=403)
    return {
        "ok": True,
        "event": serialize_organization_event(
            event, viewer, lottery=lottery, lottery_loaded=True
        ),
        "lottery": serialize_organization_event_lottery(
            lottery, viewer, include_entries=can_lists
        ),
    }


def _snapshot_user(user: AbstractBaseUser | None) -> dict[str, str]:
    author = serialize_author(user) or {}
    return {
        "display_name_snapshot": str(author.get("display_name") or "ユーザー")[:120],
        "username_snapshot": str(author.get("username") or "")[:150],
        "avatar_url_snapshot": str(author.get("avatar_url") or "")[:500],
        "initial_snapshot": str(author.get("initial") or "?")[:8],
    }


def _lottery_link(event: OrganizationEvent) -> str:
    return organization_event_lottery_url(event.organization.slug, event.pk)


def _notify_lottery_results(
    event: OrganizationEvent,
    selected_ids: list[int],
    not_selected_ids: list[int],
    excluded_ids: list[int],
) -> None:
    org_name = event.organization.name
    title = event.title
    link = _lottery_link(event)
    for user_id in selected_ids:
        create_notification(
            recipient_id=user_id,
            message=f"「{org_name}」のイベント「{title}」の抽選に当選しました。",
            link=link,
            actor=None,
            push_kind=PUSH_KIND_ORG_EVENT_LOTTERY_SELECTED,
            push_body="イベントの抽選に当選しました",
        )
    for user_id in not_selected_ids:
        create_notification(
            recipient_id=user_id,
            message=f"「{org_name}」のイベント「{title}」の抽選結果が出ました。",
            link=link,
            actor=None,
            push_kind=PUSH_KIND_ORG_EVENT_LOTTERY_NOT_SELECTED,
            push_body="イベントの抽選結果が出ました",
        )
    for user_id in excluded_ids:
        create_notification(
            recipient_id=user_id,
            message=(
                f"「{org_name}」のイベント「{title}」の抽選対象外になりました。"
            ),
            link=link,
            actor=None,
            push_kind=PUSH_KIND_ORG_EVENT_LOTTERY_EXCLUDED,
            push_body="イベントの抽選対象外になりました",
        )


def run_organization_event_lottery(
    *,
    event: OrganizationEvent,
    actor: AbstractBaseUser,
    payload: dict[str, Any],
) -> OrganizationEventLottery:
    organization = event.organization
    _require_manage(actor, organization)
    winner_count = _parse_winner_count(payload.get("winner_count"))
    excluded_notes = _parse_excluded(payload.get("excluded"))
    expected_applicant_ids = _parse_applicant_ids(payload.get("applicant_ids"))

    with transaction.atomic():
        locked = _lock_event(event.pk)
        _require_manage(actor, locked.organization)
        if locked.deleted_at is not None:
            raise OrganizationEventError("not_found", status=404)
        if locked.status == OrganizationEvent.Status.CANCELLED:
            raise OrganizationEventError("cancelled", status=409)
        if locked.status != OrganizationEvent.Status.PUBLISHED:
            raise OrganizationEventError("not_published", status=409)
        if OrganizationEventLottery.objects.filter(event_id=locked.pk).exists():
            raise OrganizationEventError("already_drawn", status=409)

        locked.registration_open = False
        locked.save(update_fields=["registration_open", "updated_at"])

        registrations = list(
            OrganizationEventRegistration.objects.select_for_update()
            .select_related("user", "user__profile")
            .filter(
                event_id=locked.pk,
                status=OrganizationEventRegistration.Status.REGISTERED,
            )
            .order_by("pk")
        )
        registered_ids = [row.user_id for row in registrations]
        registered_set = set(registered_ids)
        if expected_applicant_ids != registered_set:
            raise OrganizationEventError(
                "registrants_changed",
                status=409,
                applicant_count=len(registered_ids),
            )
        unknown = [uid for uid in excluded_notes if uid not in registered_set]
        if unknown:
            raise OrganizationEventError("invalid_excluded", status=400)

        eligible_ids = [uid for uid in registered_ids if uid not in excluded_notes]
        if not eligible_ids:
            raise OrganizationEventError(
                "no_eligible",
                status=400,
                errors={"eligible": "抽選対象者を1人以上選択してください。"},
            )
        if winner_count > len(eligible_ids):
            raise OrganizationEventError(
                "winner_count_exceeds_eligible",
                status=400,
                errors={
                    "winner_count": "当選人数は抽選対象者数以下にしてください。",
                },
                eligible_count=len(eligible_ids),
            )

        rng = secrets.SystemRandom()
        winner_ids = set(rng.sample(eligible_ids, winner_count)) if winner_count else set()
        try:
            lottery = OrganizationEventLottery.objects.create(
                event=locked,
                executed_by=actor,
                status=OrganizationEventLottery.Status.COMPLETED,
                applicant_count=len(registered_ids),
                eligible_count=len(eligible_ids),
                excluded_count=len(excluded_notes),
                winner_count=winner_count,
            )
        except IntegrityError as exc:
            raise OrganizationEventError("already_drawn", status=409) from exc

        rows: list[OrganizationEventLotteryEntry] = []
        selected_ids: list[int] = []
        not_selected_ids: list[int] = []
        excluded_ids: list[int] = []
        for registration in registrations:
            user_id = registration.user_id
            snapshot = _snapshot_user(registration.user)
            if user_id in excluded_notes:
                result = OrganizationEventLotteryEntry.Result.EXCLUDED
                note = excluded_notes[user_id]
                excluded_ids.append(user_id)
            elif user_id in winner_ids:
                result = OrganizationEventLotteryEntry.Result.SELECTED
                note = ""
                selected_ids.append(user_id)
            else:
                result = OrganizationEventLotteryEntry.Result.NOT_SELECTED
                note = ""
                not_selected_ids.append(user_id)
            rows.append(
                OrganizationEventLotteryEntry(
                    lottery=lottery,
                    user=registration.user,
                    result=result,
                    exclusion_note=note,
                    **snapshot,
                )
            )
        OrganizationEventLotteryEntry.objects.bulk_create(rows)
        lottery_id = lottery.pk
        event_id = locked.pk

    _run_after_commit(
        lambda: _notify_lottery_results(
            OrganizationEvent.objects.select_related("organization").get(pk=event_id),
            selected_ids,
            not_selected_ids,
            excluded_ids,
        )
    )
    return (
        OrganizationEventLottery.objects.select_related(
            "event", "event__organization"
        ).get(pk=lottery_id)
    )


def share_organization_event_lottery(
    *,
    event: OrganizationEvent,
    actor: AbstractBaseUser,
    chat_id: int | None = None,
) -> OrganizationEventLottery:
    from .organization_event_services import share_organization_event_to_chat

    organization = event.organization
    _require_manage(actor, organization)
    resolved_chat_id = chat_id
    if not resolved_chat_id:
        chat = get_active_recruiting_chat(organization)
        if chat is None:
            raise OrganizationEventError("no_recruiting_chat", status=409)
        resolved_chat_id = chat.pk
    else:
        chat = get_organization_chat(organization, resolved_chat_id)
        if chat is None:
            raise OrganizationEventError("no_recruiting_chat", status=409)
    share = share_organization_event_to_chat(
        event=event,
        actor=actor,
        chat_id=resolved_chat_id,
        share_type=OrganizationChatShare.ShareType.LOTTERY,
        body=LOTTERY_SHARE_BODY,
    )
    lottery = OrganizationEventLottery.objects.filter(event_id=event.pk).first()
    if lottery is None:
        raise OrganizationEventError("no_lottery", status=404)
    lottery.shared_message = share.message
    lottery.shared_at = timezone.now()
    lottery.save(update_fields=["shared_message", "shared_at", "updated_at"])
    return (
        OrganizationEventLottery.objects.select_related(
            "event", "event__organization", "shared_message"
        ).get(pk=lottery.pk)
    )


def lottery_share_extras_for_messages(
    messages: Iterable[ChatMessage],
) -> dict[int, dict[str, Any]]:
    ids = [row.pk for row in messages]
    if not ids:
        return {}
    live_ids = [
        row.pk
        for row in messages
        if row.pk and row.deleted_at is None and not row.is_hidden
    ]
    extras: dict[int, dict[str, Any]] = {}
    if not live_ids:
        return extras
    lotteries = OrganizationEventLottery.objects.filter(
        shared_message_id__in=live_ids
    ).select_related("event", "event__organization")
    for lottery in lotteries:
        extras[lottery.shared_message_id] = {
            "message_kind": "share",
            "share": serialize_lottery_share(lottery),
        }
    shares = OrganizationChatShare.objects.filter(
        message_id__in=live_ids,
        share_type=OrganizationChatShare.ShareType.LOTTERY,
    ).select_related("event", "event__organization", "event__lottery")
    for share in shares:
        lottery = getattr(share.event, "lottery", None)
        if lottery is None:
            continue
        extras[share.message_id] = {
            "message_kind": "share",
            "share": serialize_lottery_share(lottery),
        }
    return extras
