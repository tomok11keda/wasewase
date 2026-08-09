"""Profile / search JSON helpers — thin wrappers over existing services."""

from __future__ import annotations

from typing import Any

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AbstractBaseUser
from django.db.models import Count, Exists, OuterRef, Q
from django.http import HttpRequest
from django.utils import timezone

from .board_services import get_profile_timeline_posts
from .bookmark_services import get_bookmarked_timeline_posts, prepare_timeline_posts
from .dm_services import find_dm_room
from .flea_api_services import serialize_product_card
from .follow_services import (
    can_view_private_content,
    can_view_timetable_for,
    get_follow_state,
    is_account_private,
    toggle_follow_relationship,
)
from .models import Product, TimelineLike, TimelinePost
from .services import (
    get_profile_stats,
    get_user_avatar_url,
    is_following,
    search_products,
    search_timeline_posts,
    search_users,
    user_avatar_initial,
    user_display_name,
)
from .timeline_api_services import serialize_author, serialize_timeline_post
from .timetable_privacy_services import (
    get_or_create_profile as get_or_create_timetable_profile,
    is_timetable_public_value,
)
from .ugc_services import (
    filter_visible_products,
    is_either_blocked,
    is_user_blocked,
)

User = get_user_model()

SEARCH_TAB_ALL = "all"
SEARCH_TAB_LATEST = "latest"
SEARCH_TAB_USERS = "users"
SEARCH_TAB_PRODUCTS = "products"
SEARCH_TAB_CHOICES = (
    SEARCH_TAB_ALL,
    SEARCH_TAB_LATEST,
    SEARCH_TAB_USERS,
    SEARCH_TAB_PRODUCTS,
)
SEARCH_RESULT_LIMIT = 40
DISCOVER_CANDIDATE_LIMIT = 80
DISCOVER_TRENDING_LIMIT = 12
DISCOVER_FACULTY_LIMIT = 10
DISCOVER_PRODUCT_LIMIT = 16


def _search_post_score(post_payload: dict[str, Any]) -> int:
    return (
        int(post_payload.get("like_count") or 0) * 3
        + int(post_payload.get("comment_count") or 0) * 2
        + int(post_payload.get("quote_count") or 0) * 2
        + int(post_payload.get("view_count") or 0) // 10
    )


def _search_thread_score(thread_payload: dict[str, Any]) -> int:
    return int(thread_payload.get("replies_count") or 0) * 3


def _search_product_score(product_payload: dict[str, Any]) -> int:
    likes = int(product_payload.get("like_count") or 0)
    score = likes * 3
    if product_payload.get("is_available"):
        score += 8
    elif product_payload.get("is_pending"):
        score += 2
    return score


def serialize_profile_user(user: AbstractBaseUser, profile) -> dict[str, Any]:
    from .handle_services import public_username

    avatar = get_user_avatar_url(user) or ""
    return {
        "id": user.pk,
        "username": public_username(user),
        "display_name": user_display_name(user),
        "avatar_url": avatar,
        "initial": user_avatar_initial(user),
        "bio": (getattr(profile, "bio", None) or ""),
        "department": (getattr(profile, "department", None) or ""),
        "grade": (getattr(profile, "grade", None) or ""),
        "department_grade": profile.department_grade_display if profile else "",
    }


def build_profile_payload(
    profile_user: AbstractBaseUser,
    viewer: AbstractBaseUser | None,
) -> dict[str, Any]:
    profile = get_or_create_timetable_profile(profile_user)
    is_own = bool(
        viewer is not None
        and getattr(viewer, "is_authenticated", False)
        and viewer.pk == profile_user.pk
    )
    is_public = is_timetable_public_value(profile)
    stats = get_profile_stats(profile_user, "thread")

    viewer_auth = (
        viewer
        if viewer is not None and getattr(viewer, "is_authenticated", False)
        else None
    )
    following = False
    blocked = False
    can_send_dm = False
    dm_room_id = None
    follow_state = get_follow_state(viewer_auth, profile_user)
    can_view_content = can_view_private_content(viewer_auth, profile_user)
    account_private = is_account_private(profile_user)
    if viewer_auth and not is_own:
        following = is_following(viewer_auth, profile_user)
        blocked = is_user_blocked(viewer_auth, profile_user)
        can_send_dm = not is_either_blocked(viewer_auth, profile_user)
        room = find_dm_room(viewer_auth, profile_user)
        dm_room_id = room.pk if room else None

    return {
        "ok": True,
        "user": serialize_profile_user(profile_user, profile),
        "stats": {
            "post_count": stats["post_count"],
            "product_count": stats["product_count"],
            "follower_count": stats["follower_count"],
            "following_count": stats["following_count"],
            "left_label": stats["left_label"],
            "left_count": stats["left_count"],
        },
        "is_own": is_own,
        "is_following": following,
        "is_private": account_private,
        "follow_state": follow_state,
        "can_view_content": can_view_content,
        "is_blocked": blocked,
        "can_send_dm": can_send_dm,
        "dm_room_id": dm_room_id,
        "show_safety_menu": bool(viewer_auth and not is_own),
        "can_view_timetable": can_view_timetable_for(
            viewer_auth, profile_user, is_timetable_public=is_public
        ),
        "is_timetable_public": is_public,
        "can_view_bookmarks": is_own,
    }


