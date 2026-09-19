"""通知バッジ・既読化の共通ロジック。"""

from __future__ import annotations

import logging

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AbstractBaseUser
from django.db.models import Q, QuerySet

from .models import FollowRequest, Notification

logger = logging.getLogger(__name__)
PUSH_TITLE = "わせわせ"

PUSH_KIND_DM = "dm"
PUSH_KIND_DM_REQUEST = "dm_request"
PUSH_KIND_DM_REQUEST_FOLLOWUP = "dm_request_followup"
PUSH_KIND_LIKE = "like"
PUSH_KIND_COMMENT = "comment"
PUSH_KIND_MENTION = "mention"
PUSH_KIND_FOLLOW = "follow"
PUSH_KIND_FOLLOW_REQUEST = "follow_request"
PUSH_KIND_COMMUNITY_REPLY = "community_reply"
PUSH_KIND_GROUP_INVITE = "group_invite"
PUSH_KIND_FLEA_COMMENT = "flea_comment"
PUSH_KIND_FLEA_LIKE = "flea_like"
PUSH_KIND_FLEA_PURCHASE = "flea_purchase"
PUSH_KIND_FLEA_INQUIRY = "flea_inquiry"
PUSH_KIND_FLEA_TRADE_CHAT = "flea_trade_chat"
PUSH_KIND_FLEA_TRADE_CONFIRMED = "flea_trade_confirmed"
PUSH_KIND_FLEA_HANDOVER = "flea_handover"
PUSH_KIND_FLEA_TRADE_COMPLETE = "flea_trade_complete"
PUSH_KIND_FLEA_TRADE_PROGRESS = "flea_trade_progress"
PUSH_KIND_SHARE_TIMELINE = "share_timeline"
PUSH_KIND_SHARE_FLEA = "share_flea"


def build_privacy_safe_push_body(
    *,
    kind: str | None = None,
    actor: AbstractBaseUser | None = None,
    push_body: str | None = None,
) -> str:
    """Lock-screen copy. Never reuse in-app Notification.message (may contain UGC)."""
    if push_body and str(push_body).strip():
        return str(push_body).strip()
    name = notification_actor_label(actor)
    templates = {
        PUSH_KIND_DM: f"「{name}さんからメッセージが届きました」",
        PUSH_KIND_DM_REQUEST: f"「{name}さんからメッセージリクエストが届きました」",
        PUSH_KIND_DM_REQUEST_FOLLOWUP: f"「{name}さんからメッセージリクエストが届きました」",
        PUSH_KIND_LIKE: f"「{name}さんがあなたの投稿にいいねしました」",
        PUSH_KIND_COMMENT: f"「{name}さんがあなたの投稿にコメントしました」",
        PUSH_KIND_MENTION: f"「{name}さんがあなたをメンションしました」",
        PUSH_KIND_FOLLOW: f"「{name}さんがあなたをフォローしました」",
        PUSH_KIND_FOLLOW_REQUEST: f"「{name}さんからフォローリクエストが届きました」",
        PUSH_KIND_COMMUNITY_REPLY: f"「{name}さんがあなたの投稿に返信しました」",
        PUSH_KIND_GROUP_INVITE: f"「{name}さんからグループ招待が届きました」",
        PUSH_KIND_FLEA_COMMENT: f"「{name}さんがあなたの商品にコメントしました」",
        PUSH_KIND_FLEA_LIKE: f"「{name}さんがあなたの商品にいいねしました」",
        PUSH_KIND_FLEA_PURCHASE: f"「{name}さんがあなたの商品を購入しました」",
        PUSH_KIND_FLEA_INQUIRY: f"「{name}さんから商品への問い合わせがあります」",
        PUSH_KIND_FLEA_TRADE_CHAT: "取引チャットにメッセージが届きました",
        PUSH_KIND_FLEA_TRADE_CONFIRMED: "取引が確定しました",
        PUSH_KIND_FLEA_HANDOVER: "受け渡しが完了しました",
        PUSH_KIND_FLEA_TRADE_COMPLETE: "取引が完了しました",
        PUSH_KIND_FLEA_TRADE_PROGRESS: "取引の確認が進みました",
        PUSH_KIND_SHARE_TIMELINE: f"「{name}さんから投稿がシェアされました」",
        PUSH_KIND_SHARE_FLEA: f"「{name}さんから商品がシェアされました」",
    }
    if kind and kind in templates:
        return templates[kind]
    return "新しい通知があります"


