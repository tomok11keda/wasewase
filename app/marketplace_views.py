"""フリマ（マーケットプレイス）向けビュー。"""
import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.db.utils import IntegrityError, OperationalError, ProgrammingError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from .constants import FACULTY_CHOICES, FLEA_ORDER_CHOICES, HANDOVER_CAMPUS_CHOICES, TRADE_LOCATION_PRESETS
from .forms import CommentForm, ProductExhibitForm, ReviewForm
from .models import (
    ChatRoom,
    Like,
    Message as ChatMessage,
    Notification,
    Product,
    Review,
    TimelinePost,
    TradeMessage,
)
from .services import (
    build_flea_url,
    build_product_share_timeline_body,
    can_access_chat_room,
    chat_room_link,
    get_following_user_ids,
    get_reviewee,
    get_user_faculty,
    is_trade_participant,
    notify_seller,
    prioritize_same_faculty,
    user_display_name,
)
from .product_trade_schema_services import ensure_product_trade_schema
from .trade_chat_services import (
    complete_handover_by_seller,
    confirm_negotiation_trade,
    get_confirmed_room_for_product,
    start_instant_purchase,
    start_negotiation,
)
from .trade_chat_inbox_services import (
    mark_product_chat_room_read,
    product_thumbnail_url,
    trade_status_label,
)
from .ugc_services import (
    filter_visible_comments,
    filter_visible_products,
    get_visible_product_or_404,
)

logger = logging.getLogger(__name__)

_CAMPUS_VALUES = {value for value, _ in HANDOVER_CAMPUS_CHOICES}
_ORDER_VALUES = {value for value, _ in FLEA_ORDER_CHOICES if value}


def _serialize_room_message(message, current_user_id):
    created = timezone.localtime(message.created_at)
    is_system = bool(getattr(message, "is_system", False)) or message.sender_id is None
    return {
        "id": message.pk,
        "sender_id": message.sender_id,
        "sender_name": (
            "システム" if is_system else user_display_name(message.sender)
        ),
        "body": message.body,
        "created_at": created.strftime("%m/%d %H:%M"),
        "is_mine": (not is_system) and message.sender_id == current_user_id,
        "is_system": is_system,
    }


def _room_messages_json(request, message_queryset):
    after = request.GET.get("after", "").strip()
    messages_qs = message_queryset.select_related("sender").order_by("created_at")
    if after.isdigit():
        messages_qs = messages_qs.filter(pk__gt=int(after))
    latest_id = (
        message_queryset.order_by("-pk").values_list("pk", flat=True).first() or 0
    )
    return JsonResponse(
        {
            "messages": [
                _serialize_room_message(message, request.user.id)
                for message in messages_qs
            ],
            "latest_id": latest_id,
        }
    )


