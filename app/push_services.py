"""Firebase Cloud Messaging によるプッシュ通知。"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
import json
import logging
import re
from typing import TYPE_CHECKING

from django.conf import settings
from django.contrib.auth.models import AbstractBaseUser
from django.utils import timezone

from .models import DevicePushToken

if TYPE_CHECKING:
    from firebase_admin import App

logger = logging.getLogger(__name__)

_firebase_app: App | None = None
_firebase_init_attempted = False
_fcm_executor: ThreadPoolExecutor | None = None
_FCM_SEND_TIMEOUT_SEC = 4.0

PLATFORM_IOS = DevicePushToken.Platform.IOS
PLATFORM_ANDROID = DevicePushToken.Platform.ANDROID

# Capacitor PushNotifications on iOS returns a raw APNs device token (hex).
# Django / firebase-admin send via FCM, so APNs hex tokens must not be stored.
_APNS_DEVICE_TOKEN_RE = re.compile(r"^[0-9a-fA-F]{64}$|^[0-9a-fA-F]{128}$")


def is_likely_apns_device_token(token: str) -> bool:
    """True when the value looks like a raw APNs device token, not an FCM token."""
    return bool(_APNS_DEVICE_TOKEN_RE.fullmatch((token or "").strip()))


def _firebase_credentials_available() -> bool:
    return bool(
        getattr(settings, "FIREBASE_CREDENTIALS_JSON", "")
        or getattr(settings, "FIREBASE_CREDENTIALS_PATH", "")
    )


def reset_firebase_app_for_tests() -> None:
    """Test helper: allow get_firebase_app() to run init again."""
    global _firebase_app, _firebase_init_attempted
    _firebase_app = None
    _firebase_init_attempted = False


def _token_log_prefix(token: str) -> str:
    value = (token or "").strip()
    # Never log a complete FCM token (including short/unexpected values).
    if len(value) <= 12:
        return "***"
    return value[:8]


def get_firebase_app():
    """Firebase Admin アプリを遅延初期化する。未設定時は None。"""
    global _firebase_app, _firebase_init_attempted

    if _firebase_init_attempted:
        return _firebase_app

    _firebase_init_attempted = True
    if not _firebase_credentials_available():
        logger.info("Firebase credentials not configured; push notifications disabled.")
        return None

    try:
        import firebase_admin
        from firebase_admin import credentials
    except ImportError:
        logger.warning("firebase-admin is not installed; push notifications disabled.")
        return None

    if firebase_admin._apps:
        _firebase_app = firebase_admin.get_app()
        return _firebase_app

    cred_json = getattr(settings, "FIREBASE_CREDENTIALS_JSON", "")
    cred_path = getattr(settings, "FIREBASE_CREDENTIALS_PATH", "")
    try:
        if cred_json:
            cred = credentials.Certificate(json.loads(cred_json))
        else:
            cred = credentials.Certificate(cred_path)
        _firebase_app = firebase_admin.initialize_app(cred)
    except Exception:
        # Do not log the exception body — it can include credential JSON snippets.
        logger.warning("Failed to initialize Firebase Admin SDK; push notifications disabled.")
        _firebase_app = None

    return _firebase_app


def normalize_platform(platform: str) -> str:
    value = (platform or "").strip().lower()
    if value in (PLATFORM_ANDROID, "android"):
        return PLATFORM_ANDROID
    return PLATFORM_IOS


def register_device_token(
    user: AbstractBaseUser,
    token: str,
    *,
    platform: str = PLATFORM_IOS,
) -> DevicePushToken:
    """FCM 登録トークンを登録または更新する。

    同一トークンが別ユーザーに紐付いていても、現在の user へ付け替える
    （端末のログアウト→別アカウントログイン向け）。
    生の APNs デバイストークンは拒否する（FCM 送信と不一致になるため）。
    """
    token = (token or "").strip()
    if not token:
        raise ValueError("token is required")
    if is_likely_apns_device_token(token):
        raise ValueError("apns_token_not_supported")

    platform = normalize_platform(platform)
    now = timezone.now()
    existing = DevicePushToken.objects.filter(token=token).first()
    if existing:
        existing.user = user
        existing.platform = platform
        existing.updated_at = now
        existing.save(update_fields=["user", "platform", "updated_at"])
        return existing

    return DevicePushToken.objects.create(
        user=user,
        token=token,
        platform=platform,
        updated_at=now,
    )


def unregister_device_token(
    user: AbstractBaseUser,
    token: str,
) -> bool:
    """現在のユーザーに紐付くトークンだけ削除。他ユーザーのトークンは触らない。"""
    token = (token or "").strip()
    if not token:
        return False
    deleted, _ = DevicePushToken.objects.filter(
        user_id=user.pk, token=token
    ).delete()
    return deleted > 0


def _get_fcm_executor() -> ThreadPoolExecutor:
    global _fcm_executor
    if _fcm_executor is None:
        _fcm_executor = ThreadPoolExecutor(
            max_workers=2, thread_name_prefix="fcm-push"
        )
    return _fcm_executor


def sendable_fcm_tokens_for_user(user: AbstractBaseUser) -> tuple[list[str], int]:
    """Return FCM tokens for send, skipping raw APNs-looking values.

    Does not delete skipped rows (no production DB cleanup in this phase).
    """
    tokens = list(
        DevicePushToken.objects.filter(user_id=user.pk).values_list("token", flat=True)
    )
    sendable = [token for token in tokens if not is_likely_apns_device_token(token)]
    skipped = len(tokens) - len(sendable)
    return sendable, skipped


def send_push_to_user(
    user: AbstractBaseUser,
    *,
    title: str,
    body: str,
    link: str = "",
    notification_id: int | str | None = None,
    notification_type: str = "",
) -> int:
    """
    ユーザーの登録済みデバイスへプッシュ通知を送信する。
    成功した送信数を返す。Firebase 未設定時は 0。
    例外は飲み込んで 0 を返す（呼び出し元のユーザー操作を落とさない）。
    """
    try:
        return _send_push_to_user_unguarded(
            user,
            title=title,
            body=body,
            link=link,
            notification_id=notification_id,
            notification_type=notification_type,
        )
    except Exception:
        logger.exception("Push send failed for user_id=%s", getattr(user, "pk", None))
        return 0


def _send_push_to_user_unguarded(
    user: AbstractBaseUser,
    *,
    title: str,
    body: str,
    link: str = "",
    notification_id: int | str | None = None,
    notification_type: str = "",
) -> int:
    if not getattr(settings, "PUSH_NOTIFICATIONS_ENABLED", False):
        return 0
    if user is None or not getattr(user, "pk", None):
        return 0

    tokens, skipped_apns = sendable_fcm_tokens_for_user(user)
    if skipped_apns:
        logger.info(
            "Push skipped APNs-looking tokens user_id=%s count=%s",
            user.pk,
            skipped_apns,
        )
    if not tokens:
        return 0

    app = get_firebase_app()
    if not app:
        return 0

    from firebase_admin import messaging

    data = {
        "notification_id": "" if notification_id is None else str(notification_id),
        "link": str(link or ""),
    }
    multicast = messaging.MulticastMessage(
        notification=messaging.Notification(title=title, body=body),
        data=data,
        tokens=tokens,
        apns=messaging.APNSConfig(
            headers={"apns-priority": "10"},
            payload=messaging.APNSPayload(
                aps=messaging.Aps(sound="default"),
                notification_id=data["notification_id"],
                link=data["link"],
            ),
        ),
        android=messaging.AndroidConfig(priority="high"),
    )

    try:
        future = _get_fcm_executor().submit(
            messaging.send_each_for_multicast, multicast, app=app
        )
        try:
            response = future.result(timeout=_FCM_SEND_TIMEOUT_SEC)
        except FuturesTimeout:
            logger.warning("FCM send timed out for user_id=%s", user.pk)
            return 0
    except Exception:
        logger.exception("FCM multicast send failed for user_id=%s", user.pk)
        return 0

    stale_tokens: list[str] = []
    for idx, send_response in enumerate(response.responses):
        if send_response.success:
            continue
        error = send_response.exception
        if error and _is_unrecoverable_token_error(error):
            stale_tokens.append(tokens[idx])
        else:
            logger.warning(
                "FCM send failed for user_id=%s token=%s…: %s",
                user.pk,
                _token_log_prefix(tokens[idx]),
                type(error).__name__ if error else "unknown",
            )

    if stale_tokens:
        DevicePushToken.objects.filter(token__in=stale_tokens).delete()

    logger.info(
        "Push send user_id=%s type=%s success=%s stale_removed=%s apns_skipped=%s",
        user.pk,
        notification_type or "-",
        int(getattr(response, "success_count", 0) or 0),
        len(stale_tokens),
        skipped_apns,
    )
    return int(getattr(response, "success_count", 0) or 0)


def _is_unrecoverable_token_error(error: Exception) -> bool:
    from firebase_admin import messaging

    if isinstance(
        error,
        (
            messaging.UnregisteredError,
            messaging.SenderIdMismatchError,
        ),
    ):
        return True
    code = str(getattr(error, "code", "") or "").upper()
    return "UNREGISTERED" in code or "SENDER_ID_MISMATCH" in code


def notify_user_push(
    user: AbstractBaseUser,
    *,
    body: str,
    link: str = "",
    title: str = "わせわせ",
    notification_id: int | str | None = None,
    notification_type: str = "",
) -> int:
    """Privacy-safe push. Failures return 0 and never raise."""
    try:
        return send_push_to_user(
            user,
            title=title,
            body=body,
            link=link,
            notification_id=notification_id,
            notification_type=notification_type,
        )
    except Exception:
        logger.exception("notify_user_push failed for user_id=%s", getattr(user, "pk", None))
        return 0