def push_payload_link(link: str) -> str:
    """Navigable /app/... path for FCM data.link. Maps #post-N to exact post."""
    from .notification_api_services import notification_spa_path
    from .spa_canonical import app_absolute, normalize_path_for_spa_mapping

    path, _query, fragment = normalize_path_for_spa_mapping(link or "")
    frag = (fragment or "").strip()
    if frag.startswith("post-"):
        try:
            pk = int(frag.split("-", 1)[1])
        except (TypeError, ValueError, IndexError):
            pk = 0
        if pk > 0:
            return app_absolute(f"/posts/{pk}")
    spa = notification_spa_path(link or "")
    if spa:
        return app_absolute(spa)
    raw = (link or "").strip()
    return raw or app_absolute("/notifications")


def create_notification(
    *,
    recipient: AbstractBaseUser | None = None,
    recipient_id: int | None = None,
    message: str,
    link: str = "",
    push: bool = True,
    title: str | None = None,
    actor: AbstractBaseUser | None = None,
    push_kind: str | None = None,
    push_body: str | None = None,
) -> Notification:
    """Create an in-app Notification, then best-effort privacy-safe push.

    Push copy is never Notification.message. Push failures never raise.
    """
    if title is None:
        title = PUSH_TITLE
    if recipient is None and recipient_id is None:
        raise ValueError("recipient required")
    create_kwargs: dict = {"message": message, "link": link or ""}
    if recipient is not None:
        create_kwargs["recipient"] = recipient
    else:
        create_kwargs["recipient_id"] = recipient_id
    note = Notification.objects.create(**create_kwargs)
    if not push:
        return note
    try:
        from .push_services import notify_user_push

        user = recipient
        if user is None:
            user = get_user_model().objects.filter(pk=recipient_id).first()
        if user is not None:
            body = build_privacy_safe_push_body(
                kind=push_kind, actor=actor, push_body=push_body
            )
            notify_user_push(
                user,
                body=body,
                link=push_payload_link(link or ""),
                title=title,
                notification_id=note.pk,
                notification_type=push_kind or "",
            )
    except Exception:
        logger.exception(
            "Push notify failed for user_id=%s type=%s",
            getattr(recipient, "pk", None) or recipient_id,
            push_kind or "",
        )
    return note


def notification_actor_label(actor: AbstractBaseUser | None) -> str:
    """Human-facing actor name in in-app notification copy.

    Prefers profile display name, then username/handle, then a generic label.
    Does not rewrite historical Notification.message rows.
    """
    from .services import user_display_name

    return user_display_name(actor)

# Follow-request notifications use link=/app/settings/follow-requests
_FOLLOW_REQUEST_LINK_MARKER = "/settings/follow-requests"


def follow_request_notification_q() -> Q:
    """Match Notification rows created for incoming follow requests."""
    return Q(link__icontains=_FOLLOW_REQUEST_LINK_MARKER)


def is_follow_request_notification(notification: Notification) -> bool:
    link = notification.link or ""
    return _FOLLOW_REQUEST_LINK_MARKER in link


def get_pending_follow_request_count(user: AbstractBaseUser | None) -> int:
    if user is None or not getattr(user, "is_authenticated", False):
        return 0
    return FollowRequest.objects.filter(to_user_id=user.pk).count()


def _regular_unread_qs(user: AbstractBaseUser) -> QuerySet[Notification]:
    return Notification.objects.filter(recipient=user, is_read=False).exclude(
        follow_request_notification_q()
    )


def get_regular_unread_notification_count(user: AbstractBaseUser | None) -> int:
    """Unread Notification rows excluding follow-request ping notifications."""
    if user is None or not getattr(user, "is_authenticated", False):
        return 0
    return _regular_unread_qs(user).count()


def get_unread_notification_count(user: AbstractBaseUser | None) -> int:
    """Badge total: regular unread notifications + pending follow requests.

    Follow-request Notification rows are excluded from the regular unread tally
    so the same request is not double-counted with FollowRequest rows.
    """
    if user is None or not getattr(user, "is_authenticated", False):
        return 0
    return get_regular_unread_notification_count(user) + get_pending_follow_request_count(
        user
    )


def mark_all_notifications_read(user: AbstractBaseUser) -> int:
    return Notification.objects.filter(recipient=user, is_read=False).update(
        is_read=True
    )
