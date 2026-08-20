"""グローバル検索（検索タブ）のヒット集合・関連度ヘルパー。

おすすめ / 最新は「ヒット集合の並べ替え」であり、ヒット外の人気枠は混ぜない。
"""

from __future__ import annotations

import re
from typing import Any

from django.db.models import Avg, Count, Exists, OuterRef, Q, QuerySet

from .course_services import (
    day_label,
    period_label,
    serialize_offering,
)
from .models import CourseEnrollment, CourseOffering, CourseReview
from .timetable_services import TIMETABLE_DAYS

# 関連度ティア（engagement より十分大きく、完全一致が人気で消えないようにする）
RELEVANCE_EXACT = 1_000_000
RELEVANCE_PREFIX = 500_000
RELEVANCE_PARTIAL = 100_000
RELEVANCE_RELATED = 40_000
RELEVANCE_INDIRECT = 10_000

_PERIOD_RE = re.compile(r"(?:^|[^\d])(\d)\s*限")
_OD_PERIOD_RE = re.compile(r"OD\s*(\d)", re.IGNORECASE)


def _norm(text: str) -> str:
    return (text or "").strip().casefold()


def search_tokens(query: str) -> list[str]:
    """空白区切り。連続日本語は先頭2文字＋末尾2文字でも AND ヒットできるようにする。"""
    q = (query or "").strip()
    if not q:
        return []
    parts = [t for t in re.split(r"[\s　]+", q) if len(t) >= 1]
    if len(parts) >= 2:
        return [t for t in parts if len(t) >= 2] or parts
    if len(q) >= 4 and not re.search(r"[\s　]", q):
        head, tail = q[:2], q[-2:]
        if head != tail:
            return [head, tail]
    return [q]


def review_comment_match_q(query: str) -> Q:
    """レビュー本文: 全文部分一致 OR（トークン全AND）。"""
    q = (query or "").strip()
    if not q:
        return Q()
    match = Q(comment__icontains=q)
    tokens = search_tokens(q)
    if len(tokens) > 1:
        token_and = Q()
        for token in tokens:
            token_and &= Q(comment__icontains=token)
        match |= token_and
    return match


def text_relevance(query: str, *candidates: str) -> int:
    """完全一致 > 前方一致 > 部分一致。候補が空なら 0。"""
    q = _norm(query)
    if not q:
        return 0
    best = 0
    for raw in candidates:
        value = _norm(raw)
        if not value:
            continue
        if value == q:
            best = max(best, RELEVANCE_EXACT)
        elif value.startswith(q):
            best = max(best, RELEVANCE_PREFIX)
        elif q in value:
            best = max(best, RELEVANCE_PARTIAL)
    return best


def _semester_match_q(query: str) -> Q:
    q = (query or "").strip()
    if not q:
        return Q()
    clauses = Q()
    for value, label in CourseOffering.Semester.choices:
        if q.casefold() == value.casefold() or q in label or label in q:
            clauses |= Q(semester=value)
    return clauses


def _day_match_q(query: str) -> Q:
    q = (query or "").strip()
    if not q:
        return Q()
    clauses = Q()
    for index, label in enumerate(TIMETABLE_DAYS):
        aliases = (
            label,
            f"{label}曜",
            f"{label}曜日",
            f"{label}曜日限",
        )
        if any(alias in q or q == alias for alias in aliases):
            clauses |= Q(day_of_week=index)
    return clauses


def _period_match_q(query: str) -> Q:
    q = (query or "").strip()
    if not q:
        return Q()
    clauses = Q()
    od = _OD_PERIOD_RE.search(q)
    if od:
        clauses |= Q(
            period_kind=CourseOffering.PeriodKind.OD,
            period=int(od.group(1)),
        )
    match = _PERIOD_RE.search(q)
    if match:
        clauses |= Q(
            period_kind=CourseOffering.PeriodKind.PERIOD,
            period=int(match.group(1)),
        )
    return clauses


