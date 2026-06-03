import logging
import sys
import traceback
from urllib.parse import quote

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.db import transaction
from django.db.models import Case, Count, Exists, IntegerField, OuterRef, Q, Value, When
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from .constants import FACULTY_CHOICES, TRADE_LOCATION_PRESETS
from .dm_services import (
    can_access_dm_room,
    dm_room_link,
    find_dm_room,
    get_or_create_dm_room,
)
from .board_services import (
    GOD_USES_PER_MONTH,
    can_use_god_button,
    god_uses_remaining,
    notify_timeline_post_author,
    timeline_post_link,
)
from .forms import (
    CommentForm,
    EmailAuthenticationForm,
    ProductExhibitForm,
    AccountProfileForm,
    ReviewForm,
    SignUpForm,
    SignupOTPVerifyForm,
    TimelineCommentForm,
    TimelinePostForm,
)
from .models import (
    ChatRoom,
    Comment,
    Follow,
    GodButtonUse,
    Like,
    Message as ChatMessage,
    Notification,
    Product,
    Review,
    TimelinePost,
    TimelineLike,
    TradeMessage,
    UserDirectMessage,
    UserDirectMessageRoom,
    UserProfile,
)
from .otp_services import (
    EmailConfigurationError,
    SIGNUP_PENDING_SESSION_KEY,
    create_and_send_signup_otp,
    get_email_config_errors,
    verify_signup_otp,
)

logger = logging.getLogger(__name__)
from .services import (
    calc_sales_total,
    get_reviewee,
    build_home_url,
    build_product_share_timeline_body,
    build_search_url,
    can_access_chat_room,
    chat_room_link,
    search_products,
    search_timeline_posts,
    get_following_user_ids,
    get_profile_stats,
    get_user_faculty,
    is_following,
    get_user_rating_stats,
    is_trade_participant,
    notify_seller,
    prioritize_same_faculty,
)
User = get_user_model()


def index(request):
    tab = request.GET.get("tab", "flea")
    if tab not in ("flea", "board"):
        tab = "flea"

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
    faculty_tabs = [{"value": "", "label": "すべて"}] + [
        {"value": value, "label": label} for value, label in FACULTY_CHOICES
    ]

    products = Product.objects.none()
    timeline_posts = TimelinePost.objects.none()
    trending_posts = TimelinePost.objects.none()
    popular_tags = []
    active_tag = request.GET.get("tag", "").strip()
    timeline_form = None

    if tab == "board":
        timeline_posts = (
            TimelinePost.objects.select_related("author", "author__profile")
            .prefetch_related("comments__author")
        )
        if active_faculty:
            timeline_posts = timeline_posts.filter(faculty=active_faculty)
        if active_tag:
            timeline_posts = timeline_posts.filter(course_name=active_tag)
        if query:
            timeline_posts = timeline_posts.filter(
                Q(body__icontains=query)
                | Q(course_name__icontains=query)
                | Q(professor_name__icontains=query)
            )
        if feed_scope == "following":
            if request.user.is_authenticated:
                following_ids = get_following_user_ids(request.user)
                timeline_posts = timeline_posts.filter(author_id__in=following_ids)
            else:
                timeline_posts = timeline_posts.none()
        timeline_posts = timeline_posts.order_by("-created_at")
        if request.user.is_authenticated:
            timeline_posts = timeline_posts.annotate(
                user_has_liked=Exists(
                    TimelineLike.objects.filter(
                        timeline_post_id=OuterRef("pk"),
                        user_id=request.user.id,
                    )
                )
            )

        trending_posts = (
            TimelinePost.objects.select_related("author")
            .filter(god_count__gt=0)
            .order_by("-god_count", "-created_at")[:5]
        )

        popular_tags = list(
            TimelinePost.objects.exclude(course_name__isnull=True)
            .exclude(course_name="")
            .values_list("course_name", flat=True)
            .distinct()[:12]
        )

        if request.user.is_authenticated:
            timeline_form = TimelinePostForm(initial={"faculty": user_faculty})
    else:
        products = Product.objects.select_related("seller", "seller__profile").all()
        if active_faculty:
            products = products.filter(faculty=active_faculty)
        if query:
            products = products.filter(
                Q(name__icontains=query)
                | Q(description__icontains=query)
                | Q(course_name__icontains=query)
                | Q(professor_name__icontains=query)
            )
        if feed_scope == "following":
            if request.user.is_authenticated:
                following_ids = get_following_user_ids(request.user)
                products = products.filter(seller_id__in=following_ids)
            else:
                products = products.none()
        if (
            feed_scope != "following"
            and request.user.is_authenticated
            and not active_faculty
        ):
            products = prioritize_same_faculty(products, request.user)
        else:
            products = products.order_by("-created_at")

    god_remaining = (
        god_uses_remaining(request.user) if request.user.is_authenticated else 0
    )

    return render(
        request,
        "top.html",
        {
            "products": products,
            "timeline_posts": timeline_posts,
            "trending_posts": trending_posts,
            "popular_tags": popular_tags,
            "active_tag": active_tag,
            "timeline_form": timeline_form,
            "query": query,
            "user_faculty": user_faculty,
            "tab": tab,
            "faculty_tabs": faculty_tabs,
            "active_faculty": active_faculty,
            "god_remaining": god_remaining,
            "god_limit": GOD_USES_PER_MONTH,
            "can_god": can_use_god_button(request.user),
            "feed_scope": feed_scope,
            "feed_following_unauthenticated": feed_following_unauthenticated,
            "feed_url_all_flea": build_home_url(
                tab="flea",
                feed_scope="all",
                query=query,
                active_faculty=active_faculty,
                active_tag=active_tag,
            ),
            "feed_url_following_flea": build_home_url(
                tab="flea",
                feed_scope="following",
                query=query,
                active_faculty=active_faculty,
                active_tag=active_tag,
            ),
            "feed_url_all_board": build_home_url(
                tab="board",
                feed_scope="all",
                query=query,
                active_faculty=active_faculty,
                active_tag=active_tag,
            ),
            "feed_url_following_board": build_home_url(
                tab="board",
                feed_scope="following",
                query=query,
                active_faculty=active_faculty,
                active_tag=active_tag,
            ),
        },
    )


