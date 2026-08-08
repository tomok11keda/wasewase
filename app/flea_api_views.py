"""JSON API for React flea marketplace (Phase 5). Reuses marketplace + trade_chat services."""

from __future__ import annotations

import json
import logging

from django.contrib.auth.decorators import login_required
from django.db.utils import IntegrityError, OperationalError, ProgrammingError
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from .flea_api_services import (
    exhibit_meta_payload,
    list_flea_payload,
    serialize_chat_room,
    serialize_comment,
    serialize_product_card,
    serialize_product_detail,
    serialize_review,
)
from .forms import CommentForm, ProductExhibitForm, ReviewForm
from .marketplace_views import _room_messages_json, _serialize_room_message
from .models import (
    ChatRoom,
    Comment,
    Like,
    Message as ChatMessage,
    Notification,
    Product,
    Review,
    TimelinePost,
)
from .product_trade_schema_services import ensure_product_trade_schema
from .services import (
    build_product_share_timeline_body,
    can_access_chat_room,
    chat_room_link,
    get_reviewee,
    get_user_faculty,
    notify_seller,
)
from .trade_chat_inbox_services import mark_product_chat_room_read
from .trade_chat_services import (
    complete_handover_by_seller,
    confirm_negotiation_trade,
    start_instant_purchase,
    start_negotiation,
)
from .ugc_services import filter_visible_products

logger = logging.getLogger(__name__)


def _json_error(message: str, *, status: int = 400, **extra) -> JsonResponse:
    payload = {"ok": False, "error": message}
    payload.update(extra)
    return JsonResponse(payload, status=status)


