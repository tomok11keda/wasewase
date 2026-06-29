import json
import logging
import sys
import traceback
from urllib.parse import quote, urlencode

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.db import IntegrityError, transaction
from django.db.models import Case, Count, Exists, IntegerField, OuterRef, Q, Value, When
from django.utils import timezone
from django.views.decorators.cache import cache_control
from django.views.decorators.http import require_GET, require_POST
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse

from .community_services import (
    build_communities_index_url,
    create_community_thread as save_community_thread,
    create_thread_reply as save_thread_reply,
    get_community_for_new_thread,
    get_community_thread,
    get_faculty_tag_choices,
    list_community_threads,
    list_replies_for_thread,
)
from .constants import FACULTY_CHOICES
from .mention_services import notify_mentions
from .dm_services import (
    build_dm_conversations,
    can_access_dm_room,
    dm_room_link,
    find_dm_room,
    get_or_create_dm_room,
)
from .board_services import (
    prepare_timeline_post_for_save,
    TIMELINE_INITIAL_SIZE,
    TIMELINE_LOAD_MORE_SIZE,
    build_timeline_posts_queryset,
    get_profile_timeline_posts,
    get_quotable_post,
    notify_timeline_post_author,
    timeline_post_link,
)
from .bookmark_services import (
    BookmarkServiceError,
    get_bookmarked_timeline_posts,
    prepare_timeline_posts,
    toggle_bookmark,
)
from .forms import (
    EmailAuthenticationForm,
    AccountProfileForm,
    CommunityThreadForm,
    CommunityThreadReplyForm,
    ContentReportForm,
    SignUpForm,
    SignupOTPVerifyForm,
    TimelineCommentForm,
    TimelinePostForm,
)
from .models import (
    Comment,
    Community,
    ContentReport,
    Follow,
    Notification,
    TimelinePost,
    TimelineLike,
    UserDirectMessage,
    UserDirectMessageRoom,
    UserProfile,
)
from .media_services import (
    compose_save_error_message,
    describe_uploaded_file,
    ensure_local_post_images_dir,
    log_compose_request,
    log_media_storage_status,
    log_media_upload,
    log_timelinepost_db_schema,
    prepare_image_field_for_save,
    validate_timeline_image_file,
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
    build_home_url,
    build_search_url,
    get_following_user_ids,
    get_profile_stats,
    get_user_faculty,
    is_following,
    search_timeline_posts,
    user_display_name,
)
from .ugc_services import (
    block_user,
    filter_visible_timeline_posts,
    get_report_target,
    get_reported_user_id,
    is_user_blocked,
    unblock_user,
)
User = get_user_model()