def search(request):
    """フリマ（Product）とタイムライン（TimelinePost）を横断検索。"""
    query = request.GET.get("q", "").strip()
    products = search_products(query) if query else Product.objects.none()
    timeline_posts = (
        search_timeline_posts(query).prefetch_related("comments__author")
        if query
        else TimelinePost.objects.none()
    )

    return render(
        request,
        "search.html",
        {
            "query": query,
            "products": products,
            "timeline_posts": timeline_posts,
            "product_count": products.count(),
            "timeline_count": timeline_posts.count(),
            "search_url": build_search_url(query),
        },
    )


def product_detail(request, pk):
    product = get_object_or_404(
        Product.objects.select_related(
            "seller", "seller__profile", "buyer", "buyer__profile"
        ).prefetch_related("likes"),
        pk=pk,
    )
    comments = product.comments.select_related("author")
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
        product.status == Product.Status.AVAILABLE
        and request.user.is_authenticated
        and product.seller_id != request.user.id
    )

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
    can_share_to_timeline = (
        request.user.is_authenticated
        and product.seller_id == request.user.id
        and product.status == Product.Status.AVAILABLE
    )

    user_chat_room = None
    seller_chat_rooms = []
    can_contact_seller = False
    if request.user.is_authenticated and product.seller_id:
        if product.seller_id == request.user.id:
            seller_chat_rooms = list(
                ChatRoom.objects.filter(product=product)
                .select_related("buyer")
                .order_by("-updated_at")
            )
        elif product.seller_id != request.user.id:
            user_chat_room = ChatRoom.objects.filter(
                product=product, buyer=request.user
            ).first()
            can_contact_seller = not product.is_sold or user_chat_room is not None

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
            "review_form": review_form,
            "can_review": can_review,
            "user_review": user_review,
            "partner_review": partner_review,
            "review_partner": review_partner,
            "show_trade_link": show_trade_link,
            "can_share_to_timeline": can_share_to_timeline,
            "can_contact_seller": can_contact_seller,
            "user_chat_room": user_chat_room,
            "seller_chat_rooms": seller_chat_rooms,
        },
    )