def flea_index(request):
    ensure_product_trade_schema()
    feed_scope = request.GET.get("feed", "all").strip().lower()
    if feed_scope not in ("all", "following"):
        feed_scope = "all"
    feed_following_unauthenticated = (
        feed_scope == "following" and not request.user.is_authenticated
    )
    query = request.GET.get("q", "").strip()
    user_faculty = get_user_faculty(request.user) if request.user.is_authenticated else ""
    faculty_values = {value for value, _ in FACULTY_CHOICES}
    active_faculty = request.GET.get("faculty", "").strip()
    if active_faculty not in faculty_values:
        active_faculty = ""

    active_campus = request.GET.get("campus", "").strip().lower()
    if active_campus not in _CAMPUS_VALUES:
        active_campus = ""

    active_order = request.GET.get("order", "").strip().lower()
    if active_order not in _ORDER_VALUES:
        active_order = ""

    faculty_tabs = [{"value": "", "label": "すべて"}] + [
        {
            "value": value,
            "label": label,
            "url": build_flea_url(
                feed_scope=feed_scope,
                query=query,
                active_faculty=value,
                active_campus=active_campus,
                active_order=active_order,
            ),
        }
        for value, label in FACULTY_CHOICES
    ]
    for tab in faculty_tabs:
        if "url" not in tab:
            tab["url"] = build_flea_url(
                feed_scope=feed_scope,
                query=query,
                active_faculty=tab["value"],
                active_campus=active_campus,
                active_order=active_order,
            )

    campus_tabs = [{"value": "", "label": "すべて"}] + [
        {
            "value": value,
            "label": label,
            "url": build_flea_url(
                feed_scope=feed_scope,
                query=query,
                active_faculty=active_faculty,
                active_campus=value,
                active_order=active_order,
            ),
        }
        for value, label in HANDOVER_CAMPUS_CHOICES
    ]

    order_options = [
        {
            "value": value,
            "label": label,
            "url": build_flea_url(
                feed_scope=feed_scope,
                query=query,
                active_faculty=active_faculty,
                active_campus=active_campus,
                active_order=value,
            ),
        }
        for value, label in FLEA_ORDER_CHOICES
    ]

    try:
        products = filter_visible_products(
            Product.objects.select_related("seller", "seller__profile").all(),
            request.user if request.user.is_authenticated else None,
        )
        if active_faculty:
            products = products.filter(faculty=active_faculty)
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
        # 遅延評価の失敗をビュー内で捕捉するため一度触る
        products = list(products)
    except (OperationalError, ProgrammingError) as exc:
        logger.warning("flea_index product query failed (retry after schema repair): %s", exc)
        ensure_product_trade_schema()
        products = list(
            filter_visible_products(
                Product.objects.select_related("seller", "seller__profile").all(),
                request.user if request.user.is_authenticated else None,
            ).order_by("-created_at")
        )

    active_campus_label = dict(HANDOVER_CAMPUS_CHOICES).get(active_campus, "")
    active_order_label = dict(FLEA_ORDER_CHOICES).get(active_order, "おすすめ順")

    return render(
        request,
        "flea_index.html",
        {
            "products": products,
            "query": query,
            "user_faculty": user_faculty,
            "faculty_tabs": faculty_tabs,
            "active_faculty": active_faculty,
            "campus_tabs": campus_tabs,
            "active_campus": active_campus,
            "active_campus_label": active_campus_label,
            "order_options": order_options,
            "active_order": active_order,
            "active_order_label": active_order_label,
            "feed_scope": feed_scope,
            "feed_following_unauthenticated": feed_following_unauthenticated,
            "feed_url_all": build_flea_url(
                feed_scope="all",
                query=query,
                active_faculty=active_faculty,
                active_campus=active_campus,
                active_order=active_order,
            ),
            "feed_url_following": build_flea_url(
                feed_scope="following",
                query=query,
                active_faculty=active_faculty,
                active_campus=active_campus,
                active_order=active_order,
            ),
            "nav_active": "flea",
            "exhibit_success": request.GET.get("exhibit_success") == "1",
        },
    )


