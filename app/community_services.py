from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone

from .models import Community, CommunityThread, CommunityThreadReply


def list_communities_for_index():
    return (
        Community.objects.filter(is_active=True)
        .order_by("sort_order", "name")
    )


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


def list_threads_for_community(community):
    return (
        community.threads.filter(is_removed=False)
        .select_related("author", "author__profile")
        .annotate(replies_count=Count("replies", filter=Q(replies__is_removed=False)))
        .order_by("-created_at")
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


def get_community_thread(community, thread_pk):
    return get_object_or_404(
        CommunityThread.objects.select_related(
            "community",
            "author",
            "author__profile",
        ),
        pk=thread_pk,
        community=community,
        is_removed=False,
    )


def list_replies_for_thread(thread):
    return (
        thread.replies.filter(is_removed=False)
        .select_related("author", "author__profile")
        .order_by("created_at")
    )


def create_thread_reply(thread, user, body):
    with transaction.atomic():
        reply = CommunityThreadReply.objects.create(
            thread=thread,
            author=user,
            body=body,
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
