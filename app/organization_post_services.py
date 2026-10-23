"""団体名義タイムライン投稿の認可・シリアライズ（Phase 2-A）。

AccountContext / localStorage は見ない。サーバー側の所属を毎回確認する。
団体投稿の操作 User は author に残し、公開 JSON には出さない。
"""

from __future__ import annotations

from typing import Any

from django.conf import settings
from django.contrib.auth.models import AbstractBaseUser
from django.db.models import Q, QuerySet

from .models import Organization, TimelinePost
from .organization_api_services import get_organization_avatar_url
from .organization_services import (
    can_list_organization,
    can_manage_organization,
    can_view_organization_profile,
    is_organization_admin,
)

ORG_PROFILE_POSTS_PAGE = 20


class OrganizationPostError(ValueError):
    def __init__(self, code: str, *, status: int = 400, message: str = ""):
        self.code = code
        self.status = status
        super().__init__(message or code)


def org_timeline_posts_are_public() -> bool:
    """本番一般公開は統合テスト後。default False を維持する。"""
    return bool(getattr(settings, "WASE_ORG_TIMELINE_POSTS_PUBLIC", False))


def is_organization_timeline_post(post: TimelinePost | None) -> bool:
    return bool(post is not None and getattr(post, "organization_id", None))


def organization_posts_are_publicly_listable(organization: Organization | None) -> bool:
    """タイムライン/検索に団体投稿を載せるか。フラグ × active × is_listed。"""
    return org_timeline_posts_are_public() and can_list_organization(organization)


def organization_post_is_publicly_listed(post: TimelinePost | None) -> bool:
    if not is_organization_timeline_post(post):
        return False
    organization = getattr(post, "organization", None)
    if organization is None and post.organization_id:
        organization = Organization.objects.filter(pk=post.organization_id).first()
    return organization_posts_are_publicly_listable(organization)


def filter_public_organization_posts(qs: QuerySet[TimelinePost]) -> QuerySet[TimelinePost]:
    """公開フィード用。draft/suspended/未掲載の団体投稿は出さない。"""
    if not org_timeline_posts_are_public():
        return qs.filter(organization_id__isnull=True)
    return qs.filter(
        Q(organization_id__isnull=True)
        | Q(
            organization__status=Organization.Status.ACTIVE,
            organization__is_listed=True,
        )
    )


def filter_timeline_posts_by_faculty(
    qs: QuerySet[TimelinePost], faculty: str
) -> QuerySet[TimelinePost]:
    """団体投稿に学部は無い。学部タブでは個人投稿だけ残す。"""
    value = (faculty or "").strip()
    if not value:
        return qs
    return qs.filter(
        Q(organization_id__isnull=True)
        & (Q(author__profile__department=value) | Q(faculty=value))
    )


def parse_organization_id(raw) -> int | None:
    if raw is None:
        return None
    if isinstance(raw, str):
        value = raw.strip()
        if not value:
            return None
        raw = value
    try:
        organization_id = int(raw)
    except (TypeError, ValueError):
        raise OrganizationPostError("invalid_organization_id", status=400)
    if organization_id <= 0:
        raise OrganizationPostError("invalid_organization_id", status=400)
    return organization_id


def resolve_posting_organization(
    actor: AbstractBaseUser | None,
    organization_id: int | None,
) -> Organization | None:
    """投稿主体の団体。None なら個人投稿。権限はサーバー側で毎回確認する。"""
    if organization_id is None:
        return None
    organization = Organization.objects.filter(pk=organization_id).first()
    if organization is None:
        raise OrganizationPostError("organization_not_found", status=404)
    if not can_manage_organization(actor, organization):
        raise OrganizationPostError("forbidden", status=403)
    return organization


def user_can_delete_timeline_post(
    user: AbstractBaseUser | None,
    post: TimelinePost | None,
) -> bool:
    """個人投稿は本人のみ。author_id が None の個人投稿は API から消せない。

    団体投稿は owner/admin が削除可能。suspended でも所属管理者は削除できる
    （新規投稿は can_manage により不可）。staff ショートカットは無い。
    """
    if (
        user is None
        or post is None
        or not getattr(user, "pk", None)
        or not getattr(user, "is_authenticated", False)
        or not getattr(user, "is_active", False)
    ):
        return False
    if post.organization_id:
        organization = getattr(post, "organization", None)
        if organization is None:
            organization = Organization.objects.filter(pk=post.organization_id).first()
        return is_organization_admin(user, organization)
    if post.author_id is None:
        return False
    return post.author_id == user.pk


def serialize_post_organization(organization: Organization | None) -> dict[str, Any] | None:
    if organization is None or not getattr(organization, "pk", None):
        return None
    return {
        "id": organization.pk,
        "name": organization.name,
        "slug": organization.slug,
        "avatar_url": get_organization_avatar_url(organization),
        "is_verified": bool(organization.is_verified),
    }


def viewer_can_see_organization_post(
    viewer: AbstractBaseUser | None,
    post: TimelinePost | None,
) -> bool:
    """フラグOFF時の詳細GET例外。公開フィードには使わない。"""
    if not is_organization_timeline_post(post):
        return False
    if getattr(post, "is_removed", False):
        return False
    organization = getattr(post, "organization", None)
    if organization is None and post.organization_id:
        organization = Organization.objects.filter(pk=post.organization_id).first()
    return is_organization_admin(viewer, organization)


def organization_post_visibility(post: TimelinePost | None) -> str:
    if organization_post_is_publicly_listed(post):
        return "public"
    return "organization_preview"


def build_organization_posts_payload(
    organization: Organization | None,
    viewer: AbstractBaseUser | None,
    *,
    offset: int = 0,
    limit: int = ORG_PROFILE_POSTS_PAGE,
) -> dict[str, Any] | None:
    """団体プロフィールの投稿一覧。プロフィール閲覧不可なら None（404）。"""
    if organization is None or not can_view_organization_profile(viewer, organization):
        return None

    page_size = max(1, min(int(limit or ORG_PROFILE_POSTS_PAGE), 50))
    start = max(0, int(offset or 0))
    public = organization_posts_are_publicly_listable(organization)
    preview = not public
    if preview and not is_organization_admin(viewer, organization):
        return {
            "ok": True,
            "posts": [],
            "has_more": False,
            "next_offset": 0,
            "total_count": 0,
            "preview": False,
            "unpublished": True,
        }

    from .bookmark_services import prepare_timeline_posts
    from .comment_thread_services import timeline_comments_prefetch
    from .timeline_api_services import serialize_timeline_post

    queryset = (
        TimelinePost.objects.select_related(
            "author",
            "author__profile",
            "organization",
            "quoted_post",
            "quoted_post__author",
            "quoted_post__author__profile",
            "quoted_post__organization",
            "shared_product",
        )
        .prefetch_related(timeline_comments_prefetch())
        .filter(organization=organization, is_removed=False)
        .order_by("-created_at")
    )
    total = queryset.count()
    page = list(queryset[start : start + page_size])
    prepared = prepare_timeline_posts(page, viewer)
    posts = [
        serialize_timeline_post(post, viewer, include_comments=False)
        for post in prepared
    ]
    next_offset = start + len(posts)
    return {
        "ok": True,
        "posts": posts,
        "has_more": next_offset < total,
        "next_offset": next_offset,
        "total_count": total,
        "preview": preview,
        "unpublished": preview,
    }
