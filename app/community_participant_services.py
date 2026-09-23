"""Thread-local anonymous participant numbers for Community."""

from __future__ import annotations

import time

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.db.models import Max
from django.db.utils import OperationalError

from .models import CommunityThread, CommunityThreadParticipant, CommunityThreadReply

User = get_user_model()

CREATOR_NUMBER = 1


def anonymous_label_for(number: int | None) -> str:
    if not number:
        return ""
    return f"ユーザー{int(number)}"


def participant_numbers(thread: CommunityThread) -> dict[int, int]:
    return {
        user_id: int(number)
        for user_id, number in CommunityThreadParticipant.objects.filter(
            thread_id=thread.pk, user_id__isnull=False
        ).values_list("user_id", "anonymous_number")
        if user_id
    }


def _create_row(thread: CommunityThread, user_id: int, number: int) -> int:
    CommunityThreadParticipant.objects.create(
        thread=thread,
        user_id=user_id,
        anonymous_number=number,
    )
    return number


def _ensure_creator_locked(thread: CommunityThread) -> None:
    if not thread.author_id:
        return
    if CommunityThreadParticipant.objects.filter(
        thread_id=thread.pk, user_id=thread.author_id
    ).exists():
        return
    try:
        _create_row(thread, thread.author_id, CREATOR_NUMBER)
    except IntegrityError:
        return


def get_or_assign_participant(*, thread: CommunityThread, user) -> int:
    """Return a stable thread-local number for user. Never renumbers others."""
    if user is None or not getattr(user, "pk", None):
        raise ValueError("user required")
    existing = (
        CommunityThreadParticipant.objects.filter(
            thread_id=thread.pk, user_id=user.pk
        )
        .values_list("anonymous_number", flat=True)
        .first()
    )
    if existing:
        return int(existing)

    last_error: Exception | None = None
    for _ in range(8):
        try:
            with transaction.atomic():
                locked = CommunityThread.objects.select_for_update().get(
                    pk=thread.pk
                )
                again = (
                    CommunityThreadParticipant.objects.filter(
                        thread_id=locked.pk, user_id=user.pk
                    )
                    .values_list("anonymous_number", flat=True)
                    .first()
                )
                if again:
                    return int(again)
                _ensure_creator_locked(locked)
                again = (
                    CommunityThreadParticipant.objects.filter(
                        thread_id=locked.pk, user_id=user.pk
                    )
                    .values_list("anonymous_number", flat=True)
                    .first()
                )
                if again:
                    return int(again)
                max_n = (
                    CommunityThreadParticipant.objects.filter(
                        thread_id=locked.pk
                    ).aggregate(m=Max("anonymous_number"))["m"]
                    or 0
                )
                number = (
                    CREATOR_NUMBER
                    if locked.author_id == user.pk
                    else int(max_n) + 1
                )
                return _create_row(locked, user.pk, number)
        except (IntegrityError, OperationalError) as exc:
            last_error = exc
            existing = (
                CommunityThreadParticipant.objects.filter(
                    thread_id=thread.pk, user_id=user.pk
                )
                .values_list("anonymous_number", flat=True)
                .first()
            )
            if existing:
                return int(existing)
            time.sleep(0.02 * (_ + 1))
            continue
    raise RuntimeError("community_participant_assign_failed") from last_error


def ensure_participants_for_thread(thread: CommunityThread) -> dict[int, int]:
    """Idempotent backfill: creator=1, then first-seen reply authors by created_at, pk."""
    numbers = participant_numbers(thread)
    reply_author_ids = list(
        CommunityThreadReply.objects.filter(thread_id=thread.pk)
        .order_by("created_at", "pk")
        .values_list("author_id", flat=True)
    )
    needed = {aid for aid in reply_author_ids if aid}
    if thread.author_id:
        needed.add(thread.author_id)
    if needed <= set(numbers):
        return numbers

    with transaction.atomic():
        locked = CommunityThread.objects.select_for_update().get(pk=thread.pk)
        numbers = participant_numbers(locked)
        _ensure_creator_locked(locked)
        max_n = (
            CommunityThreadParticipant.objects.filter(thread_id=locked.pk).aggregate(
                m=Max("anonymous_number")
            )["m"]
            or 0
        )
        numbers = participant_numbers(locked)
        next_n = int(max_n) + 1
        for author_id in reply_author_ids:
            if not author_id or author_id in numbers:
                continue
            if not User.objects.filter(pk=author_id).exists():
                continue
            try:
                _create_row(locked, author_id, next_n)
                numbers[author_id] = next_n
                next_n += 1
            except IntegrityError:
                numbers = participant_numbers(locked)
                if author_id in numbers:
                    next_n = max(numbers.values()) + 1
                    continue
                next_n = max(numbers.values(), default=0) + 1
                try:
                    _create_row(locked, author_id, next_n)
                    numbers[author_id] = next_n
                    next_n += 1
                except IntegrityError:
                    numbers = participant_numbers(locked)
                    next_n = max(numbers.values(), default=0) + 1
    return participant_numbers(thread)


def assign_creator_participant(thread: CommunityThread, user) -> int:
    return get_or_assign_participant(thread=thread, user=user)
