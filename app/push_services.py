"""Firebase Cloud Messaging によるプッシュ通知。"""

from __future__ import annotations

import json
import logging
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

PLATFORM_IOS = DevicePushToken.Platform.IOS
PLATFORM_ANDROID = DevicePushToken.Platform.ANDROID


def _firebase_credentials_available() -> bool:
    return bool(
        getattr(settings, "FIREBASE_CREDENTIALS_JSON", "")
        or getattr(settings, "FIREBASE_CREDENTIALS_PATH", "")
    )


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
        logger.exception("Failed to initialize Firebase Admin SDK.")
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
    """デバイストークンを登録または更新する。"""
    token = (token or "").strip()
    if not token:
        raise ValueError("token is required")

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


def send_push_to_user(
    user: AbstractBaseUser,
    *,
    title: str,
    body: str,
    link: str = "",
) -> int:
    """
    ユーザーの登録済みデバイスへプッシュ通知を送信する。
    成功した送信数を返す。Firebase 未設定時は 0。
    """
    if not getattr(settings, "PUSH_NOTIFICATIONS_ENABLED", False):
        return 0

    tokens = list(
        DevicePushToken.objects.filter(user_id=user.pk).values_list("token", flat=True)
    )
    if not tokens:
        return 0

    app = get_firebase_app()
    if not app:
        return 0

    from firebase_admin import messaging

    data = {"link": link} if link else {}
    multicast = messaging.MulticastMessage(
        notification=messaging.Notification(title=title, body=body),
        data=data,
        tokens=tokens,
        apns=messaging.APNSConfig(
            payload=messaging.APNSPayload(
                aps=messaging.Aps(sound="default"),
            )
        ),
        android=messaging.AndroidConfig(priority="high"),
    )

    try:
        response = messaging.send_each_for_multicast(multicast, app=app)
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
                tokens[idx][:12],
                error,
            )

    if stale_tokens:
        DevicePushToken.objects.filter(token__in=stale_tokens).delete()

    return response.success_count


def _is_unrecoverable_token_error(error: Exception) -> bool:
    from firebase_admin import messaging

    return isinstance(
        error,
        (
            messaging.UnregisteredError,
            messaging.SenderIdMismatchError,
        ),
    )


def notify_user_push(
    user: AbstractBaseUser,
    *,
    body: str,
    link: str = "",
    title: str = "わせわせ",
) -> int:
    """アプリ内通知と同じ文面でプッシュを送る。"""
    return send_push_to_user(user, title=title, body=body, link=link)
