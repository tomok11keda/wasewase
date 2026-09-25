"""Flea listing → at most one TimelinePost share per Product."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from django.contrib.auth.models import AbstractBaseUser
from django.db import transaction
from django.http import HttpRequest

from .models import Product, TimelinePost
from .rate_limit_services import allow_timeline_post
from .services import FLEA_TIMELINE_SHARE_BODY, get_user_faculty

_TRUE_VALUES = {"1", "true", "on", "yes"}


class ShareStatus(str, Enum):
    CREATED = "created"
    ALREADY_SHARED = "already_shared"
    FORBIDDEN = "forbidden"
    NOT_AVAILABLE = "not_available"
    RATE_LIMITED = "rate_limited"


@dataclass(frozen=True)
class ShareResult:
    status: ShareStatus
    post: TimelinePost | None = None


def parse_share_to_timeline_flag(value) -> bool:
    """Explicit true only. Omitted / 'false' / unknown → False (never bool(str))."""
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value == 1
    text = str(value).strip().lower()
    return text in _TRUE_VALUES


def product_has_timeline_share(product: Product) -> bool:
    return bool(getattr(product, "timeline_share_post_id", None))


def can_share_product_to_timeline(
    product: Product, viewer: AbstractBaseUser | None
) -> bool:
    return (
        viewer is not None
        and getattr(viewer, "is_authenticated", False)
        and product.seller_id == viewer.id
        and product.is_available
        and not product_has_timeline_share(product)
    )


def share_product_to_timeline(request: HttpRequest, product: Product) -> ShareResult:
    """Create at most one flea-share TimelinePost for this product.

    Caller must be authenticated. Rate-limit is consumed only when a new
    TimelinePost is created.
    """
    user = request.user
    if product.seller_id != user.id:
        return ShareResult(ShareStatus.FORBIDDEN)
    if product.status != Product.Status.AVAILABLE:
        return ShareResult(ShareStatus.NOT_AVAILABLE)

    with transaction.atomic():
        locked = Product.objects.select_for_update().get(pk=product.pk)
        if locked.timeline_share_post_id:
            return ShareResult(
                ShareStatus.ALREADY_SHARED,
                post=locked.timeline_share_post,
            )
        if not allow_timeline_post(user):
            return ShareResult(ShareStatus.RATE_LIMITED)

        course_name = (locked.course_name or "").strip()[:120] or None
        post = TimelinePost.objects.create(
            author=user,
            body=FLEA_TIMELINE_SHARE_BODY,
            course_name=course_name,
            professor_name=locked.professor_name or "",
            faculty=locked.faculty or get_user_faculty(user),
        )
        locked.timeline_share_post = post
        locked.save(update_fields=["timeline_share_post"])
        return ShareResult(ShareStatus.CREATED, post=post)


def maybe_share_product_on_exhibit(
    request: HttpRequest, product: Product
) -> ShareResult | None:
    """Optional share after Product exists. Failures do not roll back Product."""
    if not parse_share_to_timeline_flag(request.POST.get("share_to_timeline")):
        return None
    return share_product_to_timeline(request, product)