@login_required
@require_POST
def start_product_chat(request, pk):
    product = get_object_or_404(Product.objects.select_related("seller"), pk=pk)

    if not product.seller_id or product.seller_id == request.user.id:
        messages.error(request, "出品者以外のユーザーのみチャットを開始できます。")
        return redirect(reverse("product_detail", kwargs={"pk": pk}))

    if product.is_sold:
        messages.error(request, "売り切れの商品には新しいチャットを開始できません。")
        return redirect(reverse("product_detail", kwargs={"pk": pk}))

    room, created = ChatRoom.objects.get_or_create(
        product=product,
        buyer=request.user,
    )
    if created:
        notify_seller(
            product,
            f"「{product.name}」にチャットの問い合わせがありました。",
            actor_id=request.user.id,
        )
        messages.success(request, "出品者とのチャットを開始しました。")
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

    partner = (
        room.buyer
        if request.user.id == room.product.seller_id
        else room.product.seller
    )
    chat_messages = room.messages.select_related("sender")

    return render(
        request,
        "chat_room.html",
        {
            "room": room,
            "product": room.product,
            "partner": partner,
            "chat_messages": chat_messages,
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

    like_count = product.likes.count()

    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return JsonResponse({"liked": liked, "like_count": like_count})

    return redirect(reverse("product_detail", kwargs={"pk": pk}))


@login_required
@require_POST
def purchase_product(request, pk):
    product = get_object_or_404(Product, pk=pk)

    if product.is_sold:
        messages.warning(request, "この商品はすでに売却済みです。")
    elif product.is_trading:
        messages.warning(request, "この商品はすでに取引中です。")
    elif product.seller_id == request.user.id:
        messages.error(request, "自分の商品は購入できません。")
    else:
        product.status = Product.Status.TRADING
        product.buyer = request.user
        product.seller_trade_completed = False
        product.buyer_trade_completed = False
        product.save(
            update_fields=[
                "status",
                "buyer",
                "seller_trade_completed",
                "buyer_trade_completed",
            ]
        )
        notify_seller(
            product,
            f"「{product.name}」の購入希望がありました。受け渡しチャットを確認してください。",
            actor_id=request.user.id,
        )
        messages.success(
            request,
            "現地手渡しのチャットを開始しました。出品者と受け渡し場所などを相談しましょう。",
        )
        return redirect(reverse("product_trade", kwargs={"pk": pk}))

    return redirect(reverse("product_detail", kwargs={"pk": pk}))


@login_required
def product_trade(request, pk):
    product = get_object_or_404(
        Product.objects.select_related("seller", "buyer"), pk=pk
    )
    if not is_trade_participant(product, request.user):
        messages.error(request, "この取引ページにはアクセスできません。")
        return redirect(reverse("product_detail", kwargs={"pk": pk}))

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
        Notification.objects.create(
            recipient=partner,
            message=f"「{product.name}」の手渡しチャット: {body}",
            link=reverse("product_trade", kwargs={"pk": pk}),
        )

    return redirect(reverse("product_trade", kwargs={"pk": pk}))


@login_required
@require_POST
def complete_trade(request, pk):
    product = get_object_or_404(
        Product.objects.select_related("seller", "buyer"), pk=pk
    )
    if not is_trade_participant(product, request.user):
        messages.error(request, "この取引を完了する権限がありません。")
        return redirect(reverse("product_detail", kwargs={"pk": pk}))

    if product.is_sold:
        messages.info(request, "この取引はすでに完了しています。")
        return redirect(reverse("product_trade", kwargs={"pk": pk}))

    if request.user.id == product.seller_id:
        product.seller_trade_completed = True
    else:
        product.buyer_trade_completed = True

    partner = product.buyer if request.user.id == product.seller_id else product.seller
    update_fields = ["seller_trade_completed", "buyer_trade_completed"]
    if product.seller_trade_completed and product.buyer_trade_completed:
        product.status = Product.Status.SOLD_OUT
        update_fields.append("status")
        messages.success(request, "双方の確認がそろいました。取引を完了しました。")
        if partner:
            Notification.objects.create(
                recipient=partner,
                message=f"「{product.name}」の取引が完了しました。",
                link=reverse("product_trade", kwargs={"pk": pk}),
            )
    else:
        messages.success(request, "取引完了の確認を送信しました。相手の確認を待っています。")
        if partner:
            Notification.objects.create(
                recipient=partner,
                message=f"{request.user.username}さんが「{product.name}」の取引完了を確認しました。",
                link=reverse("product_trade", kwargs={"pk": pk}),
            )

    product.save(update_fields=update_fields)
    return redirect(reverse("product_trade", kwargs={"pk": pk}))


@login_required
def notifications(request):
    items = Notification.objects.filter(recipient=request.user)
    items.filter(is_read=False).update(is_read=True)

    return render(request, "notifications.html", {"notifications": items})


@login_required
def mypage_edit(request):
    profile, _ = UserProfile.objects.get_or_create(user=request.user)

    if request.method == "POST":
        form = AccountProfileForm(
            request.POST, instance=profile, user=request.user
        )
        if form.is_valid():
            form.save()
            messages.success(
                request,
                "ニックネーム・ユーザーID・プロフィールを更新しました。",
            )
            return redirect(reverse("mypage"))
    else:
        form = AccountProfileForm(instance=profile, user=request.user)

    return render(
        request,
        "mypage_edit.html",
        {"form": form, "profile": profile},
    )


@login_required
@require_POST
def toggle_follow(request, pk):
    profile_user = get_object_or_404(User, pk=pk)
    if profile_user == request.user:
        messages.error(request, "自分自身をフォローすることはできません。")
        return redirect(reverse("user_profile", kwargs={"pk": pk}))

    follow = Follow.objects.filter(
        follower=request.user, following=profile_user
    ).first()
    if follow:
        follow.delete()
        messages.info(request, f"{profile_user.username} さんのフォローを解除しました。")
    else:
        Follow.objects.create(follower=request.user, following=profile_user)
        Notification.objects.create(
            recipient=profile_user,
            message=f"「{request.user.username}さんにフォローされました！」",
            link=reverse("user_profile", kwargs={"pk": request.user.pk}),
        )
        messages.success(request, f"{profile_user.username} さんをフォローしました。")

    next_url = request.POST.get("next") or reverse("user_profile", kwargs={"pk": pk})
    return redirect(next_url)


@login_required
def mypage(request):
    profile, _ = UserProfile.objects.get_or_create(user=request.user)

    available_products = Product.objects.filter(
        seller=request.user, status=Product.Status.AVAILABLE
    )
    sold_products = Product.objects.filter(
        seller=request.user, status=Product.Status.SOLD_OUT
    )
    total_sales = calc_sales_total(request.user)
    rating_stats = get_user_rating_stats(request.user)

    return render(
        request,
        "mypage.html",
        {
            "total_sales": total_sales,
            "available_products": available_products,
            "sold_products": sold_products,
            "rating_stats": rating_stats,
            "profile": profile,
        },
    )


def user_profile(request, pk):
    profile_user = get_object_or_404(User, pk=pk)
    profile, _ = UserProfile.objects.get_or_create(user=profile_user)

    from_source = request.GET.get("from", "market").strip().lower()
    if from_source not in ("market", "thread"):
        from_source = "market"

    available_products = Product.objects.filter(
        seller=profile_user, status=Product.Status.AVAILABLE
    )
    rating_stats = get_user_rating_stats(profile_user)
    stats = get_profile_stats(profile_user, from_source)
    is_own_profile = request.user.is_authenticated and request.user.pk == profile_user.pk
    user_is_following = (
        is_following(request.user, profile_user)
        if request.user.is_authenticated and not is_own_profile
        else False
    )
    user_dm_room = None
    can_send_dm = False
    if request.user.is_authenticated and not is_own_profile:
        can_send_dm = True
        user_dm_room = find_dm_room(request.user, profile_user)

    return render(
        request,
        "user_profile.html",
        {
            "profile_user": profile_user,
            "available_products": available_products,
            "rating_stats": rating_stats,
            "profile": profile,
            "stats": stats,
            "from_source": from_source,
            "is_own_profile": is_own_profile,
            "user_is_following": user_is_following,
            "can_send_dm": can_send_dm,
            "user_dm_room": user_dm_room,
        },
    )


@login_required
@require_POST
def start_user_dm(request, pk):
    partner = get_object_or_404(User, pk=pk)
    if partner.pk == request.user.pk:
        messages.error(request, "自分自身に DM は送れません。")
        return redirect(reverse("mypage"))

    room, created = get_or_create_dm_room(request.user, partner)
    if created:
        messages.success(request, f"{partner.username} さんとの DM を開始しました。")
    return redirect(reverse("user_dm_room", kwargs={"room_pk": room.pk}))


@login_required
def user_dm_room(request, room_pk):
    room = get_object_or_404(
        UserDirectMessageRoom.objects.select_related("user_a", "user_b").prefetch_related(
            "messages__sender"
        ),
        pk=room_pk,
    )
    if not can_access_dm_room(room, request.user):
        messages.error(request, "この DM ルームにはアクセスできません。")
        return redirect(reverse("home"))

    partner = room.other_user(request.user)
    dm_messages = room.messages.select_related("sender")
    back_url = (
        reverse("user_profile", kwargs={"pk": partner.pk}) + "?from=thread"
        if partner
        else reverse("home")
    )

    return render(
        request,
        "dm_room.html",
        {
            "room": room,
            "partner": partner,
            "dm_messages": dm_messages,
            "back_url": back_url,
        },
    )


@login_required
@require_POST
def send_user_dm_message(request, room_pk):
    room = get_object_or_404(
        UserDirectMessageRoom.objects.select_related("user_a", "user_b"),
        pk=room_pk,
    )
    if not can_access_dm_room(room, request.user):
        messages.error(request, "この DM ルームにはアクセスできません。")
        return redirect(reverse("home"))

    body = request.POST.get("body", "").strip()
    if not body:
        messages.error(request, "メッセージを入力してください。")
        return redirect(reverse("user_dm_room", kwargs={"room_pk": room.pk}))

    if len(body) > 500:
        messages.error(request, "メッセージが長すぎます（500文字以内）。")
        return redirect(reverse("user_dm_room", kwargs={"room_pk": room.pk}))

    UserDirectMessage.objects.create(
        room=room,
        sender=request.user,
        body=body,
    )
    room.save(update_fields=["updated_at"])

    recipient = room.other_user(request.user)
    if recipient:
        Notification.objects.create(
            recipient=recipient,
            message=f"{request.user.username} さんから DM: {body[:40]}",
            link=dm_room_link(room),
        )

    return redirect(reverse("user_dm_room", kwargs={"room_pk": room.pk}))


@login_required
def exhibit(request):
    if request.method == "POST":
        form = ProductExhibitForm(request.POST, request.FILES)
        if form.is_valid():
            product = form.save(commit=False)
            product.seller = request.user
            try:
                product.save()
            except Exception as exc:
                _log_media_debug("EXHIBIT SAVE FAILED", str(exc), exc=exc)
                messages.error(request, "出品の保存に失敗しました。時間をおいて再度お試しください。")
                return render(request, "exhibit.html", {"form": form})
            _log_saved_file_field(product, "image", "EXHIBIT IMAGE")
            return redirect(reverse("home"))
    else:
        form = ProductExhibitForm(initial={"faculty": get_user_faculty(request.user)})

    return render(request, "exhibit.html", {"form": form})


class AppLoginView(LoginView):
    template_name = "login.html"
    authentication_form = EmailAuthenticationForm
    redirect_authenticated_user = True


def _log_auth_debug(label: str, detail: str, *, exc: BaseException | None = None) -> None:
    logger.warning("%s: %s", label, detail, exc_info=exc)
    if settings.DEBUG:
        print(f"[WASE {label}] {detail}", file=sys.stderr, flush=True)
        if exc:
            traceback.print_exc()


def _log_media_debug(label: str, detail: str, *, exc: BaseException | None = None) -> None:
    """画像保存の診断ログ（本番 Render でも stderr に出力）。"""
    message = f"[WASE {label}] {detail}"
    logger.warning(message, exc_info=exc)
    print(message, file=sys.stderr, flush=True)
    if exc:
        traceback.print_exc(file=sys.stderr)


def _has_uploaded_file(field_file) -> bool:
    return bool(field_file and getattr(field_file, "name", None))


def _log_saved_file_field(instance, field_name: str, label: str) -> None:
    field_file = getattr(instance, field_name, None)
    if not _has_uploaded_file(field_file):
        _log_media_debug(label, "画像フィールドは空です")
        return
    try:
        file_name = field_file.name
        file_url = field_file.url
    except Exception as exc:
        _log_media_debug(f"{label} URL ERROR", str(exc), exc=exc)
        return
    _log_media_debug(
        label,
        (
            f"storage={settings.STORAGES['default']['BACKEND']} "
            f"use_cloudinary={getattr(settings, 'USE_CLOUDINARY', False)} "
            f"name={file_name} url={file_url}"
        ),
    )


def _save_timeline_post(post):
    _log_media_debug(
        "BOARD COMPOSE",
        (
            f"保存開始 post_id={post.pk} "
            f"has_image_file={_has_uploaded_file(post.image)} "
            f"storage={settings.STORAGES['default']['BACKEND']}"
        ),
    )
    try:
        post.save()
    except Exception as exc:
        _log_media_debug("BOARD COMPOSE SAVE FAILED", str(exc), exc=exc)
        raise
    _log_saved_file_field(post, "image", "BOARD COMPOSE IMAGE")
    return post


def _signup_form_errors_message(form) -> str:
    parts = []
    for field, errors in form.errors.items():
        for error in errors:
            label = field if field != "__all__" else "フォーム"
            parts.append(f"{label}: {error}")
    return " ".join(parts) if parts else "入力内容を確認してください。"


def _persist_signup_user(form):
    """新規または認証待ちユーザーを保存し、プロフィールを更新する。"""
    email = form.cleaned_data["email"]
    faculty = form.cleaned_data["faculty"]
    password = form.cleaned_data["password1"]
    nickname = form.cleaned_data["nickname"]

    pending = User.objects.filter(email__iexact=email, is_active=False).first()
    if pending:
        pending.set_password(password)
        pending.username = nickname
        pending.save(update_fields=["password", "username"])
        user = pending
    else:
        user = form.save()

    UserProfile.objects.update_or_create(
        user=user,
        defaults={"department": faculty},
    )
    return user


def _email_env_warnings_for_request():
    return list(getattr(settings, "EMAIL_ENV_WARNINGS", []))


def _flash_email_env_warnings(request) -> None:
    for warning in _email_env_warnings_for_request():
        messages.warning(request, warning)


def _start_otp_verification(request, user):
    """OTP送信後、セッションを設定して認証画面へリダイレクトする。"""
    request.session[SIGNUP_PENDING_SESSION_KEY] = user.pk
    request.session.modified = True
    if getattr(settings, "EMAIL_USE_CONSOLE_FALLBACK", False):
        messages.info(
            request,
            "開発モード: 認証コードは runserver のターミナルに出力されています。"
            " 10分以内に下の画面で入力してください。",
        )
    else:
        messages.info(
            request,
            f"{user.email} に6桁の認証コードを送信しました。10分以内に入力してください。",
        )
    return redirect(reverse("verify_otp"))


def signup(request):
    if request.user.is_authenticated and request.user.is_active:
        return redirect(reverse("home"))

    if request.method == "GET":
        _flash_email_env_warnings(request)
        if not getattr(settings, "EMAIL_USE_CONSOLE_FALLBACK", False):
            for err in get_email_config_errors():
                messages.warning(request, err)

    if request.method == "POST":
        form = SignUpForm(request.POST)
        if not form.is_valid():
            error_summary = _signup_form_errors_message(form)
            _log_auth_debug("SIGNUP VALIDATION", f"errors={form.errors.as_json()}")
            messages.error(request, error_summary)
            return render(request, "signup.html", {"form": form}, status=200)

        try:
            with transaction.atomic():
                user = _persist_signup_user(form)
                create_and_send_signup_otp(user)
        except EmailConfigurationError as exc:
            _log_auth_debug("SIGNUP EMAIL CONFIG", str(exc), exc=exc)
            messages.error(request, str(exc))
            _flash_email_env_warnings(request)
            return render(request, "signup.html", {"form": form}, status=200)
        except UnicodeEncodeError as exc:
            _log_auth_debug("SIGNUP UNICODE", str(exc), exc=exc)
            messages.error(
                request,
                "メール設定に使用できない文字（全角・日本語のプレースホルダーなど）が含まれています。"
                " サーバー起動時の [WASE EMAIL ENV] ログを確認してください。",
            )
            return render(request, "signup.html", {"form": form}, status=200)
        except Exception as exc:
            _log_auth_debug("SIGNUP FAILED", str(exc), exc=exc)
            messages.error(
                request,
                "認証メールの送信に失敗しました。ターミナルのエラーログを確認してください。",
            )
            if settings.DEBUG:
                messages.error(request, f"詳細（DEBUG）: {exc}")
            return render(request, "signup.html", {"form": form}, status=200)

        return _start_otp_verification(request, user)

    form = SignUpForm()
    return render(request, "signup.html", {"form": form})


def _get_pending_signup_user(request):
    user_id = request.session.get(SIGNUP_PENDING_SESSION_KEY)
    if not user_id:
        return None
    return User.objects.filter(pk=user_id, is_active=False).first()


def verify_otp(request):
    if request.user.is_authenticated and request.user.is_active:
        return redirect(reverse("home"))

    user = _get_pending_signup_user(request)
    if not user:
        messages.warning(request, "新規登録からやり直してください。")
        return redirect(reverse("signup"))

    if request.method == "POST" and "resend" not in request.POST:
        form = SignupOTPVerifyForm(request.POST)
        if form.is_valid():
            error = verify_signup_otp(user, form.cleaned_data["code"])
            if error:
                form.add_error("code", error)
                _log_auth_debug("VERIFY OTP", error)
            else:
                user.is_active = True
                user.save(update_fields=["is_active"])
                del request.session[SIGNUP_PENDING_SESSION_KEY]
                login(request, user)
                messages.success(
                    request, "メール認証が完了しました。ようこそ、わせわせへ！"
                )
                return redirect(reverse("home"))
        else:
            _log_auth_debug(
                "VERIFY OTP VALIDATION", f"errors={form.errors.as_json()}"
            )
    else:
        form = SignupOTPVerifyForm()

    return render(
        request,
        "verify_otp.html",
        {"form": form, "masked_email": user.email},
    )


@require_POST
def verify_otp_resend(request):
    if request.user.is_authenticated and request.user.is_active:
        return redirect(reverse("home"))

    user = _get_pending_signup_user(request)
    if not user:
        messages.warning(request, "新規登録からやり直してください。")
        return redirect(reverse("signup"))

    try:
        create_and_send_signup_otp(user)
        messages.success(request, "認証コードを再送信しました。")
    except EmailConfigurationError as exc:
        _log_auth_debug("RESEND EMAIL CONFIG", str(exc), exc=exc)
        messages.error(request, str(exc))
        _flash_email_env_warnings(request)
    except UnicodeEncodeError as exc:
        _log_auth_debug("RESEND UNICODE", str(exc), exc=exc)
        messages.error(
            request,
            "メール設定に使用できない文字が含まれています。サーバーログを確認してください。",
        )
    except Exception as exc:
        _log_auth_debug("RESEND FAILED", str(exc), exc=exc)
        messages.error(
            request,
            "認証メールの送信に失敗しました。ターミナルのエラーログを確認してください。",
        )
        if settings.DEBUG:
            messages.error(request, f"詳細（DEBUG）: {exc}")

    return redirect(reverse("verify_otp"))


def _board_redirect(request, *, tag="", post_id=None):
    url = reverse("home") + "?tab=board"
    if tag:
        url += f"&tag={quote(tag)}"
    q = request.GET.get("q", "").strip()
    if q:
        url += f"&q={q}"
    if post_id:
        url += f"#post-{post_id}"
    return redirect(url)


@login_required
@require_POST
def board_compose(request):
    form = TimelinePostForm(request.POST, request.FILES)
    if form.is_valid():
        post = form.save(commit=False)
        post.author = request.user
        faculty = get_user_faculty(request.user)
        if not post.faculty and faculty:
            post.faculty = faculty
        try:
            _save_timeline_post(post)
        except Exception as exc:
            _log_media_debug("BOARD COMPOSE FAILED", str(exc), exc=exc)
            messages.error(
                request,
                "投稿の保存に失敗しました。画像アップロード設定を確認してください。",
            )
            return _board_redirect(request, tag=form.data.get("course_name", ""))
        if post.image:
            messages.success(request, "写真付きのつぶやきを投稿しました。")
        else:
            messages.success(request, "つぶやきを投稿しました。")
    else:
        _log_auth_debug("BOARD COMPOSE", f"errors={form.errors.as_json()}")
        _log_media_debug(
            "BOARD COMPOSE VALIDATION",
            f"errors={form.errors.as_json()} files={list(request.FILES.keys())}",
        )
        messages.error(request, "投稿に失敗しました。内容を確認してください。")
        for field, errors in form.errors.items():
            for error in errors:
                messages.error(request, f"{field}: {error}")
    return _board_redirect(request, tag=form.data.get("course_name", ""))


@login_required
@require_POST
def board_timeline_like(request, pk):
    post = get_object_or_404(TimelinePost, pk=pk)
    like, created = TimelineLike.objects.get_or_create(
        timeline_post=post,
        user=request.user,
    )
    if created:
        post.like_count += 1
        post.save(update_fields=["like_count"])
        notify_timeline_post_author(
            post,
            request.user,
            f"{request.user.username}さんがあなたの投稿にいいねしました",
        )
        messages.success(request, "いいねしました。")
    else:
        like.delete()
        post.like_count = max(0, post.like_count - 1)
        post.save(update_fields=["like_count"])
        messages.success(request, "いいねを取り消しました。")
    return _board_redirect(request, tag=post.course_name)


@login_required
@require_POST
def board_timeline_god(request, pk):
    post = get_object_or_404(TimelinePost, pk=pk)

    if not can_use_god_button(request.user):
        messages.warning(
            request,
            f"今月の神！ボタンは使い切りました（月{GOD_USES_PER_MONTH}回まで）。",
        )
        return _board_redirect(request, tag=post.course_name)

    GodButtonUse.objects.create(user=request.user, timeline_post=post)
    post.god_count += 1
    post.save(update_fields=["god_count"])
    notify_timeline_post_author(
        post,
        request.user,
        f"{request.user.username}さんがあなたの投稿を『神！』と言っています",
    )
    messages.success(request, "神！を押しました。")
    return _board_redirect(request, tag=post.course_name)


@login_required
@require_POST
def board_timeline_comment(request, pk):
    post = get_object_or_404(TimelinePost, pk=pk)
    form = TimelineCommentForm(request.POST)
    if form.is_valid():
        comment = form.save(commit=False)
        comment.timeline_post = post
        comment.author = request.user
        comment.save()
        if post.author_id and post.author_id != request.user.id:
            Notification.objects.create(
                recipient=post.author,
                message=(
                    f"「{request.user.username}さんが"
                    "あなたの投稿にコメントしました」"
                ),
                link=timeline_post_link(post),
            )
        messages.success(request, "コメントを投稿しました。")
    else:
        messages.error(request, "コメントを投稿できませんでした。")
    return _board_redirect(request, tag=post.course_name, post_id=post.pk)


@login_required
@require_POST
def delete_timeline_post(request, pk):
    post = get_object_or_404(TimelinePost, pk=pk)
    if post.author_id != request.user.id:
        messages.error(request, "この投稿を削除する権限がありません。")
        return _board_redirect(request, tag=post.course_name or "")

    tag = post.course_name or ""
    post.delete()
    messages.success(request, "投稿を削除しました。")
    return redirect(build_home_url(tab="board", active_tag=tag))


@login_required
@require_POST
def delete_product(request, pk):
    product = get_object_or_404(Product, pk=pk)
    if product.seller_id != request.user.id:
        messages.error(request, "この商品を削除する権限がありません。")
        return redirect(reverse("product_detail", kwargs={"pk": pk}))

    product.delete()
    messages.success(request, "商品を削除しました。")
    return redirect(build_home_url(tab="flea"))


@login_required
@require_POST
def delete_comment(request, pk):
    comment = get_object_or_404(
        Comment.objects.select_related("product", "timeline_post"),
        pk=pk,
    )
    product_id = comment.product_id
    timeline_post = comment.timeline_post
    tag = (timeline_post.course_name or "") if timeline_post else ""
    post_id = timeline_post.pk if timeline_post else None

    if comment.author_id != request.user.id:
        messages.error(request, "このコメントを削除する権限がありません。")
        if product_id:
            return redirect(reverse("product_detail", kwargs={"pk": product_id}))
        if post_id:
            return _board_redirect(request, tag=tag, post_id=post_id)
        return redirect(reverse("home"))

    comment.delete()
    messages.success(request, "コメントを削除しました。")
    if product_id:
        return redirect(reverse("product_detail", kwargs={"pk": product_id}))
    if post_id:
        return _board_redirect(request, tag=tag, post_id=post_id)
    return redirect(reverse("home"))


def logout_view(request):
    logout(request)
    return redirect(settings.LOGOUT_REDIRECT_URL)
