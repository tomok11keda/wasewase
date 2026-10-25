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


ORG_POST_VISIBILITY_PUBLIC = TimelinePost.OrganizationVisibility.PUBLIC
ORG_POST_VISIBILITY_DRAFT = TimelinePost.OrganizationVisibility.DRAFT
ORG_POST_VISIBILITY_UNLISTED = TimelinePost.OrganizationVisibility.UNLISTED
ORG_POST_SCOPE_PUBLIC = "public"
ORG_POST_SCOPE_UNPUBLISHED = "unpublished"
_WRITABLE_ORG_VISIBILITIES = frozenset(
    {ORG_POST_VISIBILITY_PUBLIC, ORG_POST_VISIBILITY_DRAFT}
)


def org_timeline_posts_are_public() -> bool:
    """互換用。公開判定は organization_visibility を使う。"""
    return bool(getattr(settings, "WASE_ORG_TIMELINE_POSTS_PUBLIC", False))


def is_organization_timeline_post(post: TimelinePost | None) -> bool:
    return bool(post is not None and getattr(post, "organization_id", None))


def organization_posts_are_publicly_listable(organization: Organization | None) -> bool:
    """団体自体が一般掲載できるか。投稿ごとの visibility とは独立。"""
    return can_list_organization(organization)


def _post_organization(post: TimelinePost | None) -> Organization | None:
    if post is None:
        return None
    organization = getattr(post, "organization", None)
    if organization is None and getattr(post, "organization_id", None):
        organization = Organization.objects.filter(pk=post.organization_id).first()
    return organization


def organization_post_is_explicitly_public(post: TimelinePost | None) -> bool:
    return (
        is_organization_timeline_post(post)
        and getattr(post, "organization_visibility", None)
        == ORG_POST_VISIBILITY_PUBLIC
    )


def organization_post_is_publicly_listed(post: TimelinePost | None) -> bool:
    if not organization_post_is_explicitly_public(post):
        return False
    return organization_posts_are_publicly_listable(_post_organization(post))


def public_organization_post_q() -> Q:
    """一般公開の団体投稿。フラグは見ない。unlisted/draft は含めない。"""
    return Q(
        organization_id__isnull=False,
        organization_visibility=ORG_POST_VISIBILITY_PUBLIC,
        organization__status=Organization.Status.ACTIVE,
        organization__is_listed=True,
    )


def filter_public_organization_posts(qs: QuerySet[TimelinePost]) -> QuerySet[TimelinePost]:
    """公開フィード用。既存 unlisted と下書き、draft/unlisted/suspended 団体は出さない。"""
    return qs.filter(Q(organization_id__isnull=True) | public_organization_post_q())


def viewer_may_access_unpublished_organization_post(
    viewer: AbstractBaseUser | None,
    post: TimelinePost | None,
) -> bool:
    """管理者プレビュー。公開フィードや通報の一般経路には使わない。"""
    return viewer_can_see_organization_post(viewer, post)


def viewer_may_report_timeline_post(
    viewer: AbstractBaseUser | None,
    post: TimelinePost | None,
) -> bool:
    """非公開団体投稿の存在を通報APIから推測させない。"""
    if post is None or getattr(post, "is_removed", False):
        return False
    if not is_organization_timeline_post(post):
        return True
    if organization_post_is_publicly_listed(post):
        return True
    return viewer_may_access_unpublished_organization_post(viewer, post)


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


def parse_requested_visibility(raw) -> str | None:
    if raw is None:
        return None
    if isinstance(raw, str):
        value = raw.strip().lower()
        if not value:
            return None
        raw = value
    else:
        raw = str(raw).strip().lower()
        if not raw:
            return None
    if raw in _WRITABLE_ORG_VISIBILITIES:
        return raw
    raise OrganizationPostError("invalid_visibility", status=400)


def visibility_for_new_organization_post(raw) -> str:
    parsed = parse_requested_visibility(raw)
    if parsed is None:
        return ORG_POST_VISIBILITY_DRAFT
    return parsed


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
    """下書き・非公開の詳細GET例外。公開フィードには使わない。"""
    if not is_organization_timeline_post(post):
        return False
    if getattr(post, "is_removed", False):
        return False
    return is_organization_admin(viewer, _post_organization(post))


