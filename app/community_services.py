from django.db import transaction
from django.db.models import Count, Exists, OuterRef, Q
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils import timezone
from urllib.parse import urlencode

from .constants import FACULTY_CHOICES
from .models import Community, CommunityThread, CommunityThreadReply
from .ugc_services import get_either_blocked_user_ids, is_either_blocked


class CommunityInteractionBlocked(Exception):
    """Bilateral block forbids this Community write."""

    code = "blocked"


def build_communities_index_url(*, tag="", query=""):
    params = {}
    if tag:
        params["tag"] = tag
    if query:
        params["q"] = query
    base = reverse("communities_index")
    if not params:
        return base
    return f"{base}?{urlencode(params)}"


def _thread_queryset_base():
    return CommunityThread.objects.filter(
        is_removed=False,
        community__is_active=True,
    )


def _annotate_thread_queryset(queryset, blocked_ids=None):
    reply_filter = Q(replies__is_removed=False)
    if blocked_ids:
        reply_filter &= ~Q(replies__author_id__in=blocked_ids)
    return (
        queryset.select_related("author", "author__profile", "community")
        .annotate(
            replies_count=Count(
                "replies",
                filter=reply_filter,
                distinct=True,
            )
        )
        .order_by("-created_at")
    )


def _apply_thread_search(queryset, query, blocked_ids=None):
    query = (query or "").strip()
    if not query:
        return queryset
    reply_hits = CommunityThreadReply.objects.filter(
        thread_id=OuterRef("pk"),
        is_removed=False,
        body__icontains=query,
    )
    if blocked_ids:
        reply_hits = reply_hits.exclude(author_id__in=blocked_ids)
    return queryset.filter(
        Q(title__icontains=query)
        | Q(body__icontains=query)
        | Exists(reply_hits)
    )


def list_community_threads(*, query="", faculty="", viewer=None):
    queryset = _thread_queryset_base()
    faculty = (faculty or "").strip()
    if faculty:
        queryset = queryset.filter(community__faculty=faculty)
    blocked_ids = get_either_blocked_user_ids(viewer)
    queryset = _apply_thread_search(queryset, query, blocked_ids=blocked_ids)
    if blocked_ids:
        queryset = queryset.exclude(author_id__in=blocked_ids)
    return _annotate_thread_queryset(queryset, blocked_ids=blocked_ids)


def get_community_for_new_thread(*, faculty=""):
    faculty = (faculty or "").strip()
    if faculty:
        community = Community.objects.filter(
            is_active=True,
            category=Community.Category.FACULTY,
            faculty=faculty,
        ).first()
        if community:
            return community
    return (
        Community.objects.filter(
            is_active=True,
            category=Community.Category.GENERAL,
        )
        .order_by("sort_order", "name")
        .first()
    )


def get_faculty_tag_choices():
    return [{"value": "", "label": "すべて"}] + [
        {"value": value, "label": label} for value, label in FACULTY_CHOICES
    ]


def seed_communities():
    """管理コマンド・マイグレーション用の初期掲示板データ。"""
    now = timezone.now()
    seeds = [
        {
            "slug": "commerce",
            "name": "商学部板",
            "description": "商学部の履修・ゼミ・キャリアの話題",
            "category": Community.Category.FACULTY,
            "faculty": "商学部",
            "latest_thread_title": "2年生おすすめの経営系科目は？",
            "latest_thread_preview": "来学期の履修登録前に相談したいです。英語科目とのバランスも…",
            "sort_order": 10,
        },
        {
            "slug": "law",
            "name": "法学部板",
            "description": "法学部の授業・司法試験・学習法",
            "category": Community.Category.FACULTY,
            "faculty": "法学部",
            "latest_thread_title": "憲法のレポート構成について",
            "latest_thread_preview": "判例の読み方がまだ慣れなくて、構成案を見てほしいです。",
            "sort_order": 20,
        },
        {
            "slug": "polisci",
            "name": "政治経済学部板",
            "description": "政経の授業・ゼミ・インターン情報",
            "category": Community.Category.FACULTY,
            "faculty": "政治経済学部",
            "latest_thread_title": "ゼミ配属の雰囲気を教えてください",
            "latest_thread_preview": "志望ゼミを絞り込み中です。面接で聞かれがちなことを知りたいです。",
            "sort_order": 30,
        },
        {
            "slug": "science-tech",
            "name": "理工系板",
            "description": "基幹・創造・先進理工の履修と研究室",
            "category": Community.Category.FACULTY,
            "faculty": "基幹理工学部",
            "latest_thread_title": "線形代数の復習方法",
            "latest_thread_preview": "中間の点数が微妙でした。おすすめの問題集ありますか？",
            "sort_order": 40,
        },
        {
            "slug": "thesis",
            "name": "卒論・レポート相談板",
            "description": "卒論・レポートのテーマ選びと進め方",
            "category": Community.Category.GENERAL,
            "latest_thread_title": "卒論テーマが全然決まらない",
            "latest_thread_preview": "指導教員に何を聞けばいいかも分からず困っています…",
            "sort_order": 50,
        },
        {
            "slug": "seminar",
            "name": "ゼミ選び相談板",
            "description": "ゼミ配属・面接・先輩の体験談",
            "category": Community.Category.COURSE,
            "latest_thread_title": "3年から研究室に入るメリット",
            "latest_thread_preview": "早期配属を考えているのですが、研究と就活の両立が不安です。",
            "sort_order": 60,
        },
        {
            "slug": "career",
            "name": "インターン・就活板",
            "description": "インターン選考・ES・面接の情報交換",
            "category": Community.Category.GENERAL,
            "latest_thread_title": "サマーインターンの選考時期",
            "latest_thread_preview": "各社の選考スケジュールを共有できると助かります。",
            "sort_order": 70,
        },
    ]
    for item in seeds:
        Community.objects.update_or_create(
            slug=item["slug"],
            defaults={
                **item,
                "latest_activity_at": now,
                "is_active": True,
            },
        )




