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
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.cache import cache_control
from django.views.decorators.http import require_GET, require_POST
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse

from .account_deletion_services import delete_user_account
from .report_notification_services import notify_moderation_team_of_report
from .community_services import (
    build_communities_index_url,
    can_delete_community_content,
    can_edit_community_reply,
    count_visible_replies_for_thread,
    create_community_thread as save_community_thread,
    create_thread_reply as save_thread_reply,
    get_community_for_new_thread,
    get_community_reply,
    get_community_thread,
    get_faculty_tag_choices,
    list_community_threads,
    list_replies_for_thread,
    soft_remove_community_reply,
    soft_remove_community_thread,
    update_community_reply,
)
from .constants import FACULTY_CHOICES
from .mention_services import notify_mentions
from .dm_services import (
    build_dm_conversations,
    build_dm_unread_summary,
    can_access_dm_room,
    dm_room_link,
    find_dm_room,
    get_or_create_dm_room,
    list_dm_read_message_ids_for_sender,
    mark_dm_room_read,
)
from .group_chat_services import (
    assign_default_group_name,
    can_access_group_room,
    group_room_link,
    mark_group_room_read,
)
from .inbox_services import build_inbox_conversations, build_inbox_unread_summary
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
    ChatMessage,
    ChatRoom,
    ChatRoomMembership,
    ContentReport,
    Follow,
    Notification,
    Product,
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
from .notification_services import (
    get_unread_notification_count,
    mark_all_notifications_read,
)
from .timetable_services import build_timetable_grid
from .timetable_privacy_services import (
    get_or_create_profile as get_or_create_timetable_profile,
    is_timetable_public_for,
    is_timetable_public_value,
    set_timetable_public,
    toggle_timetable_public,
)
from .search_api_services import run_scoped_search
from .otp_services import (
    EmailConfigurationError,
    SIGNUP_PENDING_SESSION_KEY,
    create_and_send_signup_otp,
    get_email_config_errors,
    verify_signup_otp,
)

logger = logging.getLogger(__name__)
from .services import (
    SEARCH_TAB_ALL,
    SEARCH_TAB_LATEST,
    SEARCH_TAB_USERS,
    build_home_url,
    build_search_url,
    get_following_user_ids,
    get_profile_stats,
    get_user_avatar_url,
    get_user_faculty,
    get_user_rating_stats,
    is_following,
    normalize_search_tab,
    search_timeline_posts,
    search_users,
    user_avatar_initial,
    user_display_name,
)
from .ugc_services import (
    block_user,
    filter_visible_products,
    filter_visible_timeline_posts,
    get_blocked_users,
    get_report_target,
    get_reported_user_id,
    is_either_blocked,
    is_user_blocked,
    unblock_user,
)
User = get_user_model()


def _serialize_room_message(message, current_user_id, *, anonymize_partner: bool = False):
    created = timezone.localtime(message.created_at)
    is_mine = message.sender_id == current_user_id
    if anonymize_partner and not is_mine:
        return {
            "id": message.pk,
            "sender_id": message.sender_id,
            "sender_name": "不明なユーザー",
            "sender_initial": "?",
            "avatar_url": "",
            "body": message.body,
            "created_at": created.strftime("%m/%d %H:%M"),
            "is_mine": False,
            "is_read": message.is_read,
        }

    avatar_url = get_user_avatar_url(message.sender)
    return {
        "id": message.pk,
        "sender_id": message.sender_id,
        "sender_name": user_display_name(message.sender),
        "sender_initial": user_avatar_initial(message.sender),
        "avatar_url": avatar_url or "",
        "body": message.body,
        "created_at": created.strftime("%m/%d %H:%M"),
        "is_mine": is_mine,
        "is_read": message.is_read,
    }


def _dm_block_flags(viewer, partner) -> tuple[bool, bool]:
    """(自分が相手をブロックしているか, 双方向いずれかで送信不可か)。"""
    if partner is None:
        return False, False
    is_blocked = is_user_blocked(viewer, partner)
    messaging_blocked = is_either_blocked(viewer, partner)
    return is_blocked, messaging_blocked


