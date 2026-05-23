from urllib.parse import urlencode

from django.contrib.auth.models import AbstractBaseUser
from django.db.models import Avg, Case, Count, IntegerField, Sum, Value, When
from django.urls import reverse

from .models import Comment, Follow, Notification, Product, Review, ThreadPost, TimelinePost, UserProfile


def get_following_user_ids(user: AbstractBaseUser) -> list[int]:
    if not user.is_authenticated:
        return []
    return list(
        Follow.objects.filter(follower=user).values_list("following_id", flat=True)
    )


def build_home_url(
    *,
    tab: str,
    feed_scope: str = "all",
    query: str = "",
    active_faculty: str = "",
    active_tag: str = "",
) -> str:
    params: dict[str, str] = {"tab": tab}
    if feed_scope == "following":
        params["feed"] = "following"
    if query:
        params["q"] = query
    if active_faculty:
        params["faculty"] = active_faculty
    if active_tag:
        params["tag"] = active_tag
    return f"{reverse('home')}?{urlencode(params)}"


def build_product_share_timeline_body(product: Product, detail_url: str) -> str:
    prefix = "【出品シェア】"
    suffix = f" が出品されました！価格: {product.price}円。詳細はこちら：{detail_url}"
    name = product.name
    body = f"{prefix}{name}{suffix}"
    if len(body) <= 280:
        return body
    max_name_len = 280 - len(prefix) - len(suffix)
    if max_name_len < 1:
        return body[:280]
    return f"{prefix}{name[:max_name_len]}{suffix}"


def get_user_faculty(user: AbstractBaseUser) -> str:
    """出品時の学部初期値など（UserProfile.department）。"""
    if not user.is_authenticated:
        return ""
    profile = UserProfile.objects.filter(user=user).first()
    return profile.department if profile else ""


def prioritize_same_faculty(products, user: AbstractBaseUser):
    faculty = get_user_faculty(user)
    if not faculty:
        return products.order_by("-created_at")
    return products.annotate(
        faculty_priority=Case(
            When(seller__profile__department=faculty, then=Value(0)),
            default=Value(1),
            output_field=IntegerField(),
        )
    ).order_by("faculty_priority", "-created_at")


def count_user_products(user: AbstractBaseUser) -> int:
    return Product.objects.filter(seller=user).count()


def count_user_posts(user: AbstractBaseUser) -> int:
    return (
        TimelinePost.objects.filter(author=user).count()
        + ThreadPost.objects.filter(author=user).count()
        + Comment.objects.filter(author=user).count()
    )


def count_followers(user: AbstractBaseUser) -> int:
    return Follow.objects.filter(following=user).count()


def count_following(user: AbstractBaseUser) -> int:
    return Follow.objects.filter(follower=user).count()


def is_following(follower: AbstractBaseUser, target: AbstractBaseUser) -> bool:
    if not follower.is_authenticated:
        return False
    return Follow.objects.filter(follower=follower, following=target).exists()


def get_profile_stats(user: AbstractBaseUser, from_source: str) -> dict:
    """プロフィール画面上部の3つの数字（左は from により出品数/投稿数）。"""
    product_count = count_user_products(user)
    post_count = count_user_posts(user)
    if from_source == "thread":
        left_label = "投稿数"
        left_count = post_count
    else:
        left_label = "出品数"
        left_count = product_count
    return {
        "left_label": left_label,
        "left_count": left_count,
        "product_count": product_count,
        "post_count": post_count,
        "follower_count": count_followers(user),
        "following_count": count_following(user),
        "from_source": from_source if from_source in ("market", "thread") else "market",
    }


def is_trade_participant(product: Product, user: AbstractBaseUser) -> bool:
    if (
        not user.is_authenticated
        or product.status == Product.Status.AVAILABLE
        or not product.buyer_id
    ):
        return False
    return user.id in (product.seller_id, product.buyer_id)


def product_detail_path(product: Product) -> str:
    return reverse("product_detail", kwargs={"pk": product.pk})


def get_user_rating_stats(user: AbstractBaseUser) -> dict:
    stats = Review.objects.filter(reviewee=user).aggregate(
        avg=Avg("rating"),
        count=Count("id"),
    )
    count = stats["count"] or 0
    if count == 0:
        return {"avg_display": None, "count": 0}

    avg_raw = float(stats["avg"])
    avg_display = round(avg_raw * 5 / 3, 1)
    return {"avg_display": avg_display, "count": count}


def get_reviewee(product: Product, reviewer: AbstractBaseUser):
    if product.seller_id == reviewer.id:
        return product.buyer
    if product.buyer_id == reviewer.id:
        return product.seller
    return None


def calc_sales_total(user: AbstractBaseUser) -> int:
    total = (
        Product.objects.filter(seller=user, status=Product.Status.SOLD_OUT).aggregate(
            total=Sum("price")
        )["total"]
    )
    return total or 0


def notify_seller(product: Product, message: str, *, actor_id: int | None = None) -> None:
    if not product.seller_id:
        return
    if actor_id is not None and actor_id == product.seller_id:
        return
    Notification.objects.create(
        recipient=product.seller,
        message=message,
        link=product_detail_path(product),
    )
