from django.contrib.auth.models import AbstractBaseUser
from django.db.models import Avg, Case, Count, IntegerField, Sum, Value, When
from django.urls import reverse

from .models import Notification, Product, Review, UserProfile

def get_user_faculty(user: AbstractBaseUser) -> str:
    if not user.is_authenticated:
        return ""
    profile = UserProfile.objects.filter(user=user).first()
    return profile.faculty if profile else ""


def prioritize_same_faculty(products, user: AbstractBaseUser):
    faculty = get_user_faculty(user)
    if not faculty:
        return products.order_by("-created_at")
    return products.annotate(
        faculty_priority=Case(
            When(seller__profile__faculty=faculty, then=Value(0)),
            default=Value(1),
            output_field=IntegerField(),
        )
    ).order_by("faculty_priority", "-created_at")


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
