from urllib.parse import quote

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.db.models import Case, Count, IntegerField, Q, Value, When
from django.utils import timezone
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from .constants import FACULTY_CHOICES, TRADE_LOCATION_PRESETS
from .board_services import (
    GOD_USES_PER_MONTH,
    can_use_god_button,
    god_uses_remaining,
    notify_timeline_post_author,
)
from .forms import (
    CommentForm,
    EmailAuthenticationForm,
    ProductExhibitForm,
    ProfileForm,
    ReviewForm,
    SignUpForm,
    TimelineCommentForm,
    TimelinePostForm,
)
from .models import (
    GodButtonUse,
    Like,
    Notification,
    Product,
    Review,
    TimelinePost,
    TimelineTip,
    TradeMessage,
    UserProfile,
)
from .services import (
    calc_sales_total,
    get_reviewee,
    get_user_faculty,
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
        timeline_posts = timeline_posts.order_by("-created_at")

        trending_posts = (
            TimelinePost.objects.select_related("author")
            .filter(god_count__gt=0)
            .order_by("-god_count", "-created_at")[:5]
        )

        popular_tags = list(
            TimelinePost.objects.exclude(course_name="")
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
                | Q(course_name__icontains=query)
                | Q(professor_name__icontains=query)
            )
        if request.user.is_authenticated and not active_faculty:
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
        },
    )


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
            f"「{product.name}」の取引が開始されました。（¥{product.price:,}）",
            actor_id=request.user.id,
        )
        messages.success(
            request,
            "取引を開始しました。出品者とチャットで受け渡しを調整しましょう。",
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
def mypage(request):
    profile, _ = UserProfile.objects.get_or_create(user=request.user)

    if request.method == "POST" and request.POST.get("form_type") == "profile":
        profile_form = ProfileForm(request.POST, instance=profile)
        if profile_form.is_valid():
            profile_form.save()
            messages.success(request, "学部情報を更新しました。")
            return redirect(reverse("mypage"))
    else:
        profile_form = ProfileForm(instance=profile)

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
            "profile_form": profile_form,
        },
    )


def user_profile(request, username):
    profile_user = get_object_or_404(User, username=username)

    if request.user.is_authenticated and request.user == profile_user:
        return redirect(reverse("mypage"))

    available_products = Product.objects.filter(
        seller=profile_user, status=Product.Status.AVAILABLE
    )
    rating_stats = get_user_rating_stats(profile_user)
    profile = UserProfile.objects.filter(user=profile_user).first()

    return render(
        request,
        "user_profile.html",
        {
            "profile_user": profile_user,
            "available_products": available_products,
            "rating_stats": rating_stats,
            "profile": profile,
        },
    )


@login_required
def exhibit(request):
    if request.method == "POST":
        form = ProductExhibitForm(request.POST, request.FILES)
        if form.is_valid():
            product = form.save(commit=False)
            product.seller = request.user
            product.save()
            return redirect(reverse("home"))
    else:
        form = ProductExhibitForm(initial={"faculty": get_user_faculty(request.user)})

    return render(request, "exhibit.html", {"form": form})


class AppLoginView(LoginView):
    template_name = "login.html"
    authentication_form = EmailAuthenticationForm
    redirect_authenticated_user = True


def signup(request):
    if request.user.is_authenticated:
        return redirect(reverse("home"))

    if request.method == "POST":
        form = SignUpForm(request.POST)
        if form.is_valid():
            user = form.save()
            UserProfile.objects.create(
                user=user, faculty=form.cleaned_data["faculty"]
            )
            login(request, user)
            messages.success(request, "アカウントを作成しました。")
            return redirect(reverse("home"))
    else:
        form = SignUpForm()

    return render(request, "signup.html", {"form": form})


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
    form = TimelinePostForm(request.POST)
    if form.is_valid():
        post = form.save(commit=False)
        post.author = request.user
        faculty = get_user_faculty(request.user)
        if not post.faculty and faculty:
            post.faculty = faculty
        post.save()
        messages.success(request, "つぶやきを投稿しました。")
    else:
        messages.error(request, "投稿に失敗しました。内容を確認してください。")
    return _board_redirect(request, tag=form.data.get("course_name", ""))


@login_required
@require_POST
def board_timeline_tip(request, pk):
    post = get_object_or_404(TimelinePost, pk=pk)
    TimelineTip.objects.create(timeline_post=post, user=request.user, amount=1)
    post.tip_total += 1
    post.save(update_fields=["tip_total"])
    notify_timeline_post_author(
        post,
        request.user,
        f"{request.user.username}さんがあなたの投稿に1円投げ銭しました",
    )
    messages.success(request, "1円の投げ銭を送りました。ありがとうございます！")
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
        notify_timeline_post_author(
            post,
            request.user,
            f"{request.user.username}さんがあなたの投稿にコメントしました",
        )
        messages.success(request, "コメントを投稿しました。")
    else:
        messages.error(request, "コメントを投稿できませんでした。")
    return _board_redirect(request, tag=post.course_name, post_id=post.pk)


def logout_view(request):
    logout(request)
    return redirect(settings.LOGOUT_REDIRECT_URL)
