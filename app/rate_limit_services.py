"""Shared write-path rate limits (LocMem/Redis cache via check_rate_limit).

既存の course_services.check_rate_limit を再利用する。
キーは user 単位。scope を分けて相互干渉を避ける。
cache 障害時は fail-open（既存と同じ）。

認証（anonymous）は user.pk ではなく IP + hashed identifier を使う。
"""

from __future__ import annotations

import hashlib
import hmac

from django.conf import settings
from django.contrib.auth.models import AbstractBaseUser
from django.http import HttpRequest

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


# --- Auth (anonymous): IP + hashed identifier. Not account lockout. ---
AUTH_LOGIN_ID_SCOPE = "auth_login_id"
AUTH_LOGIN_ID_LIMIT = 10
AUTH_LOGIN_ID_WINDOW = 600

AUTH_LOGIN_IP_SCOPE = "auth_login_ip"
AUTH_LOGIN_IP_LIMIT = 40
AUTH_LOGIN_IP_WINDOW = 600

AUTH_SIGNUP_OTP_EMAIL_SCOPE = "auth_signup_otp_email"
AUTH_SIGNUP_OTP_EMAIL_LIMIT = 3
AUTH_SIGNUP_OTP_EMAIL_WINDOW = 600

AUTH_SIGNUP_OTP_EMAIL_HOUR_SCOPE = "auth_signup_otp_email_hour"
AUTH_SIGNUP_OTP_EMAIL_HOUR_LIMIT = 5
AUTH_SIGNUP_OTP_EMAIL_HOUR_WINDOW = 3600

AUTH_SIGNUP_OTP_IP_SCOPE = "auth_signup_otp_ip"
AUTH_SIGNUP_OTP_IP_LIMIT = 15
AUTH_SIGNUP_OTP_IP_WINDOW = 600

AUTH_RESET_OTP_EMAIL_SCOPE = "auth_reset_otp_email"
AUTH_RESET_OTP_EMAIL_LIMIT = 3
AUTH_RESET_OTP_EMAIL_WINDOW = 900

AUTH_RESET_OTP_IP_SCOPE = "auth_reset_otp_ip"
AUTH_RESET_OTP_IP_LIMIT = 10
AUTH_RESET_OTP_IP_WINDOW = 3600

AUTH_OTP_VERIFY_ID_SCOPE = "auth_otp_verify_id"
AUTH_OTP_VERIFY_ID_LIMIT = 20
AUTH_OTP_VERIFY_ID_WINDOW = 600

AUTH_OTP_VERIFY_IP_SCOPE = "auth_otp_verify_ip"
AUTH_OTP_VERIFY_IP_LIMIT = 40
AUTH_OTP_VERIFY_IP_WINDOW = 600


def _secret_key_bytes() -> bytes:
    key = settings.SECRET_KEY
    if isinstance(key, bytes):
        return key
    return str(key).encode("utf-8")


def normalize_auth_email(value: str | None) -> str:
    return (value or "").strip().lower()


def auth_identifier_digest(value: str | None) -> str:
    """HMAC-SHA256 of normalized email. Cache keys must not contain raw email."""
    normalized = normalize_auth_email(value)
    digest = hmac.new(
        _secret_key_bytes(),
        normalized.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return digest


def client_ip(request: HttpRequest | None) -> str:
    """REMOTE_ADDR only. Do not trust client-controlled forwarded headers."""
    if request is None:
        return "unknown"
    raw = (request.META.get("REMOTE_ADDR") or "").strip()
    return raw or "unknown"


def _allow_keyed(scope: str, token: str, *, limit: int, window: int) -> bool:
    key = f"rl:{scope}:{token}"
    return check_rate_limit(key, limit=limit, window=window)


def _allow_ip_and_identifier(
    request: HttpRequest | None,
    identifier: str | None,
    *,
    ip_scope: str,
    ip_limit: int,
    ip_window: int,
    id_scope: str | None,
    id_limit: int,
    id_window: int,
    extra_id_checks: tuple[tuple[str, int, int], ...] = (),
) -> bool:
    """Evaluate all applicable limits (no short-circuit) so budgets stay independent."""
    results: list[bool] = []
    email = normalize_auth_email(identifier)
    if email and id_scope:
        digest = auth_identifier_digest(email)
        results.append(
            _allow_keyed(id_scope, digest, limit=id_limit, window=id_window)
        )
        for extra_scope, extra_limit, extra_window in extra_id_checks:
            results.append(
                _allow_keyed(extra_scope, digest, limit=extra_limit, window=extra_window)
            )
    results.append(
        _allow_keyed(
            ip_scope,
            client_ip(request),
            limit=ip_limit,
            window=ip_window,
        )
    )
    return all(results)


def allow_login_rate_limit(request: HttpRequest | None, email: str | None) -> bool:
    return _allow_ip_and_identifier(
        request,
        email,
        ip_scope=AUTH_LOGIN_IP_SCOPE,
        ip_limit=AUTH_LOGIN_IP_LIMIT,
        ip_window=AUTH_LOGIN_IP_WINDOW,
        id_scope=AUTH_LOGIN_ID_SCOPE,
        id_limit=AUTH_LOGIN_ID_LIMIT,
        id_window=AUTH_LOGIN_ID_WINDOW,
    )


def allow_signup_otp_send(request: HttpRequest | None, email: str | None) -> bool:
    """Initial signup OTP and resend share this budget."""
    return _allow_ip_and_identifier(
        request,
        email,
        ip_scope=AUTH_SIGNUP_OTP_IP_SCOPE,
        ip_limit=AUTH_SIGNUP_OTP_IP_LIMIT,
        ip_window=AUTH_SIGNUP_OTP_IP_WINDOW,
        id_scope=AUTH_SIGNUP_OTP_EMAIL_SCOPE,
        id_limit=AUTH_SIGNUP_OTP_EMAIL_LIMIT,
        id_window=AUTH_SIGNUP_OTP_EMAIL_WINDOW,
        extra_id_checks=(
            (
                AUTH_SIGNUP_OTP_EMAIL_HOUR_SCOPE,
                AUTH_SIGNUP_OTP_EMAIL_HOUR_LIMIT,
                AUTH_SIGNUP_OTP_EMAIL_HOUR_WINDOW,
            ),
        ),
    )


def allow_reset_otp_send(request: HttpRequest | None, email: str | None) -> bool:
    """Password-reset initial request and resend share this budget."""
    return _allow_ip_and_identifier(
        request,
        email,
        ip_scope=AUTH_RESET_OTP_IP_SCOPE,
        ip_limit=AUTH_RESET_OTP_IP_LIMIT,
        ip_window=AUTH_RESET_OTP_IP_WINDOW,
        id_scope=AUTH_RESET_OTP_EMAIL_SCOPE,
        id_limit=AUTH_RESET_OTP_EMAIL_LIMIT,
        id_window=AUTH_RESET_OTP_EMAIL_WINDOW,
    )


def allow_otp_verify_rate_limit(request: HttpRequest | None, email: str | None) -> bool:
    """HTTP flood limit. Does not replace OTP_MAX_ATTEMPTS."""
    return _allow_ip_and_identifier(
        request,
        email,
        ip_scope=AUTH_OTP_VERIFY_IP_SCOPE,
        ip_limit=AUTH_OTP_VERIFY_IP_LIMIT,
        ip_window=AUTH_OTP_VERIFY_IP_WINDOW,
        id_scope=AUTH_OTP_VERIFY_ID_SCOPE,
        id_limit=AUTH_OTP_VERIFY_ID_LIMIT,
        id_window=AUTH_OTP_VERIFY_ID_WINDOW,
    )