def product_detail(request, pk):
    ensure_product_trade_schema()
    try:
        product = get_object_or_404(
            filter_visible_products(
                Product.objects.select_related(
                    "seller", "seller__profile", "buyer", "buyer__profile"
                ).prefetch_related("likes"),
                request.user if request.user.is_authenticated else None,
            ),
            pk=pk,
        )
    except (OperationalError, ProgrammingError) as exc:
        logger.warning("product_detail failed (retry after schema repair): %s", exc)
        ensure_product_trade_schema()
        product = get_object_or_404(
            filter_visible_products(
                Product.objects.select_related(
                    "seller", "seller__profile", "buyer", "buyer__profile"
                ).prefetch_related("likes"),
                request.user if request.user.is_authenticated else None,
            ),
            pk=pk,
        )
    comments = filter_visible_comments(
        product.comments.select_related("author"),
        request.user if request.user.is_authenticated else None,
    )
    like_count = product.likes.count()
    user_liked = False
    if request.user.is_authenticated:
        user_liked = product.likes.filter(user=request.user).exists()

    if request.method == "POST":
        form = CommentForm(request.POST)
        if form.is_valid():
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
            return redirect(reverse("product_detail", kwargs={"pk": pk}))
    else:
        form = CommentForm()

    can_purchase = (
        product.is_available
        and request.user.is_authenticated
        and product.seller_id != request.user.id
    )
    can_negotiate = can_purchase

    review_form = None
    can_review = False
    user_review = None
    partner_review = None
    review_partner = None

    if product.is_sold and product.buyer_id and request.user.is_authenticated:
        review_partner = get_reviewee(product, request.user)
        if review_partner:
            user_review = Review.objects.filter(
                product=product, reviewer=request.user
            ).first()
            partner_review = Review.objects.filter(
                product=product, reviewer=review_partner
            ).first()
            can_review = user_review is None
            if can_review:
                review_form = ReviewForm()

    show_trade_link = is_trade_participant(product, request.user)
    trade_chat_room = get_confirmed_room_for_product(product) if show_trade_link else None
    can_share_to_timeline = (
        request.user.is_authenticated
        and product.seller_id == request.user.id
        and product.is_available
    )

    user_chat_room = None
    seller_chat_rooms = []
    can_contact_seller = False
    if request.user.is_authenticated and product.seller_id:
        if product.seller_id == request.user.id:
            seller_chat_rooms = list(
                ChatRoom.objects.filter(product=product)
                .exclude(deal_status=ChatRoom.DealStatus.CLOSED)
                .select_related("buyer")
                .order_by("-updated_at")
            )
        elif product.seller_id != request.user.id:
            user_chat_room = ChatRoom.objects.filter(
                product=product, buyer=request.user
            ).first()
            can_contact_seller = product.is_available or (
                user_chat_room is not None
                and user_chat_room.deal_status != ChatRoom.DealStatus.CLOSED
            )

    return render(
        request,
        "product_detail.html",
        {
            "product": product,
            "comments": comments,
            "form": form,
            "like_count": like_count,
            "user_liked": user_liked,
            "can_purchase": can_purchase,
            "can_negotiate": can_negotiate,
            "review_form": review_form,
            "can_review": can_review,
            "user_review": user_review,
            "partner_review": partner_review,
            "review_partner": review_partner,
            "show_trade_link": show_trade_link,
            "trade_chat_room": trade_chat_room,
            "can_share_to_timeline": can_share_to_timeline,
            "can_contact_seller": can_contact_seller,
            "user_chat_room": user_chat_room,
            "seller_chat_rooms": seller_chat_rooms,
        },
    )


@login_required
@require_POST
def start_product_chat(request, pk):
    """値下げ交渉: 商品専用チャットを開始（ステータスは available のまま）。"""
    product = get_visible_product_or_404(
        request.user if request.user.is_authenticated else None,
        pk,
    )

    if not product.seller_id or product.seller_id == request.user.id:
        messages.error(request, "出品者以外のユーザーのみチャットを開始できます。")
        return redirect(reverse("product_detail", kwargs={"pk": pk}))

    try:
        room, created = start_negotiation(product, request.user)
    except ValueError as exc:
        code = str(exc)
        if code == "sold":
            messages.error(request, "売り切れの商品には新しい交渉を開始できません。")
        elif code == "pending":
            messages.error(request, "取引中の商品には新しい交渉を開始できません。")
        else:
            messages.error(request, "交渉を開始できません。")
        return redirect(reverse("product_detail", kwargs={"pk": pk}))

    if created:
        notify_seller(
            product,
            f"「{product.name}」に値下げ交渉の問い合わせがありました。",
            actor_id=request.user.id,
        )
        messages.success(request, "値下げ交渉のチャットを開始しました。")
    return redirect(reverse("chat_room", kwargs={"room_pk": room.pk}))


