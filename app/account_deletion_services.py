from django.db import transaction
from django.db.models import Q

from .models import (
    ContentReport,
    Notification,
    Product,
    TimelinePost,
    UserDirectMessageRoom,
)


def delete_user_account(user):
    """退会処理: 投稿は匿名化し、プライベートデータは物理削除する。"""
    with transaction.atomic():
        TimelinePost.objects.filter(author=user).update(author=None)
        Product.objects.filter(seller=user).delete()
        ContentReport.objects.filter(reporter=user).delete()
        Notification.objects.filter(recipient=user).delete()
        UserDirectMessageRoom.objects.filter(
            Q(user_a=user) | Q(user_b=user)
        ).delete()
        user.delete()
