"""団体チャット内部の出欠イベント。公開イベント・抽選 API とは独立。"""

from __future__ import annotations

from datetime import datetime, timezone as dt_timezone
from typing import Any

from django.contrib.auth.models import AbstractBaseUser
from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from .models import (
    ChatRoomMembership,
    Organization,
    OrganizationChatEvent,
    OrganizationChatEventRsvp,
    OrganizationRecruitingChat,
    User,
)
from .organization_event_services import TOKYO, OrganizationEventError, _iso
from .organization_recruiting_chat_services import (
    OrganizationRecruitingChatError,
    can_access_recruiting_room,
    get_organization_chat,
    is_recruiting_participant,
)
from .organization_services import can_manage_organization
from .timeline_api_services import serialize_author

TITLE_MAX = 120
DESCRIPTION_MAX = 2000
VENUE_NAME_MAX = 120
CHAT_EVENT_SHARE_BODY = "チャット内イベントを作成しました"
RSVP_ANSWERS = {
    OrganizationChatEventRsvp.Answer.GOING,
    OrganizationChatEventRsvp.Answer.NOT_GOING,
    OrganizationChatEventRsvp.Answer.MAYBE,
}


class OrganizationChatEventError(OrganizationEventError):
    pass


def _now() -> datetime:
    return timezone.now()


def _authenticated_user(user: AbstractBaseUser | None) -> bool:
    return bool(
        user is not None
        and getattr(user, "pk", None)
        and getattr(user, "is_authenticated", False)
        and getattr(user, "is_active", True)
    )


def _parse_datetime(value: Any, *, field: str, required: bool = True) -> datetime | None:
    if value is None or (isinstance(value, str) and not str(value).strip()):
        if required:
            raise OrganizationChatEventError(
                "invalid_payload",
                status=400,
                errors={field: "日時を入力してください。"},
            )
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        dt = parse_datetime(str(value).strip())
        if dt is None:
            raise OrganizationChatEventError(
                "invalid_payload",
                status=400,
                errors={field: "日時の形式が正しくありません。"},
            )
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, TOKYO)
    return dt.astimezone(dt_timezone.utc)


def _clean_text(value: Any, *, field: str, max_length: int, required: bool) -> str:
    text = "" if value is None else str(value).replace("\x00", "").strip()
    if required and not text:
        raise OrganizationChatEventError(
            "invalid_payload",
            status=400,
            errors={field: "入力してください。"},
        )
    if len(text) > max_length:
        raise OrganizationChatEventError(
            "invalid_payload",
            status=400,
            errors={field: f"{max_length}文字以内で入力してください。"},
        )
    return text


def _resolve_chat(
    organization: Organization, chat_id: int | None
) -> OrganizationRecruitingChat:
    if not chat_id:
        raise OrganizationChatEventError("chat_id_required", status=400)
    chat = get_organization_chat(organization, chat_id)
    if chat is None:
        raise OrganizationChatEventError("not_found", status=404)
    return chat


def _require_participant(chat: OrganizationRecruitingChat, user: AbstractBaseUser) -> None:
    if not _authenticated_user(user):
        raise OrganizationChatEventError("unauthorized", status=401)
    if not can_access_recruiting_room(chat.room, user):
        raise OrganizationChatEventError("not_found", status=404)


def _require_manage_as_member(
    chat: OrganizationRecruitingChat, user: AbstractBaseUser
) -> None:
    _require_participant(chat, user)
    if not can_manage_organization(user, chat.organization):
        raise OrganizationChatEventError("forbidden", status=403)


def _chat_is_writable(chat: OrganizationRecruitingChat) -> bool:
    return bool(chat.is_active)


def _member_ids(chat: OrganizationRecruitingChat) -> list[int]:
    return list(
        ChatRoomMembership.objects.filter(room_id=chat.room_id).values_list(
            "user_id", flat=True
        )
    )