@login_required
def chat_room(request, room_pk):
    room = get_object_or_404(
        ChatRoom.objects.select_related(
            "product", "product__seller", "buyer"
        ).prefetch_related("messages__sender"),
        pk=room_pk,
    )
    if not can_access_chat_room(room, request.user):
        messages.error(request, "このチャットルームにはアクセスできません。")
        return redirect(reverse("product_detail", kwargs={"pk": room.product_id}))

    mark_product_chat_room_read(room, request.user)

    partner = (
        room.buyer
        if request.user.id == room.product.seller_id
        else room.product.seller
    )
    chat_messages = room.messages.select_related("sender")
    latest_message_id = (
        chat_messages.order_by("-pk").values_list("pk", flat=True).first() or 0
    )
    is_seller = request.user.id == room.product.seller_id
    can_confirm_trade = (
        is_seller
        and room.is_negotiating
        and room.product.is_available
    )
    can_complete_handover = (
        is_seller
        and room.is_confirmed
        and room.product.is_pending
        and room.product.buyer_id == room.buyer_id
    )

    return render(
        request,
        "chat_room.html",
        {
            "room": room,
            "product": room.product,
            "partner": partner,
            "chat_messages": chat_messages,
            "latest_message_id": latest_message_id,
            "messages_poll_url": reverse(
                "chat_room_messages", kwargs={"room_pk": room.pk}
            ),
            "can_confirm_trade": can_confirm_trade,
            "can_complete_handover": can_complete_handover,
            "is_seller": is_seller,
            "product_thumbnail_url": product_thumbnail_url(room.product),
            "trade_status_label": trade_status_label(room, room.product),
            "inbox_back_url": f"{reverse('user_dm_inbox')}?tab=trade",
        },
    )


@login_required
@require_POST
def send_chat_message(request, room_pk):
    room = get_object_or_404(
        ChatRoom.objects.select_related("product", "product__seller", "buyer"),
        pk=room_pk,
    )
    if not can_access_chat_room(room, request.user):
        messages.error(request, "このチャットルームにはアクセスできません。")
        return redirect(reverse("product_detail", kwargs={"pk": room.product_id}))

    body = request.POST.get("body", "").strip()
    if not body:
        messages.error(request, "メッセージを入力してください。")
        return redirect(reverse("chat_room", kwargs={"room_pk": room.pk}))

    if len(body) > 500:
        messages.error(request, "メッセージが長すぎます（500文字以内）。")
        return redirect(reverse("chat_room", kwargs={"room_pk": room.pk}))

    if room.product.is_sold or room.is_closed:
        messages.info(request, "このチャットでは新しいメッセージを送信できません。")
        return redirect(reverse("chat_room", kwargs={"room_pk": room.pk}))

    ChatMessage.objects.create(
        chat_room=room,
        sender=request.user,
        body=body,
    )
    room.save(update_fields=["updated_at"])

    if request.user.id == room.product.seller_id:
        recipient = room.buyer
    else:
        recipient = room.product.seller

    if recipient:
        Notification.objects.create(
            recipient=recipient,
            message=f"「{room.product.name}」のチャット: {body[:40]}",
            link=chat_room_link(room),
        )

    return redirect(reverse("chat_room", kwargs={"room_pk": room.pk}))


@login_required
@require_POST
def confirm_product_trade(request, room_pk):
    """出品者が交渉チャットで「取引開始」→ pending。"""
    room = get_object_or_404(
        ChatRoom.objects.select_related("product", "product__seller", "buyer"),
        pk=room_pk,
    )
    try:
        room = confirm_negotiation_trade(room, request.user)
    except ValueError as exc:
        code = str(exc)
        if code == "not_seller":
            messages.error(request, "出品者のみ取引を開始できます。")
        elif code == "not_negotiating":
            messages.warning(request, "このチャットはすでに取引確定済みか終了しています。")
        elif code == "not_available":
            messages.warning(request, "この商品はすでに取引中か売り切れです。")
        else:
            messages.error(request, "取引を開始できません。")
        return redirect(reverse("chat_room", kwargs={"room_pk": room.pk}))

    if room.buyer_id:
        Notification.objects.create(
            recipient_id=room.buyer_id,
            message=f"「{room.product.name}」の取引が確定しました。受け渡しを相談しましょう。",
            link=chat_room_link(room),
        )
    messages.success(request, "取引を開始しました。受け渡し場所と時間を相談してください。")
    return redirect(reverse("chat_room", kwargs={"room_pk": room.pk}))


