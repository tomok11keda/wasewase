"""UGC 安全対策: 通報・ブロック・モデレーション用フィルタ。"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AbstractBaseUser
from django.db.models import QuerySet
from django.utils import timezone

from .models import Comment, ContentReport, Follow, Product, TimelinePost, UserBlock

User = get_user_model()


def get_blocked_user_ids(viewer: AbstractBaseUser | None) -> set[int]:
    if viewer is None or not viewer.is_authenticated:
        return set()
    return set(
        UserBlock.objects.filter(blocker_id=viewer.pk).values_list(
            "blocked_id", flat=True
        )
    )


def is_user_blocked(blocker: AbstractBaseUser, blocked: AbstractBaseUser) -> bool:
    if not blocker.is_authenticated or blocker.pk == blocked.pk:
        return False
    return UserBlock.objects.filter(blocker=blocker, blocked=blocked).exists()


def block_user(blocker: AbstractBaseUser, blocked: AbstractBaseUser) -> UserBlock:
    if blocker.pk == blocked.pk:
        raise ValueError("cannot block self")
    block, _created = UserBlock.objects.get_or_create(
        blocker=blocker,
        blocked=blocked,
    )
    Follow.objects.filter(follower=blocker, following=blocked).delete()
    Follow.objects.filter(follower=blocked, following=blocker).delete()
    return block


def unblock_user(blocker: AbstractBaseUser, blocked: AbstractBaseUser) -> None:
    UserBlock.objects.filter(blocker=blocker, blocked=blocked).delete()


def filter_visible_timeline_posts(
    qs: QuerySet[TimelinePost],
    viewer: AbstractBaseUser | None,
) -> QuerySet[TimelinePost]:
    qs = qs.filter(is_removed=False)
    blocked_ids = get_blocked_user_ids(viewer)
    if blocked_ids:
        qs = qs.exclude(author_id__in=blocked_ids)
    return qs


def filter_visible_products(
    qs: QuerySet[Product],
    viewer: AbstractBaseUser | None,
) -> QuerySet[Product]:
    qs = qs.filter(is_removed=False)
    blocked_ids = get_blocked_user_ids(viewer)
    if blocked_ids:
        qs = qs.exclude(seller_id__in=blocked_ids)
    return qs


def filter_visible_comments(
    qs: QuerySet[Comment],
    viewer: AbstractBaseUser | None,
) -> QuerySet[Comment]:
    qs = qs.filter(is_removed=False)
    blocked_ids = get_blocked_user_ids(viewer)
    if blocked_ids:
        qs = qs.exclude(author_id__in=blocked_ids)
    return qs


def get_report_target(target_type: str, target_id: int):
    if target_type == ContentReport.TargetType.POST:
        return TimelinePost.objects.filter(pk=target_id, is_removed=False).first()
    if target_type == ContentReport.TargetType.PRODUCT:
        return Product.objects.filter(pk=target_id, is_removed=False).first()
    if target_type == ContentReport.TargetType.COMMENT:
        return Comment.objects.filter(pk=target_id, is_removed=False).first()
    if target_type == ContentReport.TargetType.USER:
        return User.objects.filter(pk=target_id, is_active=True).first()
    return None


def get_reported_user_id(target_type: str, target) -> int | None:
    if target is None:
        return None
    if target_type == ContentReport.TargetType.POST:
        return target.author_id
    if target_type == ContentReport.TargetType.PRODUCT:
        return target.seller_id
    if target_type == ContentReport.TargetType.COMMENT:
        return target.author_id
    if target_type == ContentReport.TargetType.USER:
        return target.pk
    return None


def soft_remove_content(
    *,
    target_type: str,
    target_id: int,
    moderator: AbstractBaseUser,
) -> bool:
    now = timezone.now()
    updated = 0
    if target_type == ContentReport.TargetType.POST:
        updated = TimelinePost.objects.filter(pk=target_id, is_removed=False).update(
            is_removed=True,
            removed_at=now,
            removed_by=moderator,
        )
    elif target_type == ContentReport.TargetType.PRODUCT:
        updated = Product.objects.filter(pk=target_id, is_removed=False).update(
            is_removed=True,
            removed_at=now,
            removed_by=moderator,
        )
    elif target_type == ContentReport.TargetType.COMMENT:
        updated = Comment.objects.filter(pk=target_id, is_removed=False).update(
            is_removed=True,
            removed_at=now,
            removed_by=moderator,
        )
    return updated > 0
