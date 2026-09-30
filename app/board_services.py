from django.contrib.auth.models import AbstractBaseUser
from django.db.models import Count, Exists, OuterRef, Q

from .comment_thread_services import timeline_comments_prefetch
from .constants import FACULTY_CHOICES
from .models import TimelineLike, TimelinePost
from .notification_services import create_notification
from .services import get_following_user_ids
from .ugc_services import filter_visible_timeline_posts, get_blocked_user_ids

TIMELINE_INITIAL_SIZE = 25
TIMELINE_LOAD_MORE_SIZE = 15


def annotate_timeline_quote_count(queryset):
    """リポスト（quotes）件数を quote_count として付与。"""
    return queryset.annotate(
        quote_count=Count(
            "quotes",
            filter=Q(quotes__is_removed=False),
            distinct=True,
        )
    )


def prepare_timeline_post_for_save(post: TimelinePost) -> TimelinePost:
    """保存前にカウンタ系フィールドへデフォルト値を明示的にセットする。"""
    if post.like_count is None:
        post.like_count = 0
    if post.view_count is None:
        post.view_count = 0
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
            "shared_product",
        )
        .prefetch_related(timeline_comments_prefetch())
    )
    if active_faculty:
        # 投稿に付けた学部ではなく、投稿者プロフィールの所属学部で絞り込む。
        # 旧データ互換として TimelinePost.faculty も OR する。
        timeline_posts = timeline_posts.filter(
            Q(author__profile__department=active_faculty)
            | Q(faculty=active_faculty)
        )
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
    timeline_posts = annotate_timeline_quote_count(timeline_posts)
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
            "shared_product",
        )
        .prefetch_related(timeline_comments_prefetch())
        .filter(author=profile_user, is_removed=False)
        .order_by("-created_at")
    )
    queryset = filter_visible_timeline_posts(
        queryset,
        viewer if viewer and viewer.is_authenticated else None,
    )
    queryset = annotate_timeline_quote_count(queryset)
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
    from .spa_canonical import app_absolute

    return app_absolute(f"/posts/{post.pk}")


def get_quotable_post(post_id: int, viewer: AbstractBaseUser | None) -> TimelinePost | None:
    """リポスト可能な投稿を返す（削除済み・ブロック相手・非公開は不可）。"""
    from .follow_services import can_view_private_content

    post = (
        TimelinePost.objects.select_related(
            "author",
            "author__profile",
            "quoted_post",
            "quoted_post__author",
            "shared_product",
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
    if post.author_id and not can_view_private_content(viewer, post.author):
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
    create_notification(
        recipient=post.author,
        message=message,
        link=timeline_post_link(post),
        actor=actor,
        push_kind="like",
    )


def previous_timeline_comment_participant_ids(
    *,
    post: TimelinePost,
    exclude_user_ids: set[int] | None = None,
) -> set[int]:
    """Distinct authors of currently visible (non-removed) comments on the post.

    Physically deleted comments and moderated ``is_removed=True`` comments do not
    count as participation. ``author_id`` null rows are ignored.
    """
    from .models import Comment

    exclude = set(exclude_user_ids or [])
    qs = Comment.objects.filter(
        timeline_post_id=post.pk,
        is_removed=False,
        is_author_deleted=False,
        author_id__isnull=False,
    )
    if exclude:
        qs = qs.exclude(author_id__in=exclude)
    return set(qs.values_list("author_id", flat=True).distinct())


def notify_timeline_comment(
    *,
    post: TimelinePost,
    actor: AbstractBaseUser,
    comment_body: str,
    parent_comment=None,
) -> None:
    """Notify reply target, post author, mentions, then prior participants.

    Priority for the same recipient on one comment action:
    1) parent-comment reply notification
    2) post-author comment notification
    3) mention notification
    4) participant notification

    A user never receives two notifications for the same action. Self
    notifications are skipped. Participant copy uses the same push_kind
    category (``comment``) but an explicit ``push_body`` so lock-screen
    text is not the author-only template.
    """
    from django.contrib.auth import get_user_model

    from .mention_services import notify_mentions
    from .models import Comment
    from .notification_services import notification_actor_label
    from .ugc_services import get_either_blocked_user_ids

    if not getattr(actor, "is_authenticated", False):
        return

    link = timeline_post_link(post)
    actor_label = notification_actor_label(actor)
    notified: set[int] = set()
    blocked_ids = get_either_blocked_user_ids(actor)

    parent = parent_comment if isinstance(parent_comment, Comment) else None
    parent_author_id = getattr(parent, "author_id", None) if parent else None
    if (
        parent is not None
        and parent_author_id
        and parent_author_id != actor.pk
        and not parent.is_removed
        and not parent.is_author_deleted
        and parent_author_id not in blocked_ids
    ):
        reply_message = (
            f"「{actor_label}さんがあなたのコメントに返信しました」"
        )
        create_notification(
            recipient_id=parent_author_id,
            message=reply_message,
            link=link,
            actor=actor,
            push_kind="comment",
            push_body=reply_message,
        )
        notified.add(parent_author_id)

    if (
        post.author_id
        and post.author_id != actor.pk
        and post.author_id not in notified
    ):
        create_notification(
            recipient=post.author,
            message=(
                f"「{actor_label}さんがあなたの投稿にコメントしました」"
            ),
            link=link,
            actor=actor,
            push_kind="comment",
        )
        notified.add(post.author_id)

    mentioned_ids = notify_mentions(
        body=comment_body,
        actor=actor,
        link=link,
        exclude_user_ids=set(notified),
    )
    notified.update(mentioned_ids)

    participant_ids = previous_timeline_comment_participant_ids(
        post=post,
        exclude_user_ids={actor.pk} | notified,
    )
    if not participant_ids:
        return

    # Avoid notifying users in a bilateral block with the commenter.
    participant_ids -= blocked_ids
    if not participant_ids:
        return

    active_ids = set(
        get_user_model()
        .objects.filter(pk__in=participant_ids, is_active=True)
        .values_list("pk", flat=True)
    )
    if not active_ids:
        return

    participant_message = (
        f"「{actor_label}さんがコメントした投稿に新しいコメントがあります」"
    )
    for recipient_id in active_ids:
        create_notification(
            recipient_id=recipient_id,
            message=participant_message,
            link=link,
            actor=actor,
            push_kind="comment",
            push_body=participant_message,
        )