def _counts_for_event(
    event: OrganizationChatEvent, member_ids: list[int]
) -> dict[str, int]:
    member_set = set(member_ids)
    going = 0
    not_going = 0
    maybe = 0
    answered_ids: set[int] = set()
    for user_id, answer in OrganizationChatEventRsvp.objects.filter(
        event_id=event.pk, user_id__in=member_set
    ).values_list("user_id", "answer"):
        answered_ids.add(user_id)
        if answer == OrganizationChatEventRsvp.Answer.GOING:
            going += 1
        elif answer == OrganizationChatEventRsvp.Answer.NOT_GOING:
            not_going += 1
        elif answer == OrganizationChatEventRsvp.Answer.MAYBE:
            maybe += 1
    unanswered = max(0, len(member_set) - len(answered_ids))
    return {
        "going_count": going,
        "not_going_count": not_going,
        "maybe_count": maybe,
        "unanswered_count": unanswered,
        "member_count": len(member_set),
    }


def chat_event_path(event: OrganizationChatEvent) -> str:
    slug = event.organization.slug
    return (
        f"/organizations/{slug}/recruiting-chat/events/{event.pk}"
        f"?chat={event.recruiting_chat_id}"
    )


def serialize_chat_event_share(event: OrganizationChatEvent) -> dict[str, Any]:
    cancelled = event.status == OrganizationChatEvent.Status.CANCELLED
    return {
        "type": "org_chat_event",
        "id": event.pk,
        "available": True,
        "content": {
            "event_id": event.pk,
            "organization_slug": event.organization.slug,
            "chat_id": event.recruiting_chat_id,
            "title": event.title,
            "starts_at": _iso(event.starts_at),
            "ends_at": _iso(event.ends_at),
            "venue_name": event.venue_name or "",
            "status": event.status,
            "status_label": "中止" if cancelled else "チャット内",
            "path": chat_event_path(event),
        },
    }


def chat_event_share_extras_for_messages(messages) -> dict[int, dict[str, Any]]:
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
    events = OrganizationChatEvent.objects.filter(
        announcement_message_id__in=ids
    ).select_related("organization", "recruiting_chat")
    for event in events:
        extras[event.announcement_message_id] = {
            "message_kind": "share",
            "share": serialize_chat_event_share(event),
        }
    return extras


def serialize_organization_chat_event(
    event: OrganizationChatEvent,
    viewer: AbstractBaseUser | None,
    *,
    include_respondents: bool = False,
    member_ids: list[int] | None = None,
    viewer_answer: str | None = None,
) -> dict[str, Any]:
    chat = event.recruiting_chat
    members = member_ids if member_ids is not None else _member_ids(chat)
    counts = _counts_for_event(event, members)
    manage = bool(
        _authenticated_user(viewer)
        and is_recruiting_participant(chat.room, viewer)
        and can_manage_organization(viewer, event.organization)
    )
    if viewer_answer is None and _authenticated_user(viewer):
        row = (
            OrganizationChatEventRsvp.objects.filter(
                event_id=event.pk, user_id=viewer.pk
            )
            .values_list("answer", flat=True)
            .first()
        )
        viewer_answer = row
    now = _now()
    deadline_passed = bool(
        event.rsvp_deadline is not None and event.rsvp_deadline <= now
    )
    writable = _chat_is_writable(chat)
    cancelled = event.status == OrganizationChatEvent.Status.CANCELLED
    can_rsvp = bool(
        _authenticated_user(viewer)
        and writable
        and not cancelled
        and not deadline_passed
        and is_recruiting_participant(chat.room, viewer)
    )
    payload: dict[str, Any] = {
        "id": event.pk,
        "organization_id": event.organization_id,
        "organization_slug": event.organization.slug,
        "chat_id": event.recruiting_chat_id,
        "title": event.title,
        "description": event.description or "",
        "starts_at": _iso(event.starts_at),
        "ends_at": _iso(event.ends_at),
        "venue_name": event.venue_name or "",
        "rsvp_deadline": _iso(event.rsvp_deadline),
        "status": event.status,
        "is_cancelled": cancelled,
        "is_ended": bool(event.ends_at and event.ends_at <= now)
        or (event.ends_at is None and event.starts_at <= now),
        "is_deadline_passed": deadline_passed,
        "viewer_answer": viewer_answer,
        "can_rsvp": can_rsvp,
        "can_manage": manage,
        "chat_is_active": writable,
        "path": chat_event_path(event),
        "created_at": _iso(event.created_at),
        "updated_at": _iso(event.updated_at),
        **counts,
    }
    if include_respondents and manage:
        payload.update(_respondent_lists(event, members))
    return payload