def create_community_thread(community, user, title, body):
    with transaction.atomic():
        thread = CommunityThread.objects.create(
            community=community,
            author=user,
            title=title,
            body=body,
        )
        community.latest_thread_title = thread.title[:120]
        community.latest_thread_preview = thread.body[:200]
        community.latest_activity_at = timezone.now()
        community.save(
            update_fields=[
                "latest_thread_title",
                "latest_thread_preview",
                "latest_activity_at",
                "updated_at",
            ]
        )
    return thread


def get_community_thread(community, thread_pk, viewer=None):
    qs = CommunityThread.objects.select_related(
        "community",
        "author",
        "author__profile",
    ).filter(
        pk=thread_pk,
        community=community,
        is_removed=False,
    )
    blocked_ids = get_either_blocked_user_ids(viewer)
    if blocked_ids:
        qs = qs.exclude(author_id__in=blocked_ids)
    return get_object_or_404(qs)


def create_thread_reply(thread, user, body, *, reply_to=None):
    if is_either_blocked(user, getattr(thread, "author", None)):
        raise CommunityInteractionBlocked()
    if reply_to is not None and is_either_blocked(
        user, getattr(reply_to, "author", None)
    ):
        raise CommunityInteractionBlocked()
    with transaction.atomic():
        reply = CommunityThreadReply.objects.create(
            thread=thread,
            author=user,
            body=body,
            reply_to=reply_to,
        )
        now = timezone.now()
        thread.updated_at = now
        thread.save(update_fields=["updated_at"])
        community = thread.community
        community.latest_thread_title = thread.title[:120]
        community.latest_thread_preview = body[:200]
        community.latest_activity_at = now
        community.save(
            update_fields=[
                "latest_thread_title",
                "latest_thread_preview",
                "latest_activity_at",
                "updated_at",
            ]
        )
    return reply


def resolve_reply_to_for_thread(thread, reply_to_id, viewer=None):
    """同一スレッド内の返信先を検証。無効なら ValueError('invalid_reply_to')。"""
    if reply_to_id is None or reply_to_id == "":
        return None
    try:
        target_id = int(reply_to_id)
    except (TypeError, ValueError) as exc:
        raise ValueError("invalid_reply_to") from exc
    if target_id <= 0:
        raise ValueError("invalid_reply_to")
    target = (
        CommunityThreadReply.objects.select_related("author", "author__profile")
        .filter(pk=target_id, thread_id=thread.pk)
        .first()
    )
    if target is None:
        raise ValueError("invalid_reply_to")
    if is_either_blocked(viewer, getattr(target, "author", None)):
        raise ValueError("invalid_reply_to")
    return target


def notify_community_reply(
    *,
    reply: CommunityThreadReply,
    thread: CommunityThread,
) -> None:
    """返信先の著者（なければスレッド主）へ通知。自己通知は作らない。"""
    from .models import Notification
    from .services import user_display_name

    actor_name = user_display_name(reply.author)
    recipient = None
    message = ""
    if reply.reply_to_id:
        parent = reply.reply_to
        if parent is not None and not parent.is_removed and parent.author_id:
            recipient = parent.author
            message = f"{actor_name}さんがあなたの発言に返信しました"
    if recipient is None and thread.author_id:
        recipient = thread.author
        title = (thread.title or "スレッド")[:40]
        message = f"{actor_name}さんが「{title}」に返信しました"
    if recipient is None or recipient.pk == reply.author_id:
        return
    if is_either_blocked(reply.author, recipient):
        return
    slug = thread.community.slug
    link = f"/app/communities/{slug}/threads/{thread.pk}#reply-{reply.pk}"
    Notification.objects.create(
        recipient=recipient,
        message=message,
        link=link,
    )


