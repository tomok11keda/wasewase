"""Cursor pagination for chat history (DM / Group / Course Talk / Trade).

Initial open and ``before=`` history loads return the newest page only.
Polling continues to use ``after=<pk>`` for newer messages.
"""

from __future__ import annotations

from typing import Any

from django.db.models import QuerySet

# Latest N messages on room open / history page. Balances first paint vs scroll.
CHAT_HISTORY_PAGE_SIZE = 50
# Safety cap when polling with after= (normally small deltas).
CHAT_POLL_MAX_MESSAGES = 200


def parse_message_pk(raw: Any) -> int | None:
    if raw is None or raw == "":
        return None
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def slice_chat_history(
    qs: QuerySet,
    *,
    before: int | None = None,
    limit: int = CHAT_HISTORY_PAGE_SIZE,
) -> tuple[list, bool, int | None]:
    """Return (messages oldest→newest, has_more, next_before).

    ``next_before`` is the oldest pk in the page when more history exists.
    """
    page_qs = qs
    if before is not None:
        page_qs = page_qs.filter(pk__lt=before)

    # Newest-first window, then reverse for display order.
    window = list(page_qs.order_by("-pk")[: limit + 1])
    has_more = len(window) > limit
    page = window[:limit]
    page.reverse()
    next_before = page[0].pk if has_more and page else None
    return page, has_more, next_before


def slice_chat_poll(
    qs: QuerySet,
    *,
    after: int,
    limit: int = CHAT_POLL_MAX_MESSAGES,
) -> list:
    """Newer-than-cursor messages in ascending order (existing poll contract)."""
    return list(qs.filter(pk__gt=after).order_by("pk")[:limit])


def history_meta(has_more: bool, next_before: int | None) -> dict[str, Any]:
    return {
        "has_more": bool(has_more),
        "next_before": next_before,
    }