def _respondent_lists(
    event: OrganizationChatEvent, member_ids: list[int]
) -> dict[str, Any]:
    member_set = set(member_ids)
    rsvps = list(
        OrganizationChatEventRsvp.objects.filter(
            event_id=event.pk, user_id__in=member_set
        ).select_related("user", "user__profile")
    )
    answered = {row.user_id: row for row in rsvps}
    buckets: dict[str, list[dict[str, Any]]] = {
        "going": [],
        "not_going": [],
        "maybe": [],
        "unanswered": [],
    }
    users = {
        user.pk: user
        for user in User.objects.filter(pk__in=member_ids).select_related("profile")
    }
    for user_id in member_ids:
        user = users.get(user_id)
        author = serialize_author(user) or {
            "id": user_id,
            "username": "",
            "display_name": "ユーザー",
            "avatar_url": "",
            "initial": "?",
        }
        row = answered.get(user_id)
        item = {"user": author, "answer": row.answer if row else None}
        if row is None:
            buckets["unanswered"].append(item)
        elif row.answer in buckets:
            buckets[row.answer].append(item)
    return {
        "respondents": buckets,
    }


def list_organization_chat_events(
    *,
    organization: Organization,
    chat_id: int,
    viewer: AbstractBaseUser,
) -> dict[str, Any]:
    chat = _resolve_chat(organization, chat_id)
    _require_participant(chat, viewer)
    events = list(
        OrganizationChatEvent.objects.select_related(
            "organization", "recruiting_chat", "recruiting_chat__room"
        )
        .filter(recruiting_chat=chat)
        .order_by("starts_at", "pk")[:80]
    )
    member_ids = _member_ids(chat)
    viewer_answers = {
        event_id: answer
        for event_id, answer in OrganizationChatEventRsvp.objects.filter(
            event_id__in=[row.pk for row in events], user_id=viewer.pk
        ).values_list("event_id", "answer")
    }
    manage = can_manage_organization(viewer, organization) and is_recruiting_participant(
        chat.room, viewer
    )
    return {
        "ok": True,
        "chat_id": chat.pk,
        "chat_is_active": chat.is_active,
        "can_manage": manage,
        "events": [
            serialize_organization_chat_event(
                row,
                viewer,
                member_ids=member_ids,
                viewer_answer=viewer_answers.get(row.pk),
            )
            for row in events
        ],
    }


def get_organization_chat_event(
    *,
    organization: Organization,
    chat_id: int,
    event_id: int,
    viewer: AbstractBaseUser,
) -> OrganizationChatEvent:
    chat = _resolve_chat(organization, chat_id)
    _require_participant(chat, viewer)
    event = (
        OrganizationChatEvent.objects.select_related(
            "organization", "recruiting_chat", "recruiting_chat__room"
        )
        .filter(pk=event_id, recruiting_chat=chat, organization=organization)
        .first()
    )
    if event is None:
        raise OrganizationChatEventError("not_found", status=404)
    return event


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
            required=False,
        )
    if not partial or "starts_at" in payload:
        data["starts_at"] = _parse_datetime(payload.get("starts_at"), field="starts_at")
    if not partial or "ends_at" in payload:
        data["ends_at"] = _parse_datetime(
            payload.get("ends_at"), field="ends_at", required=False
        )
    if not partial or "rsvp_deadline" in payload:
        data["rsvp_deadline"] = _parse_datetime(
            payload.get("rsvp_deadline"), field="rsvp_deadline", required=False
        )
    return data


