from urllib.parse import quote

from django.contrib.auth.models import AbstractBaseUser
from django.db.models import Exists, OuterRef, Q
from django.urls import reverse

from .constants import FACULTY_CHOICES
from .models import Notification, TimelineLike, TimelinePost
from .services import get_following_user_ids
from .ugc_services import filter_visible_timeline_posts, get_blocked_user_ids

TIMELINE_INITIAL_SIZE = 25
TIMELINE_LOAD_MORE_SIZE = 15


def prepare_timeline_post_for_save(post: TimelinePost) -> TimelinePost:
    """保存前にカウンタ系フィールドへデフォルト値を明示的にセットする。"""
    if post.like_count is None:
        post.like_count = 0
    return post


def build_timeline_posts_queryset(request):
    """タイムライン一覧用の QuerySet（フィルタ・いいね状態付き）。"""
    faculty_values = {value for value, _ in FACULTY_CHOICES}
    active_faculty = request.GET.get("faculty", "").strip()
    if active_faculty not in faculty_values:
        active_faculty = ""
    active_tag = request.GET.get("tag", "").strip()
    query = request.GET.get("q", "").strip()
    feed_scope = request.GET.get("feed", "all").strip().lower()
    if feed_scope not in ("all", "following"):
        feed_scope = "all"

    timeline_posts = (
        TimelinePost.objects.select_related(
            "author",
            "author__profile",
            "quoted_post",
            "quoted_post__author",
            "quoted_post__author__profile",
        )
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
            timeline_posts = TimelinePost.objects.none()
    timeline_posts = filter_visible_timeline_posts(
        timeline_posts,
        request.user if request.user.is_authenticated else None,
    )
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
    return timeline_posts


def get_profile_timeline_posts(
    profile_user: AbstractBaseUser,
    viewer: AbstractBaseUser | None,
):
    """プロフィール画面用に、指定ユーザーの投稿一覧を表示用リストで返す。"""
    from .bookmark_services import prepare_timeline_posts

    queryset = (
        TimelinePost.objects.select_related(
            "author",
            "author__profile",
            "quoted_post",
            "quoted_post__author",
            "quoted_post__author__profile",
        )
        .prefetch_related("comments__author")
        .filter(author=profile_user, is_removed=False)
        .order_by("-created_at")
    )
    queryset = filter_visible_timeline_posts(
        queryset,
        viewer if viewer and viewer.is_authenticated else None,
    )
    if viewer and viewer.is_authenticated:
        queryset = queryset.annotate(
            user_has_liked=Exists(
                TimelineLike.objects.filter(
                    timeline_post_id=OuterRef("pk"),
                    user_id=viewer.id,
                )
            )
        )
    return prepare_timeline_posts(queryset, viewer)


def timeline_post_link(post: TimelinePost) -> str:
    base = reverse("home")
    if post.course_name:
        return f"{base}?tag={quote(post.course_name)}#post-{post.pk}"
    return f"{base}#post-{post.pk}"


def get_quotable_post(post_id: int, viewer: AbstractBaseUser | None) -> TimelinePost | None:
    """引用可能な投稿を返す（削除済み・ブロック相手は不可）。"""
    post = (
        TimelinePost.objects.select_related(
            "author",
            "author__profile",
            "quoted_post",
            "quoted_post__author",
        )
        .filter(pk=post_id, is_removed=False)
        .first()
    )
    if not post:
        return None
    if viewer and viewer.is_authenticated and post.author_id:
        blocked_ids = get_blocked_user_ids(viewer)
        if post.author_id in blocked_ids:
            return None
    return post


def notify_timeline_post_author(
    post: TimelinePost,
    actor: AbstractBaseUser,
    message: str,
) -> None:
    if not post.author_id:
        return
    if actor.is_authenticated and actor.id == post.author_id:
        return
    Notification.objects.create(
        recipient=post.author,
        message=message,
        link=timeline_post_link(post),
    )