def list_profile_posts(
    profile_user: AbstractBaseUser,
    viewer: AbstractBaseUser | None,
) -> dict[str, Any]:
    if not can_view_private_content(viewer, profile_user):
        return {"ok": True, "posts": [], "can_view_content": False}
    posts = get_profile_timeline_posts(profile_user, viewer)
    return {
        "ok": True,
        "posts": [serialize_timeline_post(p, viewer) for p in posts],
        "can_view_content": True,
    }


def list_profile_products(
    profile_user: AbstractBaseUser,
    viewer: AbstractBaseUser | None,
) -> dict[str, Any]:
    if not can_view_private_content(viewer, profile_user):
        return {"ok": True, "products": [], "can_view_content": False}
    products = filter_visible_products(
        Product.objects.filter(
            seller=profile_user, status=Product.Status.AVAILABLE
        ).select_related("seller", "seller__profile"),
        viewer,
    )
    return {
        "ok": True,
        "products": [serialize_product_card(p) for p in products],
        "can_view_content": True,
    }


def list_profile_bookmarks(
    profile_user: AbstractBaseUser,
    viewer: AbstractBaseUser,
) -> dict[str, Any]:
    posts, meta = get_bookmarked_timeline_posts(profile_user, viewer)
    return {
        "ok": True,
        "posts": [serialize_timeline_post(p, viewer) for p in posts],
        "meta": meta or {},
    }


def toggle_follow_for_api(
    actor: AbstractBaseUser, target: AbstractBaseUser
) -> dict[str, Any]:
    return toggle_follow_relationship(actor, target)


def toggle_block_for_api(
    actor: AbstractBaseUser, target: AbstractBaseUser
) -> dict[str, Any]:
    if actor.pk == target.pk:
        raise ValueError("own_user")
    from .ugc_services import block_user, unblock_user

    if is_user_blocked(actor, target):
        unblock_user(actor, target)
        blocked = False
    else:
        block_user(actor, target)
        blocked = True
    return {"ok": True, "is_blocked": blocked}


def _discover_timeline_candidates(
    viewer: AbstractBaseUser | None,
    *,
    faculty: str = "",
    limit: int = DISCOVER_CANDIDATE_LIMIT,
):
    from .board_services import annotate_timeline_quote_count
    from .ugc_services import filter_visible_timeline_posts

    qs = TimelinePost.objects.select_related(
        "author",
        "author__profile",
        "quoted_post",
        "quoted_post__author",
        "quoted_post__author__profile",
    ).prefetch_related("comments__author")
    qs = filter_visible_timeline_posts(qs, viewer)
    if faculty:
        qs = qs.filter(
            Q(author__profile__department=faculty) | Q(faculty=faculty)
        )
    qs = annotate_timeline_quote_count(qs).annotate(
        feed_comment_count=Count(
            "comments",
            filter=Q(comments__is_removed=False),
            distinct=True,
        )
    )
    if viewer is not None and getattr(viewer, "is_authenticated", False):
        qs = qs.annotate(
            user_has_liked=Exists(
                TimelineLike.objects.filter(
                    timeline_post_id=OuterRef("pk"),
                    user_id=viewer.id,
                )
            )
        )
    return list(qs.order_by("-created_at")[:limit])


