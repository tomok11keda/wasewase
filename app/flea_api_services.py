"""Flea JSON helpers — serialize + list wrappers over marketplace logic."""

from __future__ import annotations

import logging
from typing import Any

from django.contrib.auth.models import AbstractBaseUser
from django.db.models import Q
from django.db.utils import OperationalError, ProgrammingError
from django.http import HttpRequest
from django.utils.timesince import timesince

from .constants import FACULTY_CHOICES, FLEA_ORDER_CHOICES, HANDOVER_CAMPUS_CHOICES
from .models import ChatRoom, Comment, Product, Review
from .product_trade_schema_services import ensure_product_trade_schema
from .services import (
    get_following_user_ids,
    get_reviewee,
    get_user_faculty,
    is_trade_participant,
    prioritize_same_faculty,
)
from .timeline_api_services import serialize_author
from .trade_chat_inbox_services import product_thumbnail_url, trade_status_label
from .trade_chat_services import get_confirmed_room_for_product
from .ugc_services import filter_visible_comments, filter_visible_products

logger = logging.getLogger(__name__)

_CAMPUS_VALUES = {value for value, _ in HANDOVER_CAMPUS_CHOICES}
_ORDER_VALUES = {value for value, _ in FLEA_ORDER_CHOICES if value}
_FACULTY_VALUES = {value for value, _ in FACULTY_CHOICES}


def serialize_product_card(product: Product) -> dict[str, Any]:
    return {
        "id": product.pk,
        "name": product.name,
        "price": product.price,
        "status": product.status,
        "is_sold": product.is_sold,
        "is_pending": product.is_pending,
        "is_available": product.is_available,
        "faculty": product.faculty or "",
        "handover_campus": product.handover_campus or "",
        "handover_campus_label": product.get_handover_campus_display()
        if product.handover_campus
        else "",
        "course_name": product.course_name or "",
        "professor_name": product.professor_name or "",
        "created_at": product.created_at.isoformat(),
        "created_at_label": f"{timesince(product.created_at)}前",
        "image_url": product_thumbnail_url(product),
        "seller": serialize_author(product.seller),
    }


def serialize_comment(comment: Comment) -> dict[str, Any]:
    return {
        "id": comment.pk,
        "body": comment.body,
        "created_at": comment.created_at.isoformat(),
        "created_at_label": f"{timesince(comment.created_at)}前",
        "author": serialize_author(comment.author)
        if comment.author_id
        else {"id": None, "username": "", "display_name": "匿名", "avatar_url": "", "initial": "?"},
    }


def serialize_review(review: Review) -> dict[str, Any]:
    return {
        "id": review.pk,
        "rating": review.rating,
        "comment": review.comment or "",
        "reviewer": serialize_author(review.reviewer),
        "reviewee": serialize_author(review.reviewee),
    }