@login_required
@require_POST
def complete_product_handover(request, room_pk):
    """出品者が「受け渡し完了」→ sold。"""
    # 本番 SQLite で is_system / sender_id NULL が未修復だとシステムメッセージ作成で 500 になる
    ensure_product_trade_schema()
    room = get_object_or_404(
        ChatRoom.objects.select_related("product", "product__seller", "buyer"),
        pk=room_pk,
    )
    try:
        product = complete_handover_by_seller(room, request.user)
    except ValueError as exc:
        code = str(exc)
        if code == "not_seller":
            messages.error(request, "出品者のみ受け渡し完了にできます。")
        elif code == "already_sold":
            messages.info(request, "この商品はすでに売り切れです。")
        else:
            messages.error(request, "受け渡し完了にできません。")
        return redirect(reverse("chat_room", kwargs={"room_pk": room.pk}))
    except (IntegrityError, OperationalError, ProgrammingError) as exc:
        logger.exception("complete_product_handover schema/db error: %s", exc)
        ensure_product_trade_schema()
        try:
            product = complete_handover_by_seller(room, request.user)
        except Exception:
            logger.exception("complete_product_handover retry failed")
            messages.error(
                request,
                "受け渡し完了の保存に失敗しました。時間をおいて再度お試しください。",
            )
            return redirect(reverse("chat_room", kwargs={"room_pk": room.pk}))

    if product.buyer_id:
        try:
            Notification.objects.create(
                recipient_id=product.buyer_id,
                message=f"「{product.name}」の受け渡しが完了しました。",
                link=chat_room_link(room),
            )
        except Exception:
            logger.exception(
                "complete_product_handover notification failed product=%s",
                product.pk,
            )
    messages.success(request, "受け渡し完了として売り切れにしました。")
    return redirect(reverse("chat_room", kwargs={"room_pk": room.pk}))


@login_required
@require_GET
def chat_room_messages(request, room_pk):
    room = get_object_or_404(
        ChatRoom.objects.select_related("product", "product__seller", "buyer"),
        pk=room_pk,
    )
    if not can_access_chat_room(room, request.user):
        return JsonResponse({"error": "forbidden"}, status=403)

    return _room_messages_json(request, room.messages)


@login_required
@require_POST
def share_product_to_timeline(request, pk):
    product = get_object_or_404(Product.objects.select_related("seller"), pk=pk)
    if product.seller_id != request.user.id:
        messages.error(request, "自分の出品のみスレッドにシェアできます。")
        return redirect(reverse("product_detail", kwargs={"pk": pk}))

    if product.status != Product.Status.AVAILABLE:
        messages.error(request, "出品中の商品のみシェアできます。")
        return redirect(reverse("product_detail", kwargs={"pk": pk}))

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
    messages.success(request, "スレッドにシェアしました！")
    return redirect(reverse("product_detail", kwargs={"pk": pk}))


@login_required
@require_POST
def submit_review(request, pk):
    product = get_object_or_404(
        Product.objects.select_related("seller", "buyer"), pk=pk
    )

    if not product.is_sold or not product.buyer_id:
        messages.error(request, "この商品はまだ取引完了していません。")
        return redirect(reverse("product_detail", kwargs={"pk": pk}))

    reviewee = get_reviewee(product, request.user)
    if not reviewee:
        messages.error(request, "この取引の評価権限がありません。")
        return redirect(reverse("product_detail", kwargs={"pk": pk}))

    if Review.objects.filter(product=product, reviewer=request.user).exists():
        messages.warning(request, "すでに評価済みです。")
        return redirect(reverse("product_detail", kwargs={"pk": pk}))

    form = ReviewForm(request.POST)
    if form.is_valid():
        Review.objects.create(
            product=product,
            reviewer=request.user,
            reviewee=reviewee,
            rating=form.cleaned_data["rating"],
            comment=form.cleaned_data["comment"],
        )
        messages.success(
            request,
            f"{reviewee.username} さんへの評価を投稿しました。",
        )
    else:
        messages.error(request, "評価の送信に失敗しました。")

    return redirect(reverse("product_detail", kwargs={"pk": pk}))


