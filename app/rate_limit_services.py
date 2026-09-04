"""Shared write-path rate limits (LocMem/Redis cache via check_rate_limit).

既存の course_services.check_rate_limit を再利用する。
キーは user 単位。scope を分けて相互干渉を避ける。
cache 障害時は fail-open（既存と同じ）。
"""

from __future__ import annotations

from django.contrib.auth.models import AbstractBaseUser

from .course_services import check_rate_limit

# User-facing copy (API message / classic flash / FE mapping)
RATE_LIMIT_USER_MESSAGE = (
    "短時間に操作が集中しています。少し待ってからもう一度お試しください。"
)

# --- scopes & budgets (β: normal use OK, bot bursts blocked) ---
# Timeline posts are infrequent; 20/hour matches course-create density.
TIMELINE_POST_SCOPE = "timeline_post"
TIMELINE_POST_LIMIT = 20
TIMELINE_POST_WINDOW = 3600

# Comments are chatty but not as bursty as DMs.
TIMELINE_COMMENT_SCOPE = "timeline_comment"
TIMELINE_COMMENT_LIMIT = 40
TIMELINE_COMMENT_WINDOW = 600  # 10 min

# Likes are expected in rapid succession while scrolling.
TIMELINE_LIKE_SCOPE = "timeline_like"
TIMELINE_LIKE_LIMIT = 120
TIMELINE_LIKE_WINDOW = 300  # 5 min

# DM / Group / Course Talk / Trade share one chat budget (typing bursts OK).
CHAT_MESSAGE_SCOPE = "chat_message"
CHAT_MESSAGE_LIMIT = 60
CHAT_MESSAGE_WINDOW = 60

# Reports should be rare; block report spam without blocking chat.
REPORT_SCOPE = "report"
REPORT_LIMIT = 10
REPORT_WINDOW = 3600


def allow_user_rate_limit(
    user: AbstractBaseUser | None,
    scope: str,
    *,
    limit: int,
    window: int,
) -> bool:
    """True = allowed. Anonymous → True（呼び出し側で login_required 前提）。"""
    if user is None or not getattr(user, "is_authenticated", False):
        return True
    key = f"rl:{scope}:{user.pk}"
    return check_rate_limit(key, limit=limit, window=window)


def allow_timeline_post(user: AbstractBaseUser | None) -> bool:
    return allow_user_rate_limit(
        user,
        TIMELINE_POST_SCOPE,
        limit=TIMELINE_POST_LIMIT,
        window=TIMELINE_POST_WINDOW,
    )


def allow_timeline_comment(user: AbstractBaseUser | None) -> bool:
    return allow_user_rate_limit(
        user,
        TIMELINE_COMMENT_SCOPE,
        limit=TIMELINE_COMMENT_LIMIT,
        window=TIMELINE_COMMENT_WINDOW,
    )


def allow_timeline_like(user: AbstractBaseUser | None) -> bool:
    return allow_user_rate_limit(
        user,
        TIMELINE_LIKE_SCOPE,
        limit=TIMELINE_LIKE_LIMIT,
        window=TIMELINE_LIKE_WINDOW,
    )


def allow_chat_message(user: AbstractBaseUser | None) -> bool:
    return allow_user_rate_limit(
        user,
        CHAT_MESSAGE_SCOPE,
        limit=CHAT_MESSAGE_LIMIT,
        window=CHAT_MESSAGE_WINDOW,
    )


def allow_report(user: AbstractBaseUser | None) -> bool:
    return allow_user_rate_limit(
        user,
        REPORT_SCOPE,
        limit=REPORT_LIMIT,
        window=REPORT_WINDOW,
    )