def can_delete_community_content(user, author_id: int) -> bool:
    if not getattr(user, "is_authenticated", False):
        return False
    if user.pk == author_id:
        return True
    return bool(getattr(user, "is_staff", False) or getattr(user, "is_superuser", False))


def can_edit_community_reply(user, reply: CommunityThreadReply) -> bool:
    if not getattr(user, "is_authenticated", False):
        return False
    if reply.is_removed:
        return False
    return user.pk == reply.author_id


def _refresh_community_latest_activity(community: Community) -> None:
    latest_thread = (
        CommunityThread.objects.filter(community=community, is_removed=False)
        .order_by("-created_at")
        .first()
    )
    if latest_thread is None:
        community.latest_thread_title = ""
        community.latest_thread_preview = ""
        community.latest_activity_at = timezone.now()
        community.save(
            update_fields=[
                "latest_thread_title",
                "latest_thread_preview",
                "latest_activity_at",
                "updated_at",
            ]
        )
        return

    latest_reply = (
        CommunityThreadReply.objects.filter(
            thread=latest_thread,
            is_removed=False,
        )
        .order_by("-created_at")
        .first()
    )
    if latest_reply is not None:
        preview = latest_reply.body[:200]
        activity_at = latest_reply.created_at
    else:
        preview = latest_thread.body[:200]
        activity_at = latest_thread.created_at

    community.latest_thread_title = latest_thread.title[:120]
    community.latest_thread_preview = preview
    community.latest_activity_at = activity_at
    community.save(
        update_fields=[
            "latest_thread_title",
            "latest_thread_preview",
            "latest_activity_at",
            "updated_at",
        ]
    )


def soft_remove_community_thread(thread: CommunityThread) -> None:
    with transaction.atomic():
        thread.is_removed = True
        thread.save(update_fields=["is_removed", "updated_at"])
        _refresh_community_latest_activity(thread.community)


def soft_remove_community_reply(reply: CommunityThreadReply) -> None:
    reply.is_removed = True
    reply.save(update_fields=["is_removed"])


def update_community_reply(reply: CommunityThreadReply, body: str) -> None:
    reply.body = body
    reply.save(update_fields=["body"])


def get_community_reply(community, thread_pk, reply_pk, viewer=None):
    thread = get_community_thread(community, thread_pk, viewer=viewer)
    return get_object_or_404(
        CommunityThreadReply.objects.select_related(
            "author",
            "author__profile",
            "reply_to",
            "reply_to__author",
            "reply_to__author__profile",
            "thread",
        ),
        pk=reply_pk,
        thread=thread,
    )


def list_replies_for_thread(
    thread, *, include_removed=True, viewer=None, blocked_ids=None
):
    queryset = thread.replies.select_related(
        "author",
        "author__profile",
        "reply_to",
        "reply_to__author",
        "reply_to__author__profile",
    ).order_by("created_at", "pk")
    if not include_removed:
        queryset = queryset.filter(is_removed=False)
    ids = (
        blocked_ids
        if blocked_ids is not None
        else get_either_blocked_user_ids(viewer)
    )
    if ids:
        queryset = queryset.exclude(author_id__in=ids)
    return queryset


def count_visible_replies_for_thread(thread, viewer=None, blocked_ids=None) -> int:
    queryset = thread.replies.filter(is_removed=False)
    ids = (
        blocked_ids
        if blocked_ids is not None
        else get_either_blocked_user_ids(viewer)
    )
    if ids:
        queryset = queryset.exclude(author_id__in=ids)
    return queryset.count()


def reply_numbers_for_thread(replies) -> dict[int, int]:
    """soft-delete 行も含めた作成順でスレッド内番号を振る（安定）。"""
    return {reply.pk: index for index, reply in enumerate(replies, start=1)}


def reply_numbers_for_thread_all(thread) -> dict[int, int]:
    """Viewer 非依存の番号。blocked 行も含めて欠番を維持する。"""
    pks = thread.replies.order_by("created_at", "pk").values_list("pk", flat=True)
    return {pk: index for index, pk in enumerate(pks, start=1)}