@login_required
@require_POST
def toggle_like(request, pk):
    product = get_visible_product_or_404(
        request.user if request.user.is_authenticated else None,
        pk,
    )
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

    like_count = product.likes.count()

    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return JsonResponse({"liked": liked, "like_count": like_count})

    return redirect(reverse("product_detail", kwargs={"pk": pk}))


@login_required
@require_POST
def purchase_product(request, pk):
    """即決購入: 専用チャット作成 + pending + 他交渉へ終了通知。"""
    product = get_visible_product_or_404(
        request.user if request.user.is_authenticated else None,
        pk,
    )

    try:
        room = start_instant_purchase(product, request.user)
    except ValueError as exc:
        code = str(exc)
        if code == "sold":
            messages.warning(request, "この商品はすでに売却済みです。")
        elif code == "pending":
            messages.warning(request, "この商品はすでに取引中です。")
        elif code == "own_product":
            messages.error(request, "自分の商品は購入できません。")
        else:
            messages.error(request, "購入できません。")
        return redirect(reverse("product_detail", kwargs={"pk": pk}))

    notify_seller(
        product,
        f"「{product.name}」が即決購入されました。受け渡しチャットを確認してください。",
        actor_id=request.user.id,
    )
    messages.success(
        request,
        "即決購入が成立しました。受け渡し場所と時間を相談してください。",
    )
    return redirect(reverse("chat_room", kwargs={"room_pk": room.pk}))


@login_required
def product_trade(request, pk):
    """旧取引ページ。確定済みチャットがあればそちらへ誘導。"""
    product = get_object_or_404(
        Product.objects.select_related("seller", "buyer"), pk=pk
    )
    if not is_trade_participant(product, request.user):
        messages.error(request, "この取引ページにはアクセスできません。")
        return redirect(reverse("product_detail", kwargs={"pk": pk}))

    confirmed_room = get_confirmed_room_for_product(product)
    if confirmed_room:
        return redirect(reverse("chat_room", kwargs={"room_pk": confirmed_room.pk}))

    partner = product.buyer if request.user.id == product.seller_id else product.seller
    trade_messages = product.trade_messages.select_related("sender")
    user_completed = (
        product.seller_trade_completed
        if request.user.id == product.seller_id
        else product.buyer_trade_completed
    )

    return render(
        request,
        "product_trade.html",
        {
            "product": product,
            "partner": partner,
            "trade_messages": trade_messages,
            "location_presets": TRADE_LOCATION_PRESETS,
            "user_completed": user_completed,
        },
    )


@login_required
@require_POST
def send_trade_message(request, pk):
    product = get_object_or_404(
        Product.objects.select_related("seller", "buyer"), pk=pk
    )

    if not is_trade_participant(product, request.user):
        messages.error(request, "この取引のチャットに参加できません。")
        return redirect(reverse("product_detail", kwargs={"pk": pk}))

    if product.is_sold:
        messages.info(request, "完了済みの取引にはメッセージを送信できません。")
        return redirect(reverse("product_trade", kwargs={"pk": pk}))

    body = request.POST.get("body", "").strip()
    is_preset = request.POST.get("is_preset") == "1"

    if is_preset and body not in TRADE_LOCATION_PRESETS:
        messages.error(request, "無効な定型文です。")
        return redirect(reverse("product_trade", kwargs={"pk": pk}))

    if not body:
        messages.error(request, "メッセージを入力してください。")
        return redirect(reverse("product_trade", kwargs={"pk": pk}))

    if len(body) > 200:
        messages.error(request, "メッセージが長すぎます。")
        return redirect(reverse("product_trade", kwargs={"pk": pk}))

    TradeMessage.objects.create(
        product=product,
        sender=request.user,
        body=body,
        is_preset=is_preset,
    )

    partner = product.buyer if request.user.id == product.seller_id else product.seller
    if partner:
        from .spa_canonical import product_detail_url

        Notification.objects.create(
            recipient=partner,
            message=f"「{product.name}」の手渡しチャット: {body}",
            link=product_detail_url(pk),
        )

    return redirect(reverse("product_trade", kwargs={"pk": pk}))


