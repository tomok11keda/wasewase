import logging

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.db.models.deletion import ProtectedError

from app.media_services import ensure_timelinepost_author_nullable

from .models import (
    ChatMessage,
    ChatReadState,
    ChatRoom,
    ChatRoomMembership,
    Comment,
    CommunityThread,
    CommunityThreadReply,
    ContentReport,
    DevicePushToken,
    Follow,
    Like,
    Message,
    Notification,
    Product,
    Review,
    SignupOTP,
    ThreadPost,
    ThreadTip,
    TimelineLike,
    TimelinePost,
    TradeMessage,
    UserBlock,
    UserDirectMessage,
    UserDirectMessageReadState,
    UserDirectMessageRoom,
)

logger = logging.getLogger(__name__)


def _delete_step(label: str, queryset):
    """削除ステップを実行し、件数をログに残す。"""
    count, detail = queryset.delete()
    logger.info("Account deletion step %s: deleted %s rows (%s)", label, count, detail)
    return count


def delete_user_account(user) -> None:
    """退会処理: ユーザーと関連データをデータベースから物理削除する。"""
    ensure_timelinepost_author_nullable()
    user_id = user.pk
    logger.info("Account deletion started for user_id=%s email=%s", user_id, user.email)

    try:
        with transaction.atomic():
            dm_room_ids = list(
                UserDirectMessageRoom.objects.filter(
                    Q(user_a=user) | Q(user_b=user)
                ).values_list("pk", flat=True)
            )

            _delete_step(
                "dm_read_states",
                UserDirectMessageReadState.objects.filter(
                    Q(user=user) | Q(room_id__in=dm_room_ids)
                ),
            )
            _delete_step(
                "dm_messages_in_user_rooms",
                UserDirectMessage.objects.filter(room_id__in=dm_room_ids),
            )
            _delete_step(
                "dm_rooms",
                UserDirectMessageRoom.objects.filter(pk__in=dm_room_ids),
            )
            _delete_step(
                "dm_messages_sent_elsewhere",
                UserDirectMessage.objects.filter(sender=user),
            )

            _delete_step(
                "chat_read_states",
                ChatReadState.objects.filter(user=user),
            )
            _delete_step(
                "chat_memberships",
                ChatRoomMembership.objects.filter(user=user),
            )
            _delete_step(
                "product_chat_messages",
                Message.objects.filter(sender=user),
            )
            _delete_step(
                "group_chat_messages",
                ChatMessage.objects.filter(sender=user),
            )
            _delete_step(
                "trade_messages",
                TradeMessage.objects.filter(sender=user),
            )
            _delete_step(
                "product_chat_rooms_as_buyer",
                ChatRoom.objects.filter(buyer=user),
            )

            _delete_step(
                "timeline_likes",
                TimelineLike.objects.filter(user=user),
            )
            _delete_step(
                "comments_by_user",
                Comment.objects.filter(author=user),
            )
            _delete_step(
                "timeline_posts",
                TimelinePost.objects.filter(author=user),
            )

            _delete_step(
                "products_as_seller",
                Product.objects.filter(seller=user),
            )

            _delete_step(
                "content_reports",
                ContentReport.objects.filter(reporter=user),
            )
            _delete_step(
                "notifications",
                Notification.objects.filter(recipient=user),
            )
            _delete_step(
                "device_push_tokens",
                DevicePushToken.objects.filter(user=user),
            )
            _delete_step(
                "follows",
                Follow.objects.filter(Q(follower=user) | Q(following=user)),
            )
            _delete_step(
                "user_blocks",
                UserBlock.objects.filter(Q(blocker=user) | Q(blocked=user)),
            )
            _delete_step(
                "reviews",
                Review.objects.filter(Q(reviewer=user) | Q(reviewee=user)),
            )
            _delete_step(
                "product_likes",
                Like.objects.filter(user=user),
            )
            _delete_step(
                "thread_posts",
                ThreadPost.objects.filter(author=user),
            )
            _delete_step(
                "thread_tips",
                ThreadTip.objects.filter(user=user),
            )
            _delete_step(
                "community_thread_replies",
                CommunityThreadReply.objects.filter(author=user),
            )
            _delete_step(
                "community_threads",
                CommunityThread.objects.filter(author=user),
            )
            _delete_step(
                "signup_otp",
                SignupOTP.objects.filter(user=user),
            )

            user.groups.clear()
            user.user_permissions.clear()

            deleted_count, delete_detail = user.delete()
            logger.info(
                "Account deletion user.delete() for user_id=%s: deleted %s rows (%s)",
                user_id,
                deleted_count,
                delete_detail,
            )
            if deleted_count == 0:
                raise RuntimeError(
                    f"user.delete() removed 0 rows for user_id={user_id}"
                )

    except ProtectedError as exc:
        protected = getattr(exc, "protected_objects", None) or []
        protected_summary = [
            f"{obj.__class__.__name__}(pk={getattr(obj, 'pk', '?')})"
            for obj in protected
        ]
        logger.error(
            "Account deletion ProtectedError for user_id=%s: %s protected_objects=%s",
            user_id,
            exc,
            protected_summary,
            exc_info=True,
        )
        raise

    except IntegrityError as exc:
        logger.error(
            "Account deletion IntegrityError for user_id=%s: %s",
            user_id,
            exc,
            exc_info=True,
        )
        raise

    except Exception as exc:
        logger.error(
            "Account deletion unexpected error for user_id=%s: %s (%s)",
            user_id,
            exc,
            type(exc).__name__,
            exc_info=True,
        )
        raise

    if get_user_model().objects.filter(pk=user_id).exists():
        raise RuntimeError(
            f"User record still exists after delete for user_id={user_id}"
        )

    logger.info("Account physically deleted for user_id=%s", user_id)
