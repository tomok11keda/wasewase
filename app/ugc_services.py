"""UGC 安全対策: 通報・ブロック・モデレーション用フィルタ。"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AbstractBaseUser
from django.db.models import Q, QuerySet
from django.utils import timezone

from .models import Comment, ContentReport, Follow, FollowRequest, Product, TimelinePost, UserBlock

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


def is_either_blocked(
    user_a: AbstractBaseUser | None,
    user_b: AbstractBaseUser | None,
) -> bool:
    """双方向のいずれかでブロックされていれば True。"""
    if (
        user_a is None
        or user_b is None
        or not getattr(user_a, "is_authenticated", False)
        or not getattr(user_b, "is_authenticated", False)
        or user_a.pk == user_b.pk
    ):
        return False
    return UserBlock.objects.filter(
        Q(blocker=user_a, blocked=user_b) | Q(blocker=user_b, blocked=user_a)
    ).exists()


def block_user(blocker: AbstractBaseUser, blocked: AbstractBaseUser) -> UserBlock:
    if blocker.pk == blocked.pk:
        raise ValueError("cannot block self")
    block, _created = UserBlock.objects.get_or_create(
        blocker=blocker,
        blocked=blocked,
    )
    Follow.objects.filter(follower=blocker, following=blocked).delete()
    Follow.objects.filter(follower=blocked, following=blocker).delete()
    FollowRequest.objects.filter(from_user=blocker, to_user=blocked).delete()
    FollowRequest.objects.filter(from_user=blocked, to_user=blocker).delete()
    return block


def unblock_user(blocker: AbstractBaseUser, blocked: AbstractBaseUser) -> None:
    UserBlock.objects.filter(blocker=blocker, blocked=blocked).delete()


def get_blocked_users(blocker: AbstractBaseUser) -> QuerySet[UserBlock]:
    """自分がブロックしているユーザー一覧（新しい順）。"""
    if blocker is None or not blocker.is_authenticated:
        return UserBlock.objects.none()
    return (
        UserBlock.objects.filter(blocker=blocker)
        .select_related("blocked", "blocked__profile")
        .order_by("-created_at")
    )


def _filter_private_account_owners(
    qs: QuerySet,
    viewer: AbstractBaseUser | None,
    *,
    user_field: str,
) -> QuerySet:
    """Hide rows owned by private accounts the viewer cannot access."""
    private_q = Q(**{f"{user_field}__profile__is_private": True})
    null_owner = Q(**{f"{user_field}__isnull": True})
    if viewer is None or not getattr(viewer, "is_authenticated", False):
        return qs.filter(null_owner | ~private_q)
    following_ids = Follow.objects.filter(follower_id=viewer.pk).values("following_id")
    return qs.filter(
        null_owner
        | ~private_q
        | Q(**{f"{user_field}_id": viewer.pk})
        | Q(**{f"{user_field}_id__in": following_ids})
    )


def filter_visible_timeline_posts(
    qs: QuerySet[TimelinePost],
    viewer: AbstractBaseUser | None,
) -> QuerySet[TimelinePost]:
    qs = qs.filter(is_removed=False)
    blocked_ids = get_blocked_user_ids(viewer)
    if blocked_ids:
        qs = qs.exclude(author_id__in=blocked_ids)
    return _filter_private_account_owners(qs, viewer, user_field="author")


def filter_visible_products(
    qs: QuerySet[Product],
    viewer: AbstractBaseUser | None,
) -> QuerySet[Product]:
    qs = qs.filter(is_removed=False)
    blocked_ids = get_blocked_user_ids(viewer)
    if blocked_ids:
        qs = qs.exclude(seller_id__in=blocked_ids)
    return _filter_private_account_owners(qs, viewer, user_field="seller")


def get_visible_product_or_404(
    viewer: AbstractBaseUser | None,
    pk: int,
) -> Product:
    """Product detail/mutate helper — Http404 if private/block hides it."""
    from django.shortcuts import get_object_or_404

    return get_object_or_404(
        filter_visible_products(
            Product.objects.select_related(
                "seller", "seller__profile", "buyer", "buyer__profile"
            ).prefetch_related("likes"),
            viewer,
        ),
        pk=pk,
    )


def get_visible_timeline_post_or_404(
    viewer: AbstractBaseUser | None,
    pk: int,
) -> TimelinePost:
    """Timeline mutate helper — Http404 if private/block hides it."""
    from django.shortcuts import get_object_or_404

    return get_object_or_404(
        filter_visible_timeline_posts(
            TimelinePost.objects.select_related("author", "author__profile"),
            viewer,
        ),
        pk=pk,
    )


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