def _room_messages_json(request, room):
    message_queryset = room.messages
    after = request.GET.get("after", "").strip()
    messages_qs = message_queryset.select_related("sender").order_by("created_at")
    if after.isdigit():
        messages_qs = messages_qs.filter(pk__gt=int(after))

    latest_id = (
        message_queryset.order_by("-pk").values_list("pk", flat=True).first() or 0
    )
    partner = room.other_user(request.user)
    is_blocked, messaging_blocked = _dm_block_flags(request.user, partner)
    return JsonResponse(
        {
            "messages": [
                _serialize_room_message(
                    message,
                    request.user.id,
                    anonymize_partner=is_blocked,
                )
                for message in messages_qs
            ],
            "latest_id": latest_id,
            "read_message_ids": list_dm_read_message_ids_for_sender(
                room, request.user
            ),
            "is_blocked": is_blocked,
            "can_send": not messaging_blocked,
        }
    )


def _serialize_group_message(message, current_user_id):
    created = timezone.localtime(message.created_at)
    avatar_url = get_user_avatar_url(message.sender)
    return {
        "id": message.pk,
        "sender_id": message.sender_id,
        "sender_name": user_display_name(message.sender),
        "sender_initial": user_avatar_initial(message.sender),
        "avatar_url": avatar_url or "",
        "body": message.body,
        "created_at": created.strftime("%m/%d %H:%M"),
        "is_mine": message.sender_id == current_user_id,
    }


def _group_messages_json(request, room):
    message_queryset = room.chat_messages
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
                _serialize_group_message(message, request.user.id)
                for message in messages_qs
            ],
            "latest_id": latest_id,
        }
    )


def index(request):
    tab = request.GET.get("tab", "").strip().lower()
    if tab == "flea":
        params = request.GET.copy()
        params.pop("tab", None)
        url = reverse("flea_index")
        encoded = params.urlencode()
        if encoded:
            url = f"{url}?{encoded}"
        return redirect(url)
    if tab:
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
            "timeline_ad_offset": offset,
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


