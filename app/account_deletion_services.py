import logging

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q

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
    UserDirectMessageRoom,
)

logger = logging.getLogger(__name__)


def delete_user_account(user) -> None:
    """退会処理: ユーザーと関連データをデータベースから物理削除する。"""
    ensure_timelinepost_author_nullable()
    user_id = user.pk

    with transaction.atomic():
        TimelinePost.objects.filter(author=user).delete()
        Comment.objects.filter(author=user).delete()

        Product.objects.filter(seller=user).delete()

        UserDirectMessage.objects.filter(sender=user).delete()
        UserDirectMessageRoom.objects.filter(
            Q(user_a=user) | Q(user_b=user)
        ).delete()

        ChatRoom.objects.filter(buyer=user).delete()
        ChatRoomMembership.objects.filter(user=user).delete()
        ChatReadState.objects.filter(user=user).delete()

        Message.objects.filter(sender=user).delete()
        ChatMessage.objects.filter(sender=user).delete()
        TradeMessage.objects.filter(sender=user).delete()

        ContentReport.objects.filter(reporter=user).delete()
        Notification.objects.filter(recipient=user).delete()
        DevicePushToken.objects.filter(user=user).delete()
        Follow.objects.filter(Q(follower=user) | Q(following=user)).delete()
        UserBlock.objects.filter(Q(blocker=user) | Q(blocked=user)).delete()
        Review.objects.filter(Q(reviewer=user) | Q(reviewee=user)).delete()
        Like.objects.filter(user=user).delete()
        TimelineLike.objects.filter(user=user).delete()
        ThreadPost.objects.filter(author=user).delete()
        ThreadTip.objects.filter(user=user).delete()
        CommunityThread.objects.filter(author=user).delete()
        CommunityThreadReply.objects.filter(author=user).delete()
        SignupOTP.objects.filter(user=user).delete()

        deleted_count, _ = user.delete()
        if deleted_count == 0:
            raise RuntimeError(f"user.delete() removed 0 rows for user_id={user_id}")

    if get_user_model().objects.filter(pk=user_id).exists():
        raise RuntimeError(f"User record still exists after delete for user_id={user_id}")

    logger.info("Account physically deleted for user_id=%s", user_id)