@login_required
@require_POST
def complete_trade(request, pk):
    """旧 dual-confirm。確定チャットがあれば出品者の受け渡し完了に委譲。"""
    product = get_object_or_404(
        Product.objects.select_related("seller", "buyer"), pk=pk
    )
    if not is_trade_participant(product, request.user):
        messages.error(request, "この取引を完了する権限がありません。")
        return redirect(reverse("product_detail", kwargs={"pk": pk}))

    confirmed_room = get_confirmed_room_for_product(product)
    if confirmed_room and request.user.id == product.seller_id:
        return complete_product_handover(request, confirmed_room.pk)
    if confirmed_room:
        messages.info(
            request,
            "受け渡し完了は出品者がチャットから行います。",
        )
        return redirect(reverse("chat_room", kwargs={"room_pk": confirmed_room.pk}))

    if product.is_sold:
        messages.info(request, "この取引はすでに完了しています。")
        return redirect(reverse("product_trade", kwargs={"pk": pk}))

    if request.user.id == product.seller_id:
        product.seller_trade_completed = True
    else:
        product.buyer_trade_completed = True

    partner = product.buyer if request.user.id == product.seller_id else product.seller
    update_fields = ["seller_trade_completed", "buyer_trade_completed"]
    from .spa_canonical import product_detail_url

    if product.seller_trade_completed and product.buyer_trade_completed:
        product.status = Product.Status.SOLD
        update_fields.append("status")
        messages.success(request, "双方の確認がそろいました。取引を完了しました。")
        if partner:
            Notification.objects.create(
                recipient=partner,
                message=f"「{product.name}」の取引が完了しました。",
                link=product_detail_url(pk),
            )
    else:
        messages.success(request, "取引完了の確認を送信しました。相手の確認を待っています。")
        if partner:
            Notification.objects.create(
                recipient=partner,
                message=f"{request.user.username}さんが「{product.name}」の取引完了を確認しました。",
                link=product_detail_url(pk),
            )

    product.save(update_fields=update_fields)
    return redirect(reverse("product_trade", kwargs={"pk": pk}))


@login_required
def exhibit(request):
    if request.method == "POST":
        form = ProductExhibitForm(request.POST, request.FILES)
        if form.is_valid():
            product = form.save(commit=False)
            product.seller = request.user
            try:
                product.save()
            except Exception:
                logger.exception("EXHIBIT SAVE FAILED")
                messages.error(request, "出品の保存に失敗しました。時間をおいて再度お試しください。")
                return render(request, "exhibit.html", {"form": form, "nav_active": "flea"})
            return redirect(f"{reverse('flea_index')}?exhibit_success=1")
    else:
        form = ProductExhibitForm()

    return render(request, "exhibit.html", {"form": form, "nav_active": "flea"})


@login_required
@require_POST
def delete_product(request, pk):
    product = get_object_or_404(Product, pk=pk)
    if product.seller_id != request.user.id:
        messages.error(request, "この商品を削除する権限がありません。")
        return redirect(reverse("product_detail", kwargs={"pk": pk}))

    product.delete()
    messages.success(request, "商品を削除しました。")
    return redirect(reverse("flea_index"))