def serialize_product_detail(
    product: Product,
    viewer: AbstractBaseUser | None,
) -> dict[str, Any]:
    comments = filter_visible_comments(
        product.comments.select_related("author", "author__profile"),
        viewer,
    )
    like_count = product.likes.count()
    user_liked = False
    if viewer is not None and getattr(viewer, "is_authenticated", False):
        user_liked = product.likes.filter(user=viewer).exists()

    can_purchase = (
        product.is_available
        and viewer is not None
        and getattr(viewer, "is_authenticated", False)
        and product.seller_id != viewer.id
    )
    can_negotiate = can_purchase

    can_review = False
    user_review = None
    partner_review = None
    review_partner = None
    if (
        product.is_sold
        and product.buyer_id
        and viewer is not None
        and getattr(viewer, "is_authenticated", False)
    ):
        review_partner = get_reviewee(product, viewer)
        if review_partner:
            user_review = Review.objects.filter(
                product=product, reviewer=viewer
            ).first()
            partner_review = Review.objects.filter(
                product=product, reviewer=review_partner
            ).first()
            can_review = user_review is None

    show_trade_link = is_trade_participant(product, viewer) if viewer else False
    trade_chat_room = get_confirmed_room_for_product(product) if show_trade_link else None
    can_share_to_timeline = (
        viewer is not None
        and getattr(viewer, "is_authenticated", False)
        and product.seller_id == viewer.id
        and product.is_available
    )

    user_chat_room = None
    seller_chat_rooms: list[dict[str, Any]] = []
    can_contact_seller = False
    if viewer is not None and getattr(viewer, "is_authenticated", False) and product.seller_id:
        if product.seller_id == viewer.id:
            rooms = (
                ChatRoom.objects.filter(product=product)
                .exclude(deal_status=ChatRoom.DealStatus.CLOSED)
                .select_related("buyer", "buyer__profile")
                .order_by("-updated_at")
            )
            seller_chat_rooms = [
                {
                    "id": room.pk,
                    "deal_status": room.deal_status,
                    "buyer": serialize_author(room.buyer),
                }
                for room in rooms
            ]
        else:
            user_chat_room_obj = ChatRoom.objects.filter(
                product=product, buyer=viewer
            ).first()
            if user_chat_room_obj:
                user_chat_room = {
                    "id": user_chat_room_obj.pk,
                    "deal_status": user_chat_room_obj.deal_status,
                }
            can_contact_seller = product.is_available or (
                user_chat_room_obj is not None
                and user_chat_room_obj.deal_status != ChatRoom.DealStatus.CLOSED
            )

    can_delete = (
        viewer is not None
        and getattr(viewer, "is_authenticated", False)
        and product.seller_id == viewer.id
    )

    user_has_bookmarked = False
    if viewer is not None and getattr(viewer, "is_authenticated", False):
        from .bookmark_services import is_product_bookmarked

        user_has_bookmarked = is_product_bookmarked(viewer, product.pk)

    card = serialize_product_card(product)
    card.update(
        {
            "description": product.description or "",
            "like_count": like_count,
            "user_liked": user_liked,
            "user_has_bookmarked": user_has_bookmarked,
            "comments": [serialize_comment(c) for c in comments],
            "can_purchase": can_purchase,
            "can_negotiate": can_negotiate,
            "can_review": can_review,
            "can_delete": can_delete,
            "user_review": serialize_review(user_review) if user_review else None,
            "partner_review": serialize_review(partner_review)
            if partner_review
            else None,
            "review_partner": serialize_author(review_partner)
            if review_partner
            else None,
            "show_trade_link": show_trade_link,
            "trade_chat_room_id": trade_chat_room.pk if trade_chat_room else None,
            "can_share_to_timeline": can_share_to_timeline,
            "can_contact_seller": can_contact_seller,
            "user_chat_room": user_chat_room,
            "seller_chat_rooms": seller_chat_rooms,
            "buyer": serialize_author(product.buyer) if product.buyer_id else None,
        }
    )
    return card


def serialize_chat_room(
    room: ChatRoom,
    viewer: AbstractBaseUser,
) -> dict[str, Any]:
    product = room.product
    partner = (
        room.buyer
        if viewer.id == product.seller_id
        else product.seller
    )
    is_seller = viewer.id == product.seller_id
    can_confirm_trade = (
        is_seller and room.is_negotiating and product.is_available
    )
    can_complete_handover = (
        is_seller
        and room.is_confirmed
        and product.is_pending
        and product.buyer_id == room.buyer_id
    )
    return {
        "id": room.pk,
        "deal_status": room.deal_status,
        "is_seller": is_seller,
        "can_confirm_trade": can_confirm_trade,
        "can_complete_handover": can_complete_handover,
        "can_send_message": not (product.is_sold or room.is_closed),
        "trade_status_label": trade_status_label(room, product),
        "product": serialize_product_card(product),
        "partner": serialize_author(partner),
        "buyer": serialize_author(room.buyer),
        "product_thumbnail_url": product_thumbnail_url(product),
    }