@require_GET
def get_latest_posts(request):
    """タイムライン先頭の最新投稿（プル・トゥ・リフレッシュ用）。"""
    timeline_qs = build_timeline_posts_queryset(request)
    total_count = timeline_qs.count()
    posts = prepare_timeline_posts(
        list(timeline_qs[:TIMELINE_INITIAL_SIZE]),
        request.user,
    )
    next_offset = len(posts)
    has_more = next_offset < total_count

    if posts:
        html = render_to_string(
            "includes/timeline_posts_batch.html",
            {
                "timeline_posts": posts,
                "query": request.GET.get("q", "").strip(),
                "timeline_ad_offset": 0,
            },
            request=request,
        )
    else:
        feed_scope = request.GET.get("feed", "all")
        feed_following_unauthenticated = (
            feed_scope == "following" and not request.user.is_authenticated
        )
        html = render_to_string(
            "includes/timeline_empty_message.html",
            {
                "feed_following_unauthenticated": feed_following_unauthenticated,
                "feed_scope": feed_scope,
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
    """投稿（すべて／最新）とユーザーをタブで検索。"""
    query = request.GET.get("q", "").strip()
    active_tab = normalize_search_tab(request.GET.get("tab"))
    viewer = request.user if request.user.is_authenticated else None
    timeline_posts = []
    users = []
    timeline_count = 0
    user_count = 0

    if query:
        if active_tab in (SEARCH_TAB_ALL, SEARCH_TAB_LATEST):
            sort = "popular" if active_tab == SEARCH_TAB_ALL else "latest"
            timeline_qs = (
                search_timeline_posts(query, viewer=viewer, sort=sort)
                .select_related(
                    "author",
                    "author__profile",
                    "quoted_post",
                    "quoted_post__author",
                )
                .prefetch_related("comments__author")
            )
            if request.user.is_authenticated:
                timeline_qs = timeline_qs.annotate(
                    user_has_liked=Exists(
                        TimelineLike.objects.filter(
                            timeline_post_id=OuterRef("pk"),
                            user_id=request.user.id,
                        )
                    )
                )
            timeline_posts = prepare_timeline_posts(timeline_qs, viewer)
            timeline_count = len(timeline_posts)
        elif active_tab == SEARCH_TAB_USERS:
            users = list(search_users(query, viewer=viewer)[:50])
            user_count = len(users)

    return render(
        request,
        "search.html",
        {
            "query": query,
            "active_tab": active_tab,
            "timeline_posts": timeline_posts,
            "timeline_count": timeline_count,
            "users": users,
            "user_count": user_count,
            "tab_urls": {
                SEARCH_TAB_ALL: build_search_url(query, SEARCH_TAB_ALL),
                SEARCH_TAB_LATEST: build_search_url(query, SEARCH_TAB_LATEST),
                SEARCH_TAB_USERS: build_search_url(query, SEARCH_TAB_USERS),
            },
            "search_url": build_search_url(query, active_tab),
            "nav_active": "search",
        },
    )


@require_GET
def api_search(request):
    """タブ共通の部分一致検索 API。GET /api/search/?q=&scope=home|communities|flea"""
    query = request.GET.get("q", "").strip()
    scope = request.GET.get("scope", "home")
    faculty = request.GET.get("faculty", "").strip() or request.GET.get("tag", "").strip()
    viewer = request.user if request.user.is_authenticated else None
    payload = run_scoped_search(query, scope, viewer=viewer, faculty=faculty)
    return JsonResponse(payload)


def more_index(request):
    return render(
        request,
        "more.html",
        {
            "nav_active": "more",
        },
    )


def timetable_index(request):
    is_own = True
    owner = request.user if request.user.is_authenticated else None
    is_public = False
    can_edit_visibility = False
    if owner is not None:
        profile = get_or_create_timetable_profile(owner)
        is_public = is_timetable_public_value(profile)
        can_edit_visibility = True

    return render(
        request,
        "timetable.html",
        {
            "nav_active": "timetable",
            "timetable": build_timetable_grid(),
            "timetable_owner": owner,
            "is_own_timetable": is_own,
            "is_timetable_public": is_public,
            "can_edit_timetable_visibility": can_edit_visibility,
            "timetable_read_only": False,
        },
    )


def timetable_user(request, pk):
    """他ユーザーの公開時間割。非公開かつ本人以外は 404。"""
    owner = get_object_or_404(User, pk=pk)
    is_own = request.user.is_authenticated and request.user.pk == owner.pk
    is_public = is_timetable_public_for(owner)
    if not is_own and not is_public:
        from django.http import Http404

        raise Http404("この時間割は非公開です。")

    if is_own:
        return redirect("timetable_index")

    return render(
        request,
        "timetable.html",
        {
            "nav_active": "timetable",
            "timetable": build_timetable_grid(),
            "timetable_owner": owner,
            "is_own_timetable": False,
            "is_timetable_public": True,
            "can_edit_timetable_visibility": False,
            "timetable_read_only": True,
            "header_back_url": reverse("user_profile", args=[owner.pk]),
            "header_title": f"{user_display_name(owner)}の時間割",
        },
    )


@login_required
@require_POST
def api_timetable_visibility(request):
    """時間割の公開/非公開を切り替える。POST /api/timetable/visibility/"""
    desired = request.POST.get("is_public")
    if desired is None and request.content_type and "application/json" in request.content_type:
        try:
            body = json.loads(request.body.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            body = {}
        desired = body.get("is_public")

    if desired is None:
        profile = toggle_timetable_public(request.user)
    else:
        if isinstance(desired, str):
            desired_bool = desired.strip().lower() in ("1", "true", "on", "yes")
        else:
            desired_bool = bool(desired)
        profile = set_timetable_public(request.user, desired_bool)

    is_public = is_timetable_public_value(profile)
    return JsonResponse(
        {
            "is_timetable_public": is_public,
            "isTimetablePublic": is_public,
            "label": "公開中" if is_public else "非公開",
        }
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
        url = build_communities_index_url(tag=active_tag)
        separator = "&" if "?" in url else "?"
        return redirect(f"{url}{separator}thread_success=1")

    error = next(iter(form.errors.values()))[0]
    messages.error(request, error)
    return redirect(build_communities_index_url(tag=active_tag))


def community_thread_detail(request, slug, thread_pk):
    community = get_object_or_404(Community, slug=slug, is_active=True)
    thread = get_community_thread(community, thread_pk)
    replies = list(list_replies_for_thread(thread, include_removed=True))
    reply_form = CommunityThreadReplyForm() if request.user.is_authenticated else None
    return render(
        request,
        "community_thread_detail.html",
        {
            "community": community,
            "thread": thread,
            "replies": replies,
            "visible_reply_count": count_visible_replies_for_thread(thread),
            "reply_form": reply_form,
            "can_delete_thread": can_delete_community_content(
                request.user, thread.author_id
            ),
            "nav_active": "communities",
        },
    )


@login_required
@require_POST
def delete_community_thread(request, slug, thread_pk):
    community = get_object_or_404(Community, slug=slug, is_active=True)
    thread = get_community_thread(community, thread_pk)
    if not can_delete_community_content(request.user, thread.author_id):
        messages.error(request, "このスレッドを削除する権限がありません。")
        return redirect(
            reverse(
                "community_thread_detail",
                kwargs={"slug": community.slug, "thread_pk": thread.pk},
            )
        )

    soft_remove_community_thread(thread)
    messages.success(request, "スレッドを削除しました。")
    return redirect(build_communities_index_url(tag=community.faculty or ""))


@login_required
@require_POST
def delete_community_thread_reply(request, slug, thread_pk, reply_pk):
    community = get_object_or_404(Community, slug=slug, is_active=True)
    reply = get_community_reply(community, thread_pk, reply_pk)
    if reply.is_removed:
        messages.info(request, "この返信はすでに削除されています。")
    elif not can_delete_community_content(request.user, reply.author_id):
        messages.error(request, "この返信を削除する権限がありません。")
    else:
        soft_remove_community_reply(reply)
        messages.success(request, "返信を削除しました。")

    return redirect(
        reverse(
            "community_thread_detail",
            kwargs={"slug": community.slug, "thread_pk": thread_pk},
        )
        + f"#reply-{reply_pk}"
    )


@login_required
@require_POST
def edit_community_thread_reply(request, slug, thread_pk, reply_pk):
    community = get_object_or_404(Community, slug=slug, is_active=True)
    reply = get_community_reply(community, thread_pk, reply_pk)
    if not can_edit_community_reply(request.user, reply):
        messages.error(request, "この返信を編集する権限がありません。")
        return redirect(
            reverse(
                "community_thread_detail",
                kwargs={"slug": community.slug, "thread_pk": thread_pk},
            )
            + f"#reply-{reply_pk}"
        )

    form = CommunityThreadReplyForm(request.POST)
    if form.is_valid():
        update_community_reply(reply, form.cleaned_data["body"])
        messages.success(request, "返信を更新しました。")
    else:
        error = next(iter(form.errors.values()))[0]
        messages.error(request, error)

    return redirect(
        reverse(
            "community_thread_detail",
            kwargs={"slug": community.slug, "thread_pk": thread_pk},
        )
        + f"#reply-{reply_pk}"
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
            + f"?thread_reply_success=1#reply-{reply.pk}"
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
    mark_all_notifications_read(request.user)

    return render(
        request,
        "notifications.html",
        {"notifications": items, "nav_active": "notifications"},
    )


@login_required
@require_GET
def notification_unread_count(request):
    return JsonResponse(
        {"unread_count": get_unread_notification_count(request.user)}
    )


@login_required
@require_POST
def notification_mark_read(request):
    marked_count = mark_all_notifications_read(request.user)
    return JsonResponse(
        {
            "ok": True,
            "unread_count": 0,
            "marked_count": marked_count,
        }
    )


@login_required
def mypage_edit(request):
    profile, _ = UserProfile.objects.get_or_create(user=request.user)

    if request.method == "POST":
        form = AccountProfileForm(
            request.POST,
            request.FILES,
            instance=profile,
            user=request.user,
        )
        if form.is_valid():
            with transaction.atomic():
                saved_profile = form.save()
            request.user.refresh_from_db()
            profile = UserProfile.objects.get(pk=saved_profile.pk)
            messages.success(
                request,
                "ニックネーム・プロフィール画像・プロフィールを更新しました。",
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
def account_settings(request):
    return render(request, "settings.html")


@login_required
def blocked_users(request):
    blocks = get_blocked_users(request.user)
    return render(
        request,
        "blocked_users.html",
        {
            "blocks": blocks,
            "nav_active": "",
        },
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


@login_required
@require_POST
def delete_account(request):
    print("DEBUG: Delete account view triggered", flush=True)
    print(
        "DEBUG: delete_account request "
        f"method={request.method} "
        f"user_id={getattr(request.user, 'pk', None)} "
        f"confirm_delete={request.POST.get('confirm_delete')!r}",
        flush=True,
    )

    confirmation = (request.POST.get("confirm_delete") or "").strip().upper()
    if confirmation != "DELETE":
        print(
            "DEBUG: delete_account rejected invalid confirmation "
            f"value={request.POST.get('confirm_delete')!r}",
            flush=True,
        )
        messages.error(
            request,
            "アカウント削除を実行するには確認ダイアログで「はい」を選択してください。",
        )
        return redirect(reverse("account_settings"))

    user = request.user
    user_id = user.pk
    user_email = user.email
    deletion_logger = logging.getLogger(__name__)

    print(
        f"DEBUG: delete_account starting deletion user_id={user_id} email={user_email}",
        flush=True,
    )

    try:
        delete_user_account(user)
    except Exception as exc:
        print(
            f"DEBUG: delete_account exception user_id={user_id} "
            f"type={type(exc).__name__} error={exc}",
            flush=True,
        )
        traceback.print_exc()
        sys.stdout.flush()
        sys.stderr.flush()
        deletion_logger.error(
            "Account deletion failed for user_id=%s email=%s: %s (%s)",
            user_id,
            user_email,
            exc,
            type(exc).__name__,
            exc_info=True,
        )
        messages.error(
            request,
            "アカウントの削除に失敗しました。しばらくしてからもう一度お試しください。",
        )
        return redirect(reverse("account_settings"))

    user_still_exists = get_user_model().objects.filter(pk=user_id).exists()
    print(
        f"DEBUG: delete_account post-delete check user_id={user_id} "
        f"still_exists={user_still_exists}",
        flush=True,
    )
    if user_still_exists:
        print(
            f"DEBUG: delete_account completed without exception but user_id={user_id} "
            "still exists in database",
            flush=True,
        )
        traceback.print_stack(file=sys.stderr)
        sys.stdout.flush()
        sys.stderr.flush()
        deletion_logger.error(
            "Account deletion incomplete for user_id=%s email=%s: user row still exists",
            user_id,
            user_email,
        )
        messages.error(
            request,
            "アカウントの削除に失敗しました。しばらくしてからもう一度お試しください。",
        )
        return redirect(reverse("account_settings"))

    logout(request)
    print(
        f"DEBUG: delete_account success user_id={user_id} email={user_email} "
        "redirecting to login",
        flush=True,
    )
    deletion_logger.info(
        "Account deletion completed and session cleared for user_id=%s email=%s",
        user_id,
        user_email,
    )
    messages.success(request, "アカウントを削除しました。ご利用ありがとうございました。")
    return redirect(reverse("login"))


def _wants_json_response(request) -> bool:
    accept = request.headers.get("Accept", "")
    if "application/json" in accept:
        return True
    return request.headers.get("X-Requested-With") == "XMLHttpRequest"


def _redirect_after_action(request, fallback_name: str = "home"):
    """POST の next または Referer へ戻す（なければ fallback）。"""
    allowed_hosts = {request.get_host()}
    require_https = request.is_secure()

    next_url = (request.POST.get("next") or "").strip()
    if next_url and url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts=allowed_hosts,
        require_https=require_https,
    ):
        return redirect(next_url)

    referer = (request.META.get("HTTP_REFERER") or "").strip()
    if referer and url_has_allowed_host_and_scheme(
        referer,
        allowed_hosts=allowed_hosts,
        require_https=require_https,
    ):
        return redirect(referer)

    return redirect(reverse(fallback_name))


REPORT_SUCCESS_MESSAGE = "通報しました"


@login_required
@require_POST
def submit_report(request, target_type: str, target_id: int):
    valid_target_types = {choice[0] for choice in ContentReport.TargetType.choices}
    if target_type not in valid_target_types:
        message = "通報対象の種別が不正です。"
        if _wants_json_response(request):
            return JsonResponse({"ok": False, "message": message}, status=400)
        messages.error(request, message)
        return _redirect_after_action(request)

    post_data = request.POST.copy()
    post_data["target_type"] = target_type
    post_data["target_id"] = str(target_id)
    if not post_data.get("reason"):
        post_data["reason"] = ContentReport.Reason.OTHER

    form = ContentReportForm(post_data)
    if not form.is_valid():
        if _wants_json_response(request):
            return JsonResponse({"ok": False, "errors": form.errors}, status=400)
        messages.error(request, "通報内容を確認してください。")
        return _redirect_after_action(request)

    target_type = form.cleaned_data["target_type"]
    target_id = form.cleaned_data["target_id"]
    target = get_report_target(target_type, target_id)
    if target is None:
        message = "通報対象が見つからないか、すでに削除されています。"
        if _wants_json_response(request):
            return JsonResponse({"ok": False, "message": message}, status=404)
        messages.error(request, message)
        return _redirect_after_action(request)

    reported_user_id = get_reported_user_id(target_type, target)
    if reported_user_id == request.user.pk:
        message = "自分自身のコンテンツは通報できません。"
        if _wants_json_response(request):
            return JsonResponse({"ok": False, "message": message}, status=400)
        messages.error(request, message)
        return _redirect_after_action(request)

    try:
        report = ContentReport.objects.create(
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
        return _redirect_after_action(request)

    try:
        notify_moderation_team_of_report(
            report,
            target=target,
            reported_user_id=reported_user_id,
        )
    except Exception:
        logging.getLogger(__name__).exception(
            "Failed to send moderation email for report_id=%s", report.pk
        )

    if _wants_json_response(request):
        return JsonResponse({"ok": True, "message": REPORT_SUCCESS_MESSAGE})
    messages.success(request, REPORT_SUCCESS_MESSAGE)
    return _redirect_after_action(request)


@login_required
def mypage(request):
    profile, _ = UserProfile.objects.get_or_create(user=request.user)

    return render(
        request,
        "mypage.html",
        {
            "profile": profile,
            "stats": get_profile_stats(request.user, "market"),
            "nav_active": "",
        },
    )


def user_profile(request, pk):
    profile_user = get_object_or_404(User, pk=pk)
    # 時間割公開フラグ列が未作成でも落ちないよう ensure 付きで取得
    profile = get_or_create_timetable_profile(profile_user)

    is_own_profile = request.user.is_authenticated and request.user.pk == profile_user.pk
    is_timetable_public = is_timetable_public_value(profile)
    can_view_timetable = is_own_profile or is_timetable_public

    # タブ: posts / timetable / market（bookmarks は自分のみ・サイドバー用）
    # 旧 ?from=market|thread も互換のため解釈する
    from_legacy = request.GET.get("from", "").strip().lower()
    profile_tab = request.GET.get("tab", "").strip().lower()
    if profile_tab == "overview":
        profile_tab = "market" if from_legacy == "market" else "posts"
    if profile_tab not in ("posts", "timetable", "market", "bookmarks"):
        profile_tab = "market" if from_legacy == "market" else "posts"
    if profile_tab == "bookmarks" and not is_own_profile:
        profile_tab = "posts"

    from_source = "market" if profile_tab == "market" else "thread"
    available_products = filter_visible_products(
        Product.objects.filter(
            seller=profile_user, status=Product.Status.AVAILABLE
        ).select_related("seller", "seller__profile"),
        request.user if request.user.is_authenticated else None,
    )
    rating_stats = get_user_rating_stats(profile_user)
    stats = get_profile_stats(profile_user, "thread")
    show_profile_safety_menu = (
        request.user.is_authenticated and not is_own_profile
    )
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
        can_send_dm = not is_either_blocked(request.user, profile_user)
        user_dm_room = find_dm_room(request.user, profile_user)

    bookmark_posts = []
    bookmark_meta = {}
    if profile_tab == "bookmarks" and is_own_profile:
        bookmark_posts, bookmark_meta = get_bookmarked_timeline_posts(
            profile_user, request.user
        )

    profile_posts = []
    if profile_tab == "posts":
        viewer = request.user if request.user.is_authenticated else None
        profile_posts = get_profile_timeline_posts(profile_user, viewer)

    timetable = build_timetable_grid() if profile_tab == "timetable" and can_view_timetable else None

    nav_active = ""
    if is_own_profile and profile_tab == "bookmarks":
        nav_active = "bookmarks"

    return render(
        request,
        "user_profile.html",
        {
            "profile_user": profile_user,
            "available_products": available_products,
            "rating_stats": rating_stats,
            "from_source": from_source,
            "header_back_url": reverse("home"),
            "profile": profile,
            "stats": stats,
            "is_own_profile": is_own_profile,
            "show_profile_safety_menu": show_profile_safety_menu,
            "user_is_following": user_is_following,
            "user_is_blocked": user_is_blocked,
            "can_send_dm": can_send_dm,
            "user_dm_room": user_dm_room,
            "profile_tab": profile_tab,
            "bookmark_posts": bookmark_posts,
            "bookmark_meta": bookmark_meta,
            "profile_posts": profile_posts,
            "timetable": timetable,
            "nav_active": nav_active,
            "is_timetable_public": is_timetable_public,
            "can_view_timetable": can_view_timetable,
        },
    )


@login_required
def user_dm_inbox(request):
    try:
        conversations = build_inbox_conversations(request.user)
    except Exception as exc:
        logger.warning("user_dm_inbox failed to build conversations: %s", exc)
        conversations = []
        messages.error(
            request,
            "メッセージ一覧の取得中に一部データの問題が発生しました。再読み込みしてください。",
        )
    return render(
        request,
        "dm_inbox.html",
        {
            "conversations": conversations,
            "nav_active": "dm",
            "header_back_url": reverse("home"),
        },
    )


@login_required
@require_GET
def dm_unread_summary(request):
    try:
        payload = build_inbox_unread_summary(request.user)
    except Exception as exc:
        logger.warning("dm_unread_summary failed: %s", exc)
        payload = {"total_unread": 0, "rooms": []}
    return JsonResponse(payload)


@login_required
def dm_group_create(request):
    """
    1対1 DM（UserDirectMessage）とは独立した、グループチャット作成用エンドポイント。

    最低限のグループ作成フロー（部屋作成・参加者追加）だけを実装し、
    既存 DM のロジックは一切変更しません。
    """

    following_ids = set(get_following_user_ids(request.user))
    following_ids.discard(request.user.id)

    if request.method == "POST":
        selected_raw = request.POST.getlist("member_ids")
        selected_ids: set[int] = set()
        for raw in selected_raw:
            if str(raw).isdigit():
                selected_ids.add(int(raw))

        # フォロー中ユーザーだけ許可（自己除外）
        selected_ids.discard(request.user.id)
        if not selected_ids:
            messages.error(request, "グループに追加するユーザーを選択してください。")
            return redirect(reverse("dm_group_create"))

        if not selected_ids.issubset(following_ids):
            messages.error(request, "選択されたユーザーの一部が不正です。")
            return redirect(reverse("dm_group_create"))

        try:
            with transaction.atomic():
                group_name = request.POST.get("name", "").strip()[:120]
                room = ChatRoom.objects.create(
                    kind=ChatRoom.Kind.GROUP,
                    created_by=request.user,
                    name=group_name,
                )
                memberships = [
                    ChatRoomMembership(
                        room=room,
                        user=request.user,
                        role=ChatRoomMembership.Role.OWNER,
                    )
                ]
                for user_id in selected_ids:
                    memberships.append(
                        ChatRoomMembership(
                            room=room,
                            user_id=user_id,
                            role=ChatRoomMembership.Role.MEMBER,
                        )
                    )
                ChatRoomMembership.objects.bulk_create(memberships)
                if not group_name:
                    assign_default_group_name(room)
        except IntegrityError:
            messages.error(request, "グループ作成に失敗しました（重複など）。")
            return redirect(reverse("dm_group_create"))

        messages.success(request, "グループチャットを作成しました。")
        return redirect(group_room_link(room))

    following_users = list(
        User.objects.filter(id__in=following_ids).order_by("id")
    )
    return render(
        request,
        "group_create.html",
        {
            "following_users": following_users,
            "nav_active": "dm",
            "header_back_url": reverse("user_dm_inbox"),
        },
    )


@login_required
def dm_group_room(request, room_pk):
    room = get_object_or_404(
        ChatRoom.objects.prefetch_related(
            "memberships__user__profile",
            "chat_messages__sender",
        ),
        pk=room_pk,
        kind=ChatRoom.Kind.GROUP,
    )
    if not can_access_group_room(room, request.user):
        messages.error(request, "このグループチャットにはアクセスできません。")
        return redirect(reverse("user_dm_inbox"))

    members = [
        membership.user
        for membership in room.memberships.select_related("user", "user__profile")
    ]
    group_messages = room.chat_messages.select_related("sender")
    latest_message_id = mark_group_room_read(room, request.user)
    display_name = room.name or f"グループ #{room.pk}"

    return render(
        request,
        "group_room.html",
        {
            "room": room,
            "display_name": display_name,
            "members": members,
            "group_messages": group_messages,
            "back_url": reverse("user_dm_inbox"),
            "latest_message_id": latest_message_id,
            "messages_poll_url": reverse(
                "dm_group_room_messages", kwargs={"room_pk": room.pk}
            ),
            "nav_active": "dm",
        },
    )


@login_required
@require_POST
def send_group_message(request, room_pk):
    room = get_object_or_404(ChatRoom, pk=room_pk, kind=ChatRoom.Kind.GROUP)
    if not can_access_group_room(room, request.user):
        messages.error(request, "このグループチャットにはアクセスできません。")
        return redirect(reverse("user_dm_inbox"))

    body = request.POST.get("body", "").strip()
    if not body:
        messages.error(request, "メッセージを入力してください。")
        return redirect(group_room_link(room))

    if len(body) > 500:
        messages.error(request, "メッセージが長すぎます（500文字以内）。")
        return redirect(group_room_link(room))

    ChatMessage.objects.create(
        room=room,
        sender=request.user,
        body=body,
    )
    room.save(update_fields=["updated_at"])
    return redirect(group_room_link(room))


@login_required
@require_GET
def dm_group_room_messages(request, room_pk):
    room = get_object_or_404(ChatRoom, pk=room_pk, kind=ChatRoom.Kind.GROUP)
    if not can_access_group_room(room, request.user):
        return JsonResponse({"error": "forbidden"}, status=403)

    response = _group_messages_json(request, room)
    mark_group_room_read(room, request.user)
    return response


@login_required
@require_POST
def start_user_dm(request, pk):
    partner = get_object_or_404(User, pk=pk)
    if partner.pk == request.user.pk:
        messages.error(request, "自分自身に DM は送れません。")
        return redirect(reverse("mypage"))

    if is_either_blocked(request.user, partner):
        messages.error(request, "ブロック中のユーザーとは DM を開始できません。")
        return redirect(reverse("user_profile", kwargs={"pk": pk}))

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
    is_blocked, messaging_blocked = _dm_block_flags(request.user, partner)
    dm_messages = room.messages.select_related("sender")
    latest_message_id = mark_dm_room_read(room, request.user)
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
            "is_blocked": is_blocked,
            "can_send_message": not messaging_blocked,
            "nav_active": "dm",
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

    partner = room.other_user(request.user)
    if is_either_blocked(request.user, partner):
        messages.error(request, "ブロック中のユーザーにはメッセージを送信できません。")
        return redirect(reverse("user_dm_room", kwargs={"room_pk": room.pk}))

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
    if recipient and not is_user_blocked(recipient, request.user):
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

    response = _room_messages_json(request, room)
    mark_dm_room_read(room, request.user)
    return response


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
        defaults={
            "department": faculty,
            "name": nickname,
            "terms_accepted": True,
        },
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


def _board_redirect(request, *, tag="", post_id=None, extra_query=None):
    url = build_home_url(active_tag=tag)
    if extra_query:
        from urllib.parse import urlencode

        separator = "&" if "?" in url else "?"
        url = f"{url}{separator}{urlencode(extra_query)}"
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
        return _board_redirect(
            request, post_id=post.pk, extra_query={"post_success": "1"}
        )
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
    if post.author_id is not None and post.author_id != request.user.id:
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


def support_page(request):
    return render(request, "support.html")


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