def organization_post_visibility(post: TimelinePost | None) -> str:
    if not is_organization_timeline_post(post):
        return ORG_POST_VISIBILITY_PUBLIC
    value = getattr(post, "organization_visibility", None)
    if value == ORG_POST_VISIBILITY_PUBLIC:
        return ORG_POST_VISIBILITY_PUBLIC
    if value == ORG_POST_VISIBILITY_DRAFT:
        return ORG_POST_VISIBILITY_DRAFT
    return ORG_POST_VISIBILITY_UNLISTED


def update_organization_post_visibility(
    actor: AbstractBaseUser | None,
    post: TimelinePost | None,
    visibility: str,
) -> TimelinePost:
    if post is None or getattr(post, "is_removed", False):
        raise OrganizationPostError("not_found", status=404)
    if not is_organization_timeline_post(post):
        raise OrganizationPostError("not_organization_post", status=400)
    if visibility not in _WRITABLE_ORG_VISIBILITIES:
        raise OrganizationPostError("invalid_visibility", status=400)
    organization = _post_organization(post)
    if not is_organization_admin(actor, organization):
        if organization_post_is_publicly_listed(post):
            raise OrganizationPostError("forbidden", status=403)
        raise OrganizationPostError("not_found", status=404)
    if not can_manage_organization(actor, organization):
        raise OrganizationPostError("forbidden", status=403)
    if post.organization_visibility != visibility:
        post.organization_visibility = visibility
        post.save(update_fields=["organization_visibility"])
    return post


def build_organization_posts_payload(
    organization: Organization | None,
    viewer: AbstractBaseUser | None,
    *,
    offset: int = 0,
    limit: int = ORG_PROFILE_POSTS_PAGE,
    scope: str = "",
) -> dict[str, Any] | None:
    """団体プロフィールの投稿一覧。プロフィール閲覧不可なら None（404）。"""
    if organization is None or not can_view_organization_profile(viewer, organization):
        return None

    page_size = max(1, min(int(limit or ORG_PROFILE_POSTS_PAGE), 50))
    start = max(0, int(offset or 0))
    is_admin = is_organization_admin(viewer, organization)
    listable = organization_posts_are_publicly_listable(organization)
    requested_scope = (scope or "").strip().lower()
    if is_admin and requested_scope == ORG_POST_SCOPE_UNPUBLISHED:
        active_scope = ORG_POST_SCOPE_UNPUBLISHED
    else:
        active_scope = ORG_POST_SCOPE_PUBLIC

    if not listable and not is_admin:
        return {
            "ok": True,
            "posts": [],
            "has_more": False,
            "next_offset": 0,
            "total_count": 0,
            "preview": False,
            "unpublished": True,
            "scope": ORG_POST_SCOPE_PUBLIC,
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
    public_count = queryset.filter(
        organization_visibility=ORG_POST_VISIBILITY_PUBLIC
    ).count()
    unpublished_count = queryset.filter(
        organization_visibility__in=[
            ORG_POST_VISIBILITY_DRAFT,
            ORG_POST_VISIBILITY_UNLISTED,
        ]
    ).count()
    if active_scope == ORG_POST_SCOPE_UNPUBLISHED:
        queryset = queryset.filter(
            organization_visibility__in=[
                ORG_POST_VISIBILITY_DRAFT,
                ORG_POST_VISIBILITY_UNLISTED,
            ]
        )
    else:
        queryset = queryset.filter(
            organization_visibility=ORG_POST_VISIBILITY_PUBLIC
        )
    total = queryset.count()
    page = list(queryset[start : start + page_size])
    prepared = prepare_timeline_posts(page, viewer)
    posts = [
        serialize_timeline_post(post, viewer, include_comments=False)
        for post in prepared
    ]
    next_offset = start + len(posts)
    payload = {
        "ok": True,
        "posts": posts,
        "has_more": next_offset < total,
        "next_offset": next_offset,
        "total_count": total,
        "preview": is_admin and active_scope == ORG_POST_SCOPE_UNPUBLISHED,
        "unpublished": (not is_admin) and public_count == 0,
        "scope": active_scope,
    }
    if is_admin:
        payload["public_count"] = public_count
        payload["unpublished_count"] = unpublished_count
    return payload