def _validate_schedule(fields: dict[str, Any], current: OrganizationChatEvent | None) -> None:
    starts_at = fields.get("starts_at", current.starts_at if current else None)
    ends_at = fields.get("ends_at", current.ends_at if current else None)
    deadline = fields.get(
        "rsvp_deadline", current.rsvp_deadline if current else None
    )
    errors: dict[str, str] = {}
    if starts_at is None:
        errors["starts_at"] = "開始日時を入力してください。"
    if ends_at is not None and starts_at is not None and ends_at <= starts_at:
        errors["ends_at"] = "終了日時は開始日時より後にしてください。"
    if deadline is not None and starts_at is not None and deadline > starts_at:
        errors["rsvp_deadline"] = "回答期限は開始日時以前にしてください。"
    if errors:
        raise OrganizationChatEventError("invalid_payload", status=400, errors=errors)


def create_organization_chat_event(
    *,
    organization: Organization,
    actor: AbstractBaseUser,
    chat_id: int,
    payload: dict[str, Any],
) -> OrganizationChatEvent:
    chat = _resolve_chat(organization, chat_id)
    _require_manage_as_member(chat, actor)
    if not _chat_is_writable(chat):
        raise OrganizationChatEventError("inactive", status=403)
    fields = _fields_from_payload(payload, partial=False)
    _validate_schedule(fields, None)
    from .chat_message_services import create_chat_message

    with transaction.atomic():
        event = OrganizationChatEvent.objects.create(
            recruiting_chat=chat,
            organization=organization,
            created_by=actor,
            status=OrganizationChatEvent.Status.SCHEDULED,
            **fields,
        )
        try:
            message = create_chat_message(chat.room, actor, CHAT_EVENT_SHARE_BODY)
        except OrganizationRecruitingChatError as exc:
            raise OrganizationChatEventError(exc.code, status=exc.status) from exc
        except ValueError as exc:
            raise OrganizationChatEventError(str(exc) or "invalid_payload", status=400) from exc
        event.announcement_message = message
        event.save(update_fields=["announcement_message", "updated_at"])
    return (
        OrganizationChatEvent.objects.select_related(
            "organization", "recruiting_chat", "recruiting_chat__room"
        ).get(pk=event.pk)
    )


def update_organization_chat_event(
    *,
    event: OrganizationChatEvent,
    actor: AbstractBaseUser,
    payload: dict[str, Any],
) -> OrganizationChatEvent:
    chat = event.recruiting_chat
    _require_manage_as_member(chat, actor)
    if not _chat_is_writable(chat):
        raise OrganizationChatEventError("inactive", status=403)
    if event.status == OrganizationChatEvent.Status.CANCELLED:
        raise OrganizationChatEventError("cancelled", status=409)
    fields = _fields_from_payload(payload, partial=True)
    _validate_schedule(fields, event)
    for key, value in fields.items():
        setattr(event, key, value)
    event.save()
    return event


def cancel_organization_chat_event(
    *, event: OrganizationChatEvent, actor: AbstractBaseUser
) -> OrganizationChatEvent:
    chat = event.recruiting_chat
    _require_manage_as_member(chat, actor)
    if not _chat_is_writable(chat):
        raise OrganizationChatEventError("inactive", status=403)
    event.status = OrganizationChatEvent.Status.CANCELLED
    event.save(update_fields=["status", "updated_at"])
    return event


def rsvp_organization_chat_event(
    *,
    event: OrganizationChatEvent,
    user: AbstractBaseUser,
    answer: str,
) -> OrganizationChatEventRsvp:
    chat = event.recruiting_chat
    _require_participant(chat, user)
    if not _chat_is_writable(chat):
        raise OrganizationChatEventError("inactive", status=403)
    if event.status == OrganizationChatEvent.Status.CANCELLED:
        raise OrganizationChatEventError("cancelled", status=409)
    if event.rsvp_deadline is not None and event.rsvp_deadline <= _now():
        raise OrganizationChatEventError("deadline_passed", status=409)
    raw = str(answer or "").strip().lower()
    if raw not in RSVP_ANSWERS:
        raise OrganizationChatEventError(
            "invalid_payload",
            status=400,
            errors={"answer": "参加・不参加・未定のいずれかを選んでください。"},
        )
    try:
        row, _created = OrganizationChatEventRsvp.objects.update_or_create(
            event=event,
            user=user,
            defaults={"answer": raw},
        )
    except IntegrityError as exc:
        raise OrganizationChatEventError("busy", status=409) from exc
    return row
