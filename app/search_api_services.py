"""タブ横断の部分一致検索（API用）。"""

from django.db.models import Q
from django.urls import reverse

from .community_services import list_community_threads
from .models import Product, TimelinePost
from .services import user_display_name
from .ugc_services import filter_visible_products, filter_visible_timeline_posts

SEARCH_SCOPES = ("home", "communities", "flea")
SEARCH_RESULT_LIMIT = 40


def normalize_search_scope(scope: str | None) -> str:
    value = (scope or "home").strip().lower()
    if value in SEARCH_SCOPES:
        return value
    return "home"


def _serialize_post(post: TimelinePost) -> dict:
    author_name = user_display_name(post.author)
    body = (post.body or "").strip()
    preview = body if len(body) <= 120 else body[:117] + "…"
    return {
        "type": "post",
        "id": post.pk,
        "title": preview or "(本文なし)",
        "subtitle": f"@{getattr(post.author, 'username', '') or author_name}",
        "meta": (post.course_name or "").strip(),
        "url": reverse("home") + f"#post-{post.pk}",
    }


def _serialize_thread(thread) -> dict:
    preview = (thread.body or "").strip()
    if len(preview) > 100:
        preview = preview[:97] + "…"
    faculty = getattr(getattr(thread, "community", None), "faculty", "") or ""
    return {
        "type": "thread",
        "id": thread.pk,
        "title": (thread.title or "").strip() or "(無題)",
        "subtitle": preview,
        "meta": faculty,
        "url": reverse(
            "community_thread_detail",
            kwargs={"slug": thread.community.slug, "thread_pk": thread.pk},
        ),
    }


def _serialize_product(product: Product) -> dict:
    seller = user_display_name(product.seller)
    return {
        "type": "product",
        "id": product.pk,
        "title": (product.name or "").strip() or "(無題)",
        "subtitle": f"{product.price}円 · {seller}",
        "meta": (product.course_name or product.faculty or "").strip(),
        "url": reverse("product_detail", kwargs={"pk": product.pk}),
    }


def search_home_posts(query: str, viewer=None, *, limit: int = SEARCH_RESULT_LIMIT):
    query = (query or "").strip()
    if not query:
        return []
    qs = TimelinePost.objects.select_related("author", "author__profile").filter(
        Q(body__icontains=query)
        | Q(course_name__icontains=query)
        | Q(professor_name__icontains=query)
    ).order_by("-created_at")
    qs = filter_visible_timeline_posts(qs, viewer)[:limit]
    return [_serialize_post(post) for post in qs]


def search_community_threads_api(
    query: str, *, faculty: str = "", limit: int = SEARCH_RESULT_LIMIT
):
    query = (query or "").strip()
    if not query:
        return []
    threads = list(list_community_threads(query=query, faculty=faculty)[:limit])
    return [_serialize_thread(thread) for thread in threads]


def search_flea_products_api(
    query: str, viewer=None, *, limit: int = SEARCH_RESULT_LIMIT
):
    query = (query or "").strip()
    if not query:
        return []
    qs = Product.objects.select_related("seller", "seller__profile").filter(
        Q(name__icontains=query)
        | Q(description__icontains=query)
        | Q(course_name__icontains=query)
        | Q(professor_name__icontains=query)
    ).order_by("-created_at")
    qs = filter_visible_products(qs, viewer)[:limit]
    return [_serialize_product(product) for product in qs]


def run_scoped_search(
    query: str,
    scope: str,
    viewer=None,
    *,
    faculty: str = "",
) -> dict:
    """scope に応じた部分一致検索。0件時は results=[]。"""
    normalized_scope = normalize_search_scope(scope)
    q = (query or "").strip()
    if not q:
        return {"q": "", "scope": normalized_scope, "results": [], "count": 0}

    if normalized_scope == "communities":
        results = search_community_threads_api(q, faculty=faculty)
    elif normalized_scope == "flea":
        results = search_flea_products_api(q, viewer=viewer)
    else:
        results = search_home_posts(q, viewer=viewer)

    return {
        "q": q,
        "scope": normalized_scope,
        "results": results,
        "count": len(results),
    }