def search_course_offerings_global(
    query: str, *, limit: int = 40
) -> list[CourseOffering]:
    """授業横断検索。レビュー本文ヒットも Offering を返す（Review 単体は返さない）。"""
    query = (query or "").strip()
    if not query:
        return []

    review_hit = Exists(
        CourseReview.objects.filter(
            offering_id=OuterRef("pk"),
            is_hidden=False,
        ).filter(review_comment_match_q(query))
    )
    filter_q = (
        Q(title__icontains=query)
        | Q(title_normalized__icontains=query)
        | Q(instructor__icontains=query)
        | Q(instructor_normalized__icontains=query)
        | Q(school__icontains=query)
        | review_hit
    )
    filter_q |= _semester_match_q(query)
    filter_q |= _day_match_q(query)
    filter_q |= _period_match_q(query)

    qs: QuerySet[CourseOffering] = (
        CourseOffering.objects.filter(
            status=CourseOffering.Status.ACTIVE,
        )
        .filter(filter_q)
        .select_related("course")
        .annotate(
            search_review_count=Count(
                "reviews",
                filter=Q(reviews__is_hidden=False),
                distinct=True,
            ),
            search_review_overall=Avg(
                "reviews__overall_rating",
                filter=Q(reviews__is_hidden=False),
            ),
            search_enrollment_count=Count(
                "enrollments",
                filter=Q(enrollments__role=CourseEnrollment.Role.CURRENT),
                distinct=True,
            ),
            search_review_hit=review_hit,
        )
        .distinct()
    )

    offerings = list(qs[: max(limit * 3, 80)])

    def rank(offering: CourseOffering) -> tuple:
        title_rel = text_relevance(query, offering.title, offering.title_normalized)
        instructor_rel = text_relevance(
            query, offering.instructor, offering.instructor_normalized
        )
        school_rel = text_relevance(query, offering.school)
        related = 0
        if _semester_match_q(query) and offering.semester:
            # semester matched via filter; boost related
            related = max(related, RELEVANCE_RELATED)
        day = day_label(offering.day_of_week)
        period = period_label(offering.period_kind, offering.period)
        schedule_rel = text_relevance(
            query,
            day,
            f"{day}曜",
            f"{day}{period}",
            period,
            offering.get_semester_display(),
        )
        if schedule_rel:
            related = max(related, schedule_rel if schedule_rel >= RELEVANCE_PARTIAL else RELEVANCE_RELATED)
        indirect = (
            RELEVANCE_INDIRECT if getattr(offering, "search_review_hit", False) else 0
        )
        relevance = max(title_rel, instructor_rel, school_rel, related, indirect)
        review_count = int(getattr(offering, "search_review_count", 0) or 0)
        enroll_count = int(getattr(offering, "search_enrollment_count", 0) or 0)
        # 人気は補助。relevance が同点のときだけ効くよう下位桁に置く
        popularity = review_count * 3 + enroll_count
        return (-relevance, -popularity, offering.title, offering.pk)

    offerings.sort(key=rank)
    return offerings[:limit]


def offering_relevance(query: str, offering: CourseOffering) -> int:
    title_rel = text_relevance(query, offering.title, offering.title_normalized)
    instructor_rel = text_relevance(
        query, offering.instructor, offering.instructor_normalized
    )
    school_rel = text_relevance(query, offering.school)
    day = day_label(offering.day_of_week)
    period = period_label(offering.period_kind, offering.period)
    schedule_rel = text_relevance(
        query,
        day,
        f"{day}曜",
        f"{day}{period}",
        period,
        offering.get_semester_display(),
        offering.semester,
    )
    indirect = (
        RELEVANCE_INDIRECT if getattr(offering, "search_review_hit", False) else 0
    )
    related = schedule_rel if schedule_rel else 0
    if school_rel and school_rel < RELEVANCE_PARTIAL:
        related = max(related, RELEVANCE_RELATED)
    return max(title_rel, instructor_rel, school_rel, related, indirect)


def serialize_search_offering(offering: CourseOffering) -> dict[str, Any]:
    payload = serialize_offering(offering)
    review_count = int(getattr(offering, "search_review_count", 0) or 0)
    overall = getattr(offering, "search_review_overall", None)
    enrollment = getattr(offering, "search_enrollment_count", None)
    if enrollment is not None:
        payload["enrollment_count"] = int(enrollment or 0)
    payload["review_count"] = review_count
    payload["review_overall"] = (
        round(float(overall), 1) if overall is not None else None
    )
    return payload


def post_relevance(query: str, post: dict[str, Any]) -> int:
    return text_relevance(
        query,
        post.get("body") or "",
        post.get("course_name") or "",
        post.get("professor_name") or "",
    )


def thread_relevance(query: str, thread: dict[str, Any]) -> int:
    return text_relevance(
        query,
        thread.get("title") or "",
        thread.get("body") or "",
        thread.get("body_preview") or "",
    )


def product_relevance(query: str, product: dict[str, Any]) -> int:
    return text_relevance(
        query,
        product.get("name") or "",
        product.get("description") or "",
        product.get("course_name") or "",
        product.get("professor_name") or "",
    )


def user_relevance(query: str, user_payload: dict[str, Any]) -> int:
    primary = text_relevance(
        query,
        user_payload.get("username") or "",
        user_payload.get("display_name") or "",
    )
    related = text_relevance(
        query,
        user_payload.get("bio") or "",
        user_payload.get("department") or "",
    )
    if related and related < RELEVANCE_PARTIAL:
        related = RELEVANCE_RELATED
    elif related:
        related = min(related, RELEVANCE_RELATED)
    return max(primary, related)


def combine_recommend_score(relevance: int, engagement: int) -> int:
    """おすすめ最終スコア。関連度が主、人気は補助。"""
    return int(relevance) + min(int(engagement), 50_000)
