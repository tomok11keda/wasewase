from django.contrib.auth.models import AbstractBaseUser
from django.db.models import Q, Sum

from .models import Product, TimelinePost, UserProfile

SCORE_PER_LEVEL = 10
TRADE_SCORE_MULTIPLIER = 20


def level_from_score(score: int) -> int:
    return max(1, score // SCORE_PER_LEVEL + 1)


def rank_title_from_level(level: int) -> str:
    if level >= 50:
        return "大隈重信クラス"
    if level >= 30:
        return "早稲田インフルエンサー"
    if level >= 15:
        return "わせわせ常連組"
    if level >= 5:
        return "アクティブ早大生"
    return "一般学生"


def score_to_next_level(score: int) -> int:
    level = level_from_score(score)
    return level * SCORE_PER_LEVEL - score


def count_completed_trades(user: AbstractBaseUser) -> int:
    return Product.objects.filter(
        status=Product.Status.SOLD_OUT,
    ).filter(Q(seller=user) | Q(buyer=user)).count()


def compute_level_score(user: AbstractBaseUser) -> dict:
    engagement = TimelinePost.objects.filter(author=user).aggregate(
        likes=Sum("like_count"),
        gods=Sum("god_count"),
    )
    likes_received = engagement["likes"] or 0
    gods_received = engagement["gods"] or 0
    engagement_score = likes_received + gods_received

    completed_trades = count_completed_trades(user)
    trade_score = completed_trades * TRADE_SCORE_MULTIPLIER
    total_score = engagement_score + trade_score
    level = level_from_score(total_score)

    return {
        "total_score": total_score,
        "level": level,
        "rank_title": rank_title_from_level(level),
        "score_to_next_level": score_to_next_level(total_score),
        "engagement_score": engagement_score,
        "likes_received": likes_received,
        "gods_received": gods_received,
        "completed_trades": completed_trades,
        "trade_score": trade_score,
    }


def recalculate_user_level(user: AbstractBaseUser) -> dict:
    stats = compute_level_score(user)
    profile, _ = UserProfile.objects.get_or_create(user=user)
    if profile.level_score != stats["total_score"] or profile.level != stats["level"]:
        profile.level_score = stats["total_score"]
        profile.level = stats["level"]
        profile.save(update_fields=["level_score", "level"])
    return stats


def get_user_level_stats(user: AbstractBaseUser) -> dict:
    return recalculate_user_level(user)


def sync_user_level_stats(user: AbstractBaseUser | None) -> None:
    if user is not None and getattr(user, "is_authenticated", False):
        recalculate_user_level(user)