def _discover_mixed_rows(
    posts: list,
    threads: list,
    viewer: AbstractBaseUser | None,
    *,
    limit: int,
) -> list[dict[str, Any]]:
    from .community_api_services import serialize_thread_summary
    from .feed_ranking import (
        community_recommend_score,
        timeline_recommend_score,
    )
    from .services import get_following_user_ids

    now = timezone.now()
    following_ids: set[int] = set()
    viewer_dept = ""
    viewer_grade = ""
    if viewer is not None and getattr(viewer, "is_authenticated", False):
        following_ids = set(get_following_user_ids(viewer))
        profile = getattr(viewer, "profile", None)
        viewer_dept = (getattr(profile, "department", None) or "") if profile else ""
        viewer_grade = (getattr(profile, "grade", None) or "") if profile else ""

    prepared_posts = prepare_timeline_posts(posts, viewer)
    rows: list[dict[str, Any]] = []
    for post in prepared_posts:
        score = timeline_recommend_score(
            post,
            now=now,
            following_ids=following_ids,
            viewer_dept=viewer_dept,
            viewer_grade=viewer_grade,
            seen_ids=set(),
        )
        payload = serialize_timeline_post(post, viewer)
        rows.append(
            {
                "kind": "post",
                "created_at": payload.get("created_at") or "",
                "score": int(score),
                "post": payload,
            }
        )
    for thread in threads:
        score = community_recommend_score(
            thread,
            now=now,
            viewer_faculty=viewer_dept,
        )
        payload = serialize_thread_summary(thread, viewer)
        rows.append(
            {
                "kind": "thread",
                "created_at": payload.get("created_at") or "",
                "score": int(score),
                "thread": payload,
            }
        )
    rows.sort(
        key=lambda row: (
            int(row.get("score") or 0),
            row.get("created_at") or "",
        ),
        reverse=True,
    )
    return rows[:limit]


def build_search_discover_payload(request: HttpRequest) -> dict[str, Any]:
    """Search-tab empty state: sectioned discovery (not a mixed ranking dump)."""
    from .community_services import list_community_threads
    from .services import get_user_faculty

    viewer = request.user if request.user.is_authenticated else None
    faculty = get_user_faculty(viewer) if viewer is not None else ""

    trending_posts = _discover_timeline_candidates(viewer)
    trending_threads = list(list_community_threads(query="", faculty="")[:DISCOVER_CANDIDATE_LIMIT])
    trending = _discover_mixed_rows(
        trending_posts,
        trending_threads,
        viewer,
        limit=DISCOVER_TRENDING_LIMIT,
    )

    faculty_section: dict[str, Any] | None = None
    if faculty:
        faculty_posts = _discover_timeline_candidates(viewer, faculty=faculty)
        faculty_threads = list(
            list_community_threads(query="", faculty=faculty)[
                :DISCOVER_CANDIDATE_LIMIT
            ]
        )
        faculty_rows = _discover_mixed_rows(
            faculty_posts,
            faculty_threads,
            viewer,
            limit=DISCOVER_FACULTY_LIMIT,
        )
        if faculty_rows:
            faculty_section = {
                "faculty": faculty,
                "title": f"{faculty}で話題",
                "results": faculty_rows,
            }

    product_qs = (
        filter_visible_products(
            Product.objects.select_related("seller", "seller__profile").all(),
            viewer,
        )
        .annotate(like_count_ann=Count("likes", distinct=True))
        .order_by("-like_count_ann", "-created_at")
    )
    products_payload: list[dict[str, Any]] = []
    for product in list(product_qs[:DISCOVER_PRODUCT_LIMIT]):
        card = serialize_product_card(product)
        card["like_count"] = int(getattr(product, "like_count_ann", 0) or 0)
        products_payload.append(card)

    return {
        "trending": trending,
        "faculty": faculty_section,
        "products": products_payload,
    }