def list_flea_payload(request: HttpRequest) -> dict[str, Any]:
    ensure_product_trade_schema()
    feed_scope = request.GET.get("feed", "all").strip().lower()
    if feed_scope not in ("all", "following"):
        feed_scope = "all"
    feed_following_unauthenticated = (
        feed_scope == "following" and not request.user.is_authenticated
    )
    query = request.GET.get("q", "").strip()
    user_faculty = (
        get_user_faculty(request.user) if request.user.is_authenticated else ""
    )

    active_faculty = request.GET.get("faculty", "").strip()
    if active_faculty not in _FACULTY_VALUES:
        active_faculty = ""

    active_campus = request.GET.get("campus", "").strip().lower()
    if active_campus not in _CAMPUS_VALUES:
        active_campus = ""

    active_order = request.GET.get("order", "").strip().lower()
    if active_order not in _ORDER_VALUES:
        active_order = ""

    faculty_tabs = [{"value": "", "label": "すべて"}] + [
        {"value": value, "label": label} for value, label in FACULTY_CHOICES
    ]
    campus_tabs = [{"value": "", "label": "すべて"}] + [
        {"value": value, "label": label}
        for value, label in HANDOVER_CAMPUS_CHOICES
    ]
    order_options = [
        {"value": value, "label": label} for value, label in FLEA_ORDER_CHOICES
    ]

    viewer = request.user if request.user.is_authenticated else None
    try:
        products = filter_visible_products(
            Product.objects.select_related("seller", "seller__profile").all(),
            viewer,
        )
        if active_faculty:
            # 出品者プロフィールの所属学部で絞り込む（商品.faculty も互換のため OR）。
            products = products.filter(
                Q(seller__profile__department=active_faculty)
                | Q(faculty=active_faculty)
            )
        if active_campus:
            products = products.filter(handover_campus=active_campus)
        if query:
            products = products.filter(
                Q(name__icontains=query)
                | Q(description__icontains=query)
                | Q(course_name__icontains=query)
                | Q(professor_name__icontains=query)
            )
        if feed_scope == "following":
            if request.user.is_authenticated:
                products = products.filter(
                    seller_id__in=get_following_user_ids(request.user)
                )
            else:
                products = products.none()

        if active_order == "price_low":
            products = products.order_by("price", "-created_at")
        elif active_order == "price_high":
            products = products.order_by("-price", "-created_at")
        elif active_order == "newest":
            products = products.order_by("-created_at")
        elif (
            feed_scope != "following"
            and request.user.is_authenticated
            and not active_faculty
            and not active_campus
        ):
            products = prioritize_same_faculty(products, request.user)
        else:
            products = products.order_by("-created_at")
        products = list(products)
    except (OperationalError, ProgrammingError) as exc:
        logger.warning(
            "flea api list failed (retry after schema repair): %s", exc
        )
        ensure_product_trade_schema()
        products = list(
            filter_visible_products(
                Product.objects.select_related("seller", "seller__profile").all(),
                viewer,
            ).order_by("-created_at")
        )

    return {
        "products": [serialize_product_card(p) for p in products],
        "feed": feed_scope,
        "q": query,
        "faculty": active_faculty,
        "campus": active_campus,
        "campus_label": dict(HANDOVER_CAMPUS_CHOICES).get(active_campus, ""),
        "order": active_order,
        "order_label": dict(FLEA_ORDER_CHOICES).get(active_order, "おすすめ順"),
        "feed_following_unauthenticated": feed_following_unauthenticated,
        "user_faculty": user_faculty,
        "faculty_tabs": faculty_tabs,
        "campus_tabs": campus_tabs,
        "order_options": order_options,
    }


def exhibit_meta_payload() -> dict[str, Any]:
    return {
        "faculty_choices": [
            {"value": "", "label": "学部を選択（任意）"},
            *[{"value": v, "label": l} for v, l in FACULTY_CHOICES],
        ],
        "campus_choices": [
            {"value": "", "label": "キャンパスを選択"},
            *[{"value": v, "label": l} for v, l in HANDOVER_CAMPUS_CHOICES],
        ],
    }