def _parse_json(request: HttpRequest) -> dict:
    if request.content_type and "application/json" in request.content_type:
        try:
            return json.loads(request.body.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            return {}
    return {}


def _viewer(request: HttpRequest):
    return request.user if request.user.is_authenticated else None


def _get_visible_product(request: HttpRequest, pk: int) -> Product:
    ensure_product_trade_schema()
    try:
        return get_object_or_404(
            filter_visible_products(
                Product.objects.select_related(
                    "seller", "seller__profile", "buyer", "buyer__profile"
                ).prefetch_related("likes"),
                _viewer(request),
            ),
            pk=pk,
        )
    except (OperationalError, ProgrammingError) as exc:
        logger.warning("flea api product load failed: %s", exc)
        ensure_product_trade_schema()
        return get_object_or_404(
            filter_visible_products(
                Product.objects.select_related(
                    "seller", "seller__profile", "buyer", "buyer__profile"
                ).prefetch_related("likes"),
                _viewer(request),
            ),
            pk=pk,
        )


@require_GET
def api_v1_flea_list(request: HttpRequest) -> JsonResponse:
    return JsonResponse(list_flea_payload(request))


@require_http_methods(["GET", "POST"])
def api_v1_flea_products(request: HttpRequest) -> HttpResponse:
    if request.method == "GET":
        return JsonResponse(exhibit_meta_payload())
    return api_v1_flea_product_create(request)


@login_required
@require_POST
def api_v1_flea_product_create(request: HttpRequest) -> HttpResponse:
    form = ProductExhibitForm(request.POST, request.FILES)
    if not form.is_valid():
        return _json_error(
            "validation_failed",
            status=400,
            errors=form.errors.get_json_data(),
        )
    product = form.save(commit=False)
    product.seller = request.user
    try:
        product.save()
    except Exception:
        logger.exception("EXHIBIT SAVE FAILED (api)")
        return _json_error("save_failed", status=500)
    product = Product.objects.select_related("seller", "seller__profile").get(
        pk=product.pk
    )
    return JsonResponse(
        {"ok": True, "product": serialize_product_card(product)},
        status=201,
    )


@require_GET
def api_v1_flea_product_detail(request: HttpRequest, pk: int) -> JsonResponse:
    product = _get_visible_product(request, pk)
    return JsonResponse(
        {"ok": True, "product": serialize_product_detail(product, _viewer(request))}
    )


@login_required
@require_POST
def api_v1_flea_product_like(request: HttpRequest, pk: int) -> JsonResponse:
    product = get_object_or_404(Product, pk=pk)
    like = Like.objects.filter(user=request.user, product=product).first()
    if like:
        like.delete()
        liked = False
    else:
        Like.objects.create(user=request.user, product=product)
        liked = True
        notify_seller(
            product,
            f"「{product.name}」にいいねがつきました。",
            actor_id=request.user.id,
        )
    return JsonResponse(
        {"ok": True, "liked": liked, "like_count": product.likes.count()}
    )


@require_POST
def api_v1_flea_product_comment(request: HttpRequest, pk: int) -> JsonResponse:
    product = _get_visible_product(request, pk)
    data = _parse_json(request)
    form = CommentForm(data if data else request.POST)
    if not form.is_valid():
        return _json_error(
            "validation_failed",
            status=400,
            errors=form.errors.get_json_data(),
        )
    comment = form.save(commit=False)
    comment.product = product
    if request.user.is_authenticated:
        comment.author = request.user
    comment.save()
    actor_id = request.user.id if request.user.is_authenticated else None
    notify_seller(
        product,
        f"「{product.name}」にコメントがつきました。",
        actor_id=actor_id,
    )
    comment = Comment.objects.select_related("author", "author__profile").get(
        pk=comment.pk
    )
    return JsonResponse(
        {"ok": True, "comment": serialize_comment(comment)},
        status=201,
    )


@login_required
@require_POST
def api_v1_flea_product_purchase(request: HttpRequest, pk: int) -> JsonResponse:
    product = get_object_or_404(Product, pk=pk)
    try:
        room = start_instant_purchase(product, request.user)
    except ValueError as exc:
        return _json_error(str(exc), status=400)
    notify_seller(
        product,
        f"「{product.name}」が即決購入されました。受け渡しチャットを確認してください。",
        actor_id=request.user.id,
    )
    return JsonResponse({"ok": True, "room_id": room.pk})


@login_required
@require_POST
def api_v1_flea_product_chat_start(request: HttpRequest, pk: int) -> JsonResponse:
    product = get_object_or_404(Product.objects.select_related("seller"), pk=pk)
    if not product.seller_id or product.seller_id == request.user.id:
        return _json_error("own_product", status=400)
    try:
        room, created = start_negotiation(product, request.user)
    except ValueError as exc:
        return _json_error(str(exc), status=400)
    if created:
        notify_seller(
            product,
            f"「{product.name}」に値下げ交渉の問い合わせがありました。",
            actor_id=request.user.id,
        )
    return JsonResponse({"ok": True, "room_id": room.pk, "created": created})


@login_required
@require_http_methods(["DELETE", "POST"])
def api_v1_flea_product_delete(request: HttpRequest, pk: int) -> JsonResponse:
    product = get_object_or_404(Product, pk=pk)
    if product.seller_id != request.user.id:
        return _json_error("forbidden", status=403)
    product.delete()
    return JsonResponse({"ok": True})


@login_required
@require_POST
def api_v1_flea_product_share(request: HttpRequest, pk: int) -> JsonResponse:
    product = get_object_or_404(Product.objects.select_related("seller"), pk=pk)
    if product.seller_id != request.user.id:
        return _json_error("forbidden", status=403)
    if product.status != Product.Status.AVAILABLE:
        return _json_error("not_available", status=400)
    detail_url = request.build_absolute_uri(
        reverse("product_detail", kwargs={"pk": product.pk})
    )
    body = build_product_share_timeline_body(product, detail_url)
    course_name = (product.course_name or "").strip()[:120] or None
    TimelinePost.objects.create(
        author=request.user,
        body=body,
        course_name=course_name,
        professor_name=product.professor_name or "",
        faculty=product.faculty or get_user_faculty(request.user),
    )
    return JsonResponse({"ok": True})


@login_required
@require_POST
def api_v1_flea_product_review(request: HttpRequest, pk: int) -> JsonResponse:
    product = get_object_or_404(
        Product.objects.select_related("seller", "buyer"), pk=pk
    )
    if not product.is_sold or not product.buyer_id:
        return _json_error("not_sold", status=400)
    reviewee = get_reviewee(product, request.user)
    if not reviewee:
        return _json_error("no_permission", status=403)
    if Review.objects.filter(product=product, reviewer=request.user).exists():
        return _json_error("already_reviewed", status=400)
    data = _parse_json(request)
    form = ReviewForm(data if data else request.POST)
    if not form.is_valid():
        return _json_error(
            "validation_failed",
            status=400,
            errors=form.errors.get_json_data(),
        )
    review = Review.objects.create(
        product=product,
        reviewer=request.user,
        reviewee=reviewee,
        rating=form.cleaned_data["rating"],
        comment=form.cleaned_data["comment"],
    )
    review = Review.objects.select_related(
        "reviewer", "reviewer__profile", "reviewee", "reviewee__profile"
    ).get(pk=review.pk)
    return JsonResponse({"ok": True, "review": serialize_review(review)}, status=201)


@login_required
@require_GET
def api_v1_flea_chat_detail(request: HttpRequest, room_pk: int) -> JsonResponse:
    room = get_object_or_404(
        ChatRoom.objects.select_related(
            "product",
            "product__seller",
            "product__seller__profile",
            "buyer",
            "buyer__profile",
        ),
        pk=room_pk,
    )
    if not can_access_chat_room(room, request.user):
        return _json_error("forbidden", status=403)
    mark_product_chat_room_read(room, request.user)
    return JsonResponse({"ok": True, "room": serialize_chat_room(room, request.user)})


@login_required
@require_GET
def api_v1_flea_chat_messages(request: HttpRequest, room_pk: int) -> JsonResponse:
    room = get_object_or_404(
        ChatRoom.objects.select_related("product", "product__seller", "buyer"),
        pk=room_pk,
    )
    if not can_access_chat_room(room, request.user):
        return JsonResponse({"error": "forbidden"}, status=403)
    return _room_messages_json(request, room.messages)


@login_required
@require_POST
def api_v1_flea_chat_send(request: HttpRequest, room_pk: int) -> JsonResponse:
    room = get_object_or_404(
        ChatRoom.objects.select_related("product", "product__seller", "buyer"),
        pk=room_pk,
    )
    if not can_access_chat_room(room, request.user):
        return _json_error("forbidden", status=403)
    data = _parse_json(request)
    body = str(data.get("body") if data else request.POST.get("body", "")).strip()
    if not body:
        return _json_error("empty", status=400)
    if len(body) > 500:
        return _json_error("too_long", status=400)
    if room.product.is_sold or room.is_closed:
        return _json_error("closed", status=400)
    message = ChatMessage.objects.create(
        chat_room=room,
        sender=request.user,
        body=body,
    )
    room.save(update_fields=["updated_at"])
    recipient = (
        room.buyer
        if request.user.id == room.product.seller_id
        else room.product.seller
    )
    if recipient:
        Notification.objects.create(
            recipient=recipient,
            message=f"「{room.product.name}」のチャット: {body[:40]}",
            link=chat_room_link(room),
        )
    return JsonResponse(
        {
            "ok": True,
            "message": _serialize_room_message(message, request.user.id),
        },
        status=201,
    )


@login_required
@require_POST
def api_v1_flea_chat_confirm(request: HttpRequest, room_pk: int) -> JsonResponse:
    room = get_object_or_404(
        ChatRoom.objects.select_related("product", "product__seller", "buyer"),
        pk=room_pk,
    )
    try:
        room = confirm_negotiation_trade(room, request.user)
    except ValueError as exc:
        return _json_error(str(exc), status=400)
    if room.buyer_id:
        Notification.objects.create(
            recipient_id=room.buyer_id,
            message=f"「{room.product.name}」の取引が確定しました。受け渡しを相談しましょう。",
            link=chat_room_link(room),
        )
    room = ChatRoom.objects.select_related(
        "product",
        "product__seller",
        "product__seller__profile",
        "buyer",
        "buyer__profile",
    ).get(pk=room.pk)
    return JsonResponse(
        {
            "ok": True,
            "deal_status": room.deal_status,
            "product_status": room.product.status,
            "room": serialize_chat_room(room, request.user),
        }
    )


@login_required
@require_POST
def api_v1_flea_chat_handover(request: HttpRequest, room_pk: int) -> JsonResponse:
    ensure_product_trade_schema()
    room = get_object_or_404(
        ChatRoom.objects.select_related("product", "product__seller", "buyer"),
        pk=room_pk,
    )
    try:
        product = complete_handover_by_seller(room, request.user)
    except ValueError as exc:
        return _json_error(str(exc), status=400)
    except (IntegrityError, OperationalError, ProgrammingError) as exc:
        logger.exception("flea api handover schema/db error: %s", exc)
        ensure_product_trade_schema()
        try:
            product = complete_handover_by_seller(room, request.user)
        except Exception:
            logger.exception("flea api handover retry failed")
            return _json_error("save_failed", status=500)
    if product.buyer_id:
        Notification.objects.create(
            recipient_id=product.buyer_id,
            message=f"「{product.name}」の受け渡しが完了しました。",
            link=chat_room_link(room),
        )
    room = ChatRoom.objects.select_related(
        "product",
        "product__seller",
        "product__seller__profile",
        "buyer",
        "buyer__profile",
    ).get(pk=room.pk)
    return JsonResponse(
        {
            "ok": True,
            "product_status": product.status,
            "room": serialize_chat_room(room, request.user),
        }
    )