def build_search_page_payload(request: HttpRequest) -> dict[str, Any]:
    from .community_api_services import serialize_thread_summary
    from .community_services import list_community_threads

    query = request.GET.get("q", "").strip()
    tab = (request.GET.get("tab") or SEARCH_TAB_ALL).strip().lower()
    if tab not in SEARCH_TAB_CHOICES:
        tab = SEARCH_TAB_ALL
    viewer = request.user if request.user.is_authenticated else None

    posts_payload: list[dict[str, Any]] = []
    threads_payload: list[dict[str, Any]] = []
    users_payload: list[dict[str, Any]] = []
    products_payload: list[dict[str, Any]] = []
    results: list[dict[str, Any]] = []

    if not query:
        return {
            "ok": True,
            "q": "",
            "tab": tab,
            "results": [],
            "posts": [],
            "threads": [],
            "users": [],
            "products": [],
            "post_count": 0,
            "thread_count": 0,
            "user_count": 0,
            "product_count": 0,
            "result_count": 0,
            "discover": build_search_discover_payload(request),
        }

    def _load_posts(*, sort: str) -> None:
        nonlocal posts_payload
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
        if viewer is not None and getattr(viewer, "is_authenticated", False):
            timeline_qs = timeline_qs.annotate(
                user_has_liked=Exists(
                    TimelineLike.objects.filter(
                        timeline_post_id=OuterRef("pk"),
                        user_id=viewer.id,
                    )
                )
            )
        posts = prepare_timeline_posts(
            list(timeline_qs[:SEARCH_RESULT_LIMIT]),
            viewer,
        )
        posts_payload = [serialize_timeline_post(p, viewer) for p in posts]

    def _load_threads(*, recommended: bool) -> None:
        nonlocal threads_payload
        thread_qs = list_community_threads(query=query, faculty="")
        if recommended:
            thread_qs = thread_qs.order_by("-replies_count", "-updated_at")
        else:
            thread_qs = thread_qs.order_by("-created_at")
        threads = list(thread_qs[:SEARCH_RESULT_LIMIT])
        threads_payload = [
            serialize_thread_summary(thread, viewer) for thread in threads
        ]

    def _load_products(*, recommended: bool) -> None:
        nonlocal products_payload
        product_qs = search_products(query, viewer=viewer).annotate(
            like_count_ann=Count("likes", distinct=True)
        )
        if recommended:
            product_qs = product_qs.order_by("-like_count_ann", "-created_at")
        else:
            product_qs = product_qs.order_by("-created_at")
        products = list(product_qs[:SEARCH_RESULT_LIMIT])
        for product in products:
            card = serialize_product_card(product)
            card["like_count"] = int(getattr(product, "like_count_ann", 0) or 0)
            products_payload.append(card)

    if query:
        if tab == SEARCH_TAB_ALL:
            _load_posts(sort="popular")
            _load_threads(recommended=True)
            _load_products(recommended=True)
            for post in posts_payload:
                results.append(
                    {
                        "kind": "post",
                        "created_at": post.get("created_at") or "",
                        "score": _search_post_score(post),
                        "post": post,
                    }
                )
            for thread in threads_payload:
                results.append(
                    {
                        "kind": "thread",
                        "created_at": thread.get("created_at") or "",
                        "score": _search_thread_score(thread),
                        "thread": thread,
                    }
                )
            for product in products_payload:
                results.append(
                    {
                        "kind": "product",
                        "created_at": product.get("created_at") or "",
                        "score": _search_product_score(product),
                        "product": product,
                    }
                )
            results.sort(
                key=lambda row: (
                    int(row.get("score") or 0),
                    row.get("created_at") or "",
                ),
                reverse=True,
            )
        elif tab == SEARCH_TAB_LATEST:
            # 最新: タイムライン＋コミュニティのみ（商品は「商品」タブへ）
            _load_posts(sort="latest")
            _load_threads(recommended=False)
            for post in posts_payload:
                results.append(
                    {
                        "kind": "post",
                        "created_at": post.get("created_at") or "",
                        "score": _search_post_score(post),
                        "post": post,
                    }
                )
            for thread in threads_payload:
                results.append(
                    {
                        "kind": "thread",
                        "created_at": thread.get("created_at") or "",
                        "score": _search_thread_score(thread),
                        "thread": thread,
                    }
                )
            results.sort(
                key=lambda row: row.get("created_at") or "",
                reverse=True,
            )
        elif tab == SEARCH_TAB_USERS:
            for user in list(search_users(query, viewer=viewer)[:50]):
                users_payload.append(serialize_author(user))
        elif tab == SEARCH_TAB_PRODUCTS:
            _load_products(recommended=False)
            for product in products_payload:
                results.append(
                    {
                        "kind": "product",
                        "created_at": product.get("created_at") or "",
                        "score": _search_product_score(product),
                        "product": product,
                    }
                )

    if tab == SEARCH_TAB_USERS:
        result_count = len(users_payload)
    else:
        result_count = len(results)

    return {
        "ok": True,
        "q": query,
        "tab": tab,
        "results": results,
        "posts": posts_payload,
        "threads": threads_payload,
        "users": users_payload,
        "products": products_payload,
        "post_count": len(posts_payload),
        "thread_count": len(threads_payload),
        "user_count": len(users_payload),
        "product_count": len(products_payload),
        "result_count": result_count,
    }