def _serialize_room_message(message, current_user_id):
    created = timezone.localtime(message.created_at)
    return {
        "id": message.pk,
        "sender_id": message.sender_id,
        "sender_name": user_display_name(message.sender),
        "body": message.body,
        "created_at": created.strftime("%m/%d %H:%M"),
        "is_mine": message.sender_id == current_user_id,
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


def index(request):
    if request.GET.get("tab"):
        params = request.GET.copy()
        params.pop("tab", None)
        url = reverse("home")
        encoded = params.urlencode()
        if encoded:
            url = f"{url}?{encoded}"
        return redirect(url, permanent=True)

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

    active_tag = request.GET.get("tag", "").strip()

    timeline_qs = build_timeline_posts_queryset(request)
    timeline_total_count = timeline_qs.count()
    timeline_posts = list(timeline_qs[:TIMELINE_INITIAL_SIZE])
    timeline_posts = prepare_timeline_posts(timeline_posts, request.user)
    timeline_has_more = timeline_total_count > len(timeline_posts)
    timeline_next_offset = len(timeline_posts)

    trending_posts = list(
        filter_visible_timeline_posts(
            TimelinePost.objects.select_related("author")
            .filter(like_count__gt=0)
            .order_by("-like_count", "-created_at"),
            request.user if request.user.is_authenticated else None,
        )[:5]
    )

    popular_tags = list(
        TimelinePost.objects.exclude(course_name__isnull=True)
        .exclude(course_name="")
        .values_list("course_name", flat=True)
        .distinct()[:12]
    )

    return render(
        request,
        "top.html",
        {
            "timeline_posts": timeline_posts,
            "trending_posts": trending_posts,
            "popular_tags": popular_tags,
            "active_tag": active_tag,
            "query": query,
            "user_faculty": user_faculty,
            "faculty_tabs": faculty_tabs,
            "active_faculty": active_faculty,
            "feed_scope": feed_scope,
            "feed_following_unauthenticated": feed_following_unauthenticated,
            "feed_url_all": build_home_url(
                feed_scope="all",
                query=query,
                active_faculty=active_faculty,
                active_tag=active_tag,
            ),
            "feed_url_following": build_home_url(
                feed_scope="following",
                query=query,
                active_faculty=active_faculty,
                active_tag=active_tag,
            ),
            "timeline_has_more": timeline_has_more,
            "timeline_next_offset": timeline_next_offset,
            "timeline_total_count": timeline_total_count,
            "nav_active": "home",
        },
    )


@require_GET
def timeline_feed(request):
    """タイムラインの追加読み込み（無限スクロール用）。"""
    try:
        offset = max(0, int(request.GET.get("offset", "0")))
    except ValueError:
        offset = 0

    timeline_qs = build_timeline_posts_queryset(request)
    total_count = timeline_qs.count()
    posts = prepare_timeline_posts(
        list(timeline_qs[offset : offset + TIMELINE_LOAD_MORE_SIZE]),
        request.user,
    )
    next_offset = offset + len(posts)
    has_more = next_offset < total_count

    html = render_to_string(
        "includes/timeline_posts_batch.html",
        {
            "timeline_posts": posts,
            "query": request.GET.get("q", "").strip(),
        },
        request=request,
    )
    return JsonResponse(
        {
            "html": html,
            "has_more": has_more,
            "next_offset": next_offset,
            "total_count": total_count,
        }
    )


def search(request):
    """タイムライン投稿を検索。"""
    query = request.GET.get("q", "").strip()
    viewer = request.user if request.user.is_authenticated else None
    timeline_posts = TimelinePost.objects.none()
    if query:
        timeline_posts = (
            search_timeline_posts(query, viewer=viewer)
            .select_related(
                "author",
                "author__profile",
                "quoted_post",
                "quoted_post__author",
            )
            .prefetch_related("comments__author")
        )
        if request.user.is_authenticated:
            timeline_posts = timeline_posts.annotate(
                user_has_liked=Exists(
                    TimelineLike.objects.filter(
                        timeline_post_id=OuterRef("pk"),
                        user_id=request.user.id,
                    )
                )
            )

    timeline_posts = prepare_timeline_posts(timeline_posts, viewer)

    return render(
        request,
        "search.html",
        {
            "query": query,
            "timeline_posts": timeline_posts,
            "timeline_count": len(timeline_posts),
            "search_url": build_search_url(query),
            "nav_active": "search",
        },
    )


def communities_index(request):
    """学部タグと検索で絞り込めるスレッド一覧。"""
    faculty_values = {value for value, _ in FACULTY_CHOICES}
    active_tag = request.GET.get("tag", "").strip()
    if active_tag not in faculty_values:
        active_tag = ""
    query = request.GET.get("q", "").strip()
    threads = list_community_threads(query=query, faculty=active_tag)
    thread_form = CommunityThreadForm() if request.user.is_authenticated else None

    return render(
        request,
        "communities_index.html",
        {
            "threads": threads,
            "faculty_tabs": get_faculty_tag_choices(),
            "active_tag": active_tag,
            "query": query,
            "thread_form": thread_form,
            "nav_active": "communities",
        },
    )


def community_detail(request, slug):
    """旧掲示板URLからコミュニティ一覧へリダイレクト。"""
    community = get_object_or_404(Community, slug=slug, is_active=True)
    return redirect(build_communities_index_url(tag=community.faculty))


@login_required
@require_POST
def create_community_thread(request):
    faculty_values = {value for value, _ in FACULTY_CHOICES}
    active_tag = request.POST.get("tag", "").strip()
    if active_tag not in faculty_values:
        active_tag = ""
    community = get_community_for_new_thread(faculty=active_tag)
    if community is None:
        messages.error(request, "スレッドを作成できる掲示板がありません。")
        return redirect(reverse("communities_index"))

    form = CommunityThreadForm(request.POST)
    if form.is_valid():
        save_community_thread(
            community,
            request.user,
            form.cleaned_data["title"],
            form.cleaned_data["body"],
        )
        messages.success(request, "スレッドを作成しました。")
    else:
        error = next(iter(form.errors.values()))[0]
        messages.error(request, error)
    return redirect(build_communities_index_url(tag=active_tag))


def community_thread_detail(request, slug, thread_pk):
    community = get_object_or_404(Community, slug=slug, is_active=True)
    thread = get_community_thread(community, thread_pk)
    replies = list_replies_for_thread(thread)
    reply_form = CommunityThreadReplyForm() if request.user.is_authenticated else None
    return render(
        request,
        "community_thread_detail.html",
        {
            "community": community,
            "thread": thread,
            "replies": replies,
            "reply_form": reply_form,
            "nav_active": "communities",
        },
    )


@login_required
@require_POST
def create_community_thread_reply(request, slug, thread_pk):
    community = get_object_or_404(Community, slug=slug, is_active=True)
    thread = get_community_thread(community, thread_pk)
    form = CommunityThreadReplyForm(request.POST)
    if form.is_valid():
        reply = save_thread_reply(thread, request.user, form.cleaned_data["body"])
        messages.success(request, "返信を投稿しました。")
        return redirect(
            reverse(
                "community_thread_detail",
                kwargs={"slug": community.slug, "thread_pk": thread.pk},
            )
            + f"#reply-{reply.pk}"
        )
    else:
        error = next(iter(form.errors.values()))[0]
        messages.error(request, error)
    return redirect(
        reverse(
            "community_thread_detail",
            kwargs={"slug": community.slug, "thread_pk": thread.pk},
        )
    )


@login_required
def notifications(request):
    items = Notification.objects.filter(recipient=request.user)
    items.filter(is_read=False).update(is_read=True)

    return render(
        request,
        "notifications.html",
        {"notifications": items, "nav_active": "notifications"},
    )


@login_required
def mypage_edit(request):
    profile, _ = UserProfile.objects.get_or_create(user=request.user)

    if request.method == "POST":
        form = AccountProfileForm(
            request.POST, instance=profile, user=request.user
        )
        if form.is_valid():
            with transaction.atomic():
                saved_profile = form.save()
            request.user.refresh_from_db()
            profile = UserProfile.objects.get(pk=saved_profile.pk)
            messages.success(
                request,
                "ニックネーム・ユーザーID・プロフィールを更新しました。",
            )
            return redirect(reverse("mypage"))
        messages.error(request, "保存に失敗しました。入力内容を確認してください。")
        for field, errors in form.errors.items():
            for error in errors:
                messages.error(request, f"{field}: {error}")
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
@require_POST
def toggle_block(request, pk):
    profile_user = get_object_or_404(User, pk=pk)
    if profile_user == request.user:
        messages.error(request, "自分自身をブロックすることはできません。")
        return redirect(reverse("user_profile", kwargs={"pk": pk}))

    if is_user_blocked(request.user, profile_user):
        unblock_user(request.user, profile_user)
        messages.info(request, f"{profile_user.username} さんのブロックを解除しました。")
    else:
        block_user(request.user, profile_user)
        messages.success(
            request,
            f"{profile_user.username} さんをブロックしました。このユーザーの投稿は表示されなくなります。",
        )

    next_url = request.POST.get("next") or reverse("user_profile", kwargs={"pk": pk})
    return redirect(next_url)


def _wants_json_response(request) -> bool:
    accept = request.headers.get("Accept", "")
    if "application/json" in accept:
        return True
    return request.headers.get("X-Requested-With") == "XMLHttpRequest"


@login_required
@require_POST
def submit_report(request):
    form = ContentReportForm(request.POST)
    if not form.is_valid():
        if _wants_json_response(request):
            return JsonResponse({"ok": False, "errors": form.errors}, status=400)
        messages.error(request, "通報内容を確認してください。")
        return redirect(request.META.get("HTTP_REFERER", reverse("home")))

    target_type = form.cleaned_data["target_type"]
    if target_type == ContentReport.TargetType.PRODUCT:
        message = "この通報種別は利用できません。"
        if _wants_json_response(request):
            return JsonResponse({"ok": False, "message": message}, status=400)
        messages.error(request, message)
        return redirect(request.META.get("HTTP_REFERER", reverse("home")))

    target_id = form.cleaned_data["target_id"]
    target = get_report_target(target_type, target_id)
    if target is None:
        message = "通報対象が見つからないか、すでに削除されています。"
        if _wants_json_response(request):
            return JsonResponse({"ok": False, "message": message}, status=404)
        messages.error(request, message)
        return redirect(request.META.get("HTTP_REFERER", reverse("home")))

    reported_user_id = get_reported_user_id(target_type, target)
    if reported_user_id == request.user.pk:
        message = "自分自身のコンテンツは通報できません。"
        if _wants_json_response(request):
            return JsonResponse({"ok": False, "message": message}, status=400)
        messages.error(request, message)
        return redirect(request.META.get("HTTP_REFERER", reverse("home")))

    try:
        ContentReport.objects.create(
            reporter=request.user,
            target_type=target_type,
            target_id=target_id,
            reason=form.cleaned_data["reason"],
            detail=form.cleaned_data.get("detail", ""),
        )
    except IntegrityError:
        message = "この内容はすでに通報済みです。運営が確認します。"
        if _wants_json_response(request):
            return JsonResponse({"ok": True, "message": message})
        messages.info(request, message)
        return redirect(request.META.get("HTTP_REFERER", reverse("home")))

    message = "通報を受け付けました。内容を確認し、必要に応じて対応します。"
    if _wants_json_response(request):
        return JsonResponse({"ok": True, "message": message})
    messages.success(request, message)
    return redirect(request.META.get("HTTP_REFERER", reverse("home")))


@login_required
def mypage(request):
    profile, _ = UserProfile.objects.get_or_create(user=request.user)

    return render(
        request,
        "mypage.html",
        {
            "profile": profile,
            "stats": get_profile_stats(request.user),
            "nav_active": "mypage",
        },
    )


def user_profile(request, pk):
    profile_user = get_object_or_404(User, pk=pk)
    profile, _ = UserProfile.objects.get_or_create(user=profile_user)

    stats = get_profile_stats(profile_user)
    is_own_profile = request.user.is_authenticated and request.user.pk == profile_user.pk
    user_is_following = (
        is_following(request.user, profile_user)
        if request.user.is_authenticated and not is_own_profile
        else False
    )
    user_is_blocked = (
        is_user_blocked(request.user, profile_user)
        if request.user.is_authenticated and not is_own_profile
        else False
    )
    user_dm_room = None
    can_send_dm = False
    if request.user.is_authenticated and not is_own_profile:
        can_send_dm = True
        user_dm_room = find_dm_room(request.user, profile_user)

    profile_tab = request.GET.get("tab", "overview").strip()
    if profile_tab not in ("overview", "bookmarks"):
        profile_tab = "overview"
    if profile_tab == "bookmarks" and not is_own_profile:
        profile_tab = "overview"

    bookmark_posts = []
    bookmark_meta = {}
    if profile_tab == "bookmarks" and is_own_profile:
        bookmark_posts, bookmark_meta = get_bookmarked_timeline_posts(
            profile_user, request.user
        )

    profile_posts = []
    if profile_tab == "overview":
        viewer = request.user if request.user.is_authenticated else None
        profile_posts = get_profile_timeline_posts(profile_user, viewer)

    nav_active = ""
    if is_own_profile:
        nav_active = "bookmarks" if profile_tab == "bookmarks" else "mypage"

    return render(
        request,
        "user_profile.html",
        {
            "profile_user": profile_user,
            "profile": profile,
            "stats": stats,
            "is_own_profile": is_own_profile,
            "user_is_following": user_is_following,
            "user_is_blocked": user_is_blocked,
            "can_send_dm": can_send_dm,
            "user_dm_room": user_dm_room,
            "profile_tab": profile_tab,
            "bookmark_posts": bookmark_posts,
            "bookmark_meta": bookmark_meta,
            "profile_posts": profile_posts,
            "nav_active": nav_active,
        },
    )


@login_required
def user_dm_inbox(request):
    return render(
        request,
        "dm_inbox.html",
        {
            "conversations": build_dm_conversations(request.user),
            "nav_active": "messages",
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
    latest_message_id = (
        dm_messages.order_by("-pk").values_list("pk", flat=True).first() or 0
    )
    back_url = reverse("user_dm_inbox")
    return render(
        request,
        "dm_room.html",
        {
            "room": room,
            "partner": partner,
            "dm_messages": dm_messages,
            "back_url": back_url,
            "latest_message_id": latest_message_id,
            "messages_poll_url": reverse(
                "user_dm_room_messages", kwargs={"room_pk": room.pk}
            ),
            "nav_active": "messages",
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
@require_GET
def user_dm_room_messages(request, room_pk):
    room = get_object_or_404(
        UserDirectMessageRoom.objects.select_related("user_a", "user_b"),
        pk=room_pk,
    )
    if not can_access_dm_room(room, request.user):
        return JsonResponse({"error": "forbidden"}, status=403)

    return _room_messages_json(request, room.messages)


class AppLoginView(LoginView):
    template_name = "login.html"
    authentication_form = EmailAuthenticationForm
    redirect_authenticated_user = True

    def get_success_url(self):
        url = super().get_success_url()
        separator = "&" if "?" in url else "?"
        return f"{url}{separator}login_success=1"


def _log_auth_debug(label: str, detail: str, *, exc: BaseException | None = None) -> None:
    logger.warning("%s: %s", label, detail, exc_info=exc)
    if settings.DEBUG:
        print(f"[WASE {label}] {detail}", file=sys.stderr, flush=True)
        if exc:
            traceback.print_exc()


def _log_media_debug(label: str, detail: str, *, exc: BaseException | None = None) -> None:
    log_media_upload(label, detail, exc=exc)


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
    log_media_storage_status()
    has_image = _has_uploaded_file(post.image)
    log_media_upload(
        "BOARD COMPOSE SAVE",
        (
            f"post_id={post.pk} author_id={post.author_id} "
            f"has_image={has_image} "
            f"image={describe_uploaded_file(post.image) if has_image else 'none'} "
            f"storage={settings.STORAGES['default']['BACKEND']}"
        ),
    )
    if has_image and not getattr(settings, "USE_CLOUDINARY", False):
        try:
            ensure_local_post_images_dir()
        except OSError as exc:
            log_media_upload("BOARD COMPOSE MKDIR", str(exc), exc=exc)
            raise
    if has_image:
        prepare_image_field_for_save(post)
    prepare_timeline_post_for_save(post)
    try:
        post.save()
    except Exception as exc:
        log_timelinepost_db_schema()
        log_media_upload(
            "BOARD COMPOSE SAVE FAILED",
            f"type={type(exc).__qualname__} message={exc}",
            exc=exc,
        )
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
        pending.save(update_fields=["password"])
        user = pending
    else:
        user = form.save()

    UserProfile.objects.update_or_create(
        user=user,
        defaults={"department": faculty, "name": nickname},
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
                return redirect(reverse("home") + "?login_success=1")
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
    url = build_home_url(active_tag=tag)
    if post_id:
        url += f"#post-{post_id}"
    return redirect(url)


@login_required
@require_POST
def board_compose(request):
    log_compose_request(request)
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
            log_media_upload(
                "BOARD COMPOSE FAILED",
                f"type={type(exc).__qualname__} message={exc}",
                exc=exc,
            )
            messages.error(request, compose_save_error_message(exc))
            if settings.DEBUG:
                messages.error(request, f"詳細（DEBUG）: {type(exc).__name__}: {exc}")
            return _board_redirect(request)
        link = timeline_post_link(post)
        notify_mentions(body=post.body, actor=request.user, link=link)
        if post.image:
            messages.success(request, "写真付きのつぶやきを投稿しました。")
        elif post.quoted_post_id:
            messages.success(request, "引用投稿しました。")
        else:
            messages.success(request, "つぶやきを投稿しました。")
        return _board_redirect(request, post_id=post.pk)
    else:
        _log_auth_debug("BOARD COMPOSE", f"errors={form.errors.as_json()}")
        log_media_upload(
            "BOARD COMPOSE VALIDATION",
            (
                f"errors={form.errors.as_json()} "
                f"POST_keys={list(request.POST.keys())} "
                f"FILES_keys={list(request.FILES.keys())} "
                f"FILES=[{'; '.join(f'{k}={describe_uploaded_file(v)}' for k, v in request.FILES.items()) or 'none'}]"
            ),
        )
        messages.error(request, "投稿に失敗しました。内容を確認してください。")
        for field, errors in form.errors.items():
            for error in errors:
                messages.error(request, f"{field}: {error}")
    return _board_redirect(request)


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
def board_timeline_bookmark(request, pk):
    post = get_object_or_404(TimelinePost, pk=pk, is_removed=False)
    try:
        bookmarked = toggle_bookmark(request.user, post.pk)
    except BookmarkServiceError:
        messages.error(
            request,
            "ブックマーク機能は現在利用できません。しばらくしてからお試しください。",
        )
    else:
        if bookmarked:
            messages.success(request, "ブックマークに追加しました。")
        else:
            messages.success(request, "ブックマークを解除しました。")
    next_url = request.POST.get("next") or request.META.get("HTTP_REFERER")
    if next_url:
        return redirect(next_url)
    return _board_redirect(request, tag=post.course_name)


@login_required
@require_GET
def board_quote(request, pk):
    post = get_quotable_post(pk, request.user)
    if not post:
        messages.error(request, "この投稿は引用できません。")
        return redirect(reverse("home"))
    return redirect(f"{reverse('home')}?quote={post.pk}")


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
        link = timeline_post_link(post)
        if post.author_id and post.author_id != request.user.id:
            Notification.objects.create(
                recipient=post.author,
                message=(
                    f"「{request.user.username}さんが"
                    "あなたの投稿にコメントしました」"
                ),
                link=link,
            )
        notify_mentions(
            body=comment.body,
            actor=request.user,
            link=link,
            exclude_user_ids={post.author_id} if post.author_id else None,
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
    return redirect(build_home_url(active_tag=tag))


@login_required
@require_POST
def delete_comment(request, pk):
    comment = get_object_or_404(
        Comment.objects.select_related("timeline_post"),
        pk=pk,
    )
    timeline_post = comment.timeline_post
    tag = (timeline_post.course_name or "") if timeline_post else ""
    post_id = timeline_post.pk if timeline_post else None

    if comment.author_id != request.user.id:
        messages.error(request, "このコメントを削除する権限がありません。")
        if post_id:
            return _board_redirect(request, tag=tag, post_id=post_id)
        return redirect(reverse("home"))

    comment.delete()
    messages.success(request, "コメントを削除しました。")
    if post_id:
        return _board_redirect(request, tag=tag, post_id=post_id)
    return redirect(reverse("home"))


def _pwa_icon_url(request, filename: str) -> str:
    return request.build_absolute_uri(f"{settings.STATIC_URL}pwa/{filename}")


@require_GET
def pwa_manifest(request):
    """Web App Manifest（/manifest.json）"""
    manifest = {
        "name": settings.PWA_APP_NAME,
        "short_name": settings.PWA_SHORT_NAME,
        "description": settings.PWA_DESCRIPTION,
        "start_url": request.build_absolute_uri(reverse("home")),
        "scope": request.build_absolute_uri("/"),
        "display": "standalone",
        "orientation": "portrait-primary",
        "background_color": settings.PWA_BACKGROUND_COLOR,
        "theme_color": settings.PWA_THEME_COLOR,
        "lang": "ja",
        "icons": [
            {
                "src": _pwa_icon_url(request, "icon-192.png"),
                "sizes": "192x192",
                "type": "image/png",
                "purpose": "any",
            },
            {
                "src": _pwa_icon_url(request, "icon-512.png"),
                "sizes": "512x512",
                "type": "image/png",
                "purpose": "any",
            },
            {
                "src": _pwa_icon_url(request, "icon-512.png"),
                "sizes": "512x512",
                "type": "image/png",
                "purpose": "maskable",
            },
        ],
    }
    return HttpResponse(
        json.dumps(manifest, ensure_ascii=False),
        content_type="application/manifest+json; charset=utf-8",
    )


@require_GET
@cache_control(max_age=3600, public=True)
def ads_txt(request):
    """Google AdSense 用 ads.txt（/ads.txt）"""
    ads_path = settings.BASE_DIR / "ads.txt"
    content = ads_path.read_text(encoding="utf-8")
    return HttpResponse(content, content_type="text/plain; charset=utf-8")


def privacy_policy(request):
    return render(request, "privacy.html")


def terms_of_service(request):
    return render(request, "terms.html")


@require_GET
@cache_control(max_age=0, no_cache=True, no_store=True, must_revalidate=True)
def pwa_service_worker(request):
    """Service Worker（/service-worker.js）"""
    sw_path = settings.BASE_DIR / "static" / "pwa" / "service-worker.js"
    content = sw_path.read_text(encoding="utf-8")
    return HttpResponse(content, content_type="application/javascript; charset=utf-8")


@login_required
@require_POST
def register_push_token(request):
    """Capacitor が取得したデバイストークンを保存・更新する。"""
    if request.content_type == "application/json":
        try:
            payload = json.loads(request.body.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return JsonResponse({"error": "invalid_json"}, status=400)
    else:
        payload = request.POST

    token = (payload.get("token") or "").strip()
    if not token:
        return JsonResponse({"error": "token_required"}, status=400)

    platform = (payload.get("platform") or "ios").strip()

    from .push_services import register_device_token

    try:
        device = register_device_token(request.user, token, platform=platform)
    except ValueError:
        return JsonResponse({"error": "token_required"}, status=400)

    return JsonResponse(
        {
            "ok": True,
            "platform": device.platform,
            "updated_at": device.updated_at.isoformat(),
        }
    )


def logout_view(request):
    logout(request)
    return redirect(settings.LOGOUT_REDIRECT_URL)
