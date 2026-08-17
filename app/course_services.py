"""授業マスタ検索・履修・重複検知・統合（production hardening 込み）。"""
from __future__ import annotations

import logging
import re
import unicodedata
from datetime import date

from django.contrib.auth.base_user import AbstractBaseUser
from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.db.models import Avg, Count, Q, QuerySet
from django.utils import timezone

from .constants import COURSE_CAMPUS_CHOICES, FACULTY_CHOICES
from .models import (
    Course,
    CourseEnrollment,
    CourseOffering,
    CourseReview,
    TimetableSlot,
)
from .timetable_services import (
    TIMETABLE_DAYS,
    parse_slot_key,
    upsert_timetable_slot,
)

logger = logging.getLogger(__name__)

_SPACE_RE = re.compile(r"\s+")
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")

MAX_TITLE_LEN = 120
MAX_INSTRUCTOR_LEN = 120
MAX_ROOM_LEN = 80
MAX_CREDITS_LEN = 20
MAX_QUERY_LEN = 80
MAX_COMMENT_LEN = 1000

# 年度は現在年度 ±1 のみ受け付ける（誤入力・改ざん防止）
ACADEMIC_YEAR_WINDOW = 1

CREATE_OFFERING_RATE_LIMIT = 20
CREATE_OFFERING_RATE_WINDOW = 3600
REVIEW_RATE_LIMIT = 30
REVIEW_RATE_WINDOW = 3600

_FACULTY_VALUES = {v for v, _ in FACULTY_CHOICES if v}
_CAMPUS_VALUES = {v for v, _ in COURSE_CAMPUS_CHOICES}


def normalize_course_text(value: str | None) -> str:
    """全角半角・大小・連続スペースなどを揃える。"""
    text = unicodedata.normalize("NFKC", (value or "").strip())
    text = _SPACE_RE.sub(" ", text)
    return text.casefold()


def sanitize_plain_text(value: str | None, *, max_len: int) -> str:
    text = _CONTROL_RE.sub("", (value or "")).strip()
    text = _SPACE_RE.sub(" ", text)
    return text[:max_len]


def current_academic_year(today: date | None = None) -> int:
    d = today or timezone.localdate()
    return d.year if d.month >= 4 else d.year - 1


def current_semester(today: date | None = None) -> str:
    d = today or timezone.localdate()
    if 4 <= d.month <= 9:
        return CourseOffering.Semester.SPRING
    return CourseOffering.Semester.FALL


def validate_academic_year(year: int) -> int:
    current = current_academic_year()
    lo = current - ACADEMIC_YEAR_WINDOW
    hi = current + ACADEMIC_YEAR_WINDOW
    if year < lo or year > hi:
        raise ValueError("invalid_academic_year")
    return year


def day_label(day_of_week: int) -> str:
    if 0 <= day_of_week < len(TIMETABLE_DAYS):
        return TIMETABLE_DAYS[day_of_week]
    return ""


def period_label(period_kind: str, period: int) -> str:
    if period_kind == CourseOffering.PeriodKind.OD:
        return f"OD{period}"
    return f"{period}限"


def check_rate_limit(key: str, *, limit: int, window: int) -> bool:
    """超過なら False。"""
    try:
        count = cache.get(key)
        if count is None:
            cache.set(key, 1, window)
            return True
        if int(count) >= limit:
            return False
        try:
            cache.incr(key)
        except ValueError:
            cache.set(key, int(count) + 1, window)
        return True
    except Exception:
        logger.exception("course rate limit cache failed key=%s", key)
        return True


def resolve_canonical_offering(
    offering: CourseOffering,
    *,
    max_hops: int = 8,
) -> CourseOffering:
    """merged 連鎖を辿って有効な開講を返す。hidden / 途切れは ValueError。"""
    seen: set[int] = set()
    current = offering
    for _ in range(max_hops):
        if current.pk in seen:
            raise ValueError("offering_merge_cycle")
        seen.add(current.pk)
        if current.status == CourseOffering.Status.ACTIVE:
            return current
        if current.status == CourseOffering.Status.HIDDEN:
            raise ValueError("offering_hidden")
        if (
            current.status == CourseOffering.Status.MERGED
            and current.merged_into_id
        ):
            nxt = (
                CourseOffering.objects.filter(pk=current.merged_into_id)
                .select_related("course")
                .first()
            )
            if nxt is None:
                raise ValueError("offering_inactive")
            current = nxt
            continue
        raise ValueError("offering_inactive")
    raise ValueError("offering_merge_cycle")


def serialize_offering(
    offering: CourseOffering,
    *,
    enrollment_count: int | None = None,
    viewer: AbstractBaseUser | None = None,
    viewer_enrollment: str | None = None,
    viewer_has_review: bool | None = None,
) -> dict:
    payload = {
        "id": offering.pk,
        "course_id": offering.course_id,
        "title": offering.title,
        "instructor": offering.instructor,
        "academic_year": offering.academic_year,
        "semester": offering.semester,
        "semester_label": offering.get_semester_display(),
        "day_of_week": offering.day_of_week,
        "day_label": day_label(offering.day_of_week),
        "period_kind": offering.period_kind,
        "period": offering.period,
        "period_label": period_label(offering.period_kind, offering.period),
        "slot_key": offering.slot_key,
        "school": offering.school or "",
        "campus": offering.campus or "",
        "room": offering.room or "",
        "credits": offering.credits or "",
        "status": offering.status,
        "enrollment_count": enrollment_count
        if enrollment_count is not None
        else offering.enrollments.filter(
            role=CourseEnrollment.Role.CURRENT
        ).count(),
    }
    if viewer is not None and getattr(viewer, "is_authenticated", False):
        if viewer_enrollment is None:
            enrollment = (
                CourseEnrollment.objects.filter(
                    user_id=viewer.pk, offering_id=offering.pk
                )
                .only("role")
                .first()
            )
            viewer_enrollment = enrollment.role if enrollment else None
        if viewer_has_review is None:
            viewer_has_review = CourseReview.objects.filter(
                user_id=viewer.pk,
                offering_id=offering.pk,
                is_hidden=False,
            ).exists()
        payload["viewer_enrollment"] = viewer_enrollment
        payload["viewer_has_review"] = bool(viewer_has_review)
    return payload


def viewer_states_for(
    viewer: AbstractBaseUser | None, offering_ids: list[int]
) -> tuple[dict[int, str], set[int]]:
    if not viewer or not getattr(viewer, "is_authenticated", False) or not offering_ids:
        return {}, set()
    enroll_map = {
        row["offering_id"]: row["role"]
        for row in CourseEnrollment.objects.filter(
            user_id=viewer.pk, offering_id__in=offering_ids
        ).values("offering_id", "role")
    }
    review_ids = set(
        CourseReview.objects.filter(
            user_id=viewer.pk,
            offering_id__in=offering_ids,
            is_hidden=False,
        ).values_list("offering_id", flat=True)
    )
    return enroll_map, review_ids


def active_offerings() -> QuerySet[CourseOffering]:
    return CourseOffering.objects.filter(status=CourseOffering.Status.ACTIVE)


def search_offerings(
    *,
    q: str = "",
    day_of_week: int | None = None,
    period_kind: str | None = None,
    period: int | None = None,
    semester: str | None = None,
    academic_year: int | None = None,
    limit: int = 30,
) -> list[CourseOffering]:
    qs = active_offerings().select_related("course")
    if academic_year is not None:
        qs = qs.filter(academic_year=academic_year)
    else:
        # 年度更新直後も前年度を拾えるよう、未指定時は現在±1年を対象にする
        y = current_academic_year()
        qs = qs.filter(
            academic_year__gte=y - ACADEMIC_YEAR_WINDOW,
            academic_year__lte=y + ACADEMIC_YEAR_WINDOW,
        )
    if semester:
        qs = qs.filter(semester=semester)

    q = sanitize_plain_text(q, max_len=MAX_QUERY_LEN)
    norm = normalize_course_text(q)
    tokens = [t for t in norm.split(" ") if t][:6]

    if tokens:
        for token in tokens:
            qs = qs.filter(
                Q(title_normalized__contains=token)
                | Q(instructor_normalized__contains=token)
            )

    limit = max(1, min(int(limit or 30), 50))
    offerings = list(qs[: max(limit * 3, 60)])

    def rank(o: CourseOffering) -> tuple:
        title_n = o.title_normalized or normalize_course_text(o.title)
        inst_n = o.instructor_normalized or normalize_course_text(o.instructor)
        same_slot = (
            day_of_week is not None
            and period is not None
            and o.day_of_week == day_of_week
            and o.period == period
            and (period_kind is None or o.period_kind == period_kind)
        )
        title_hit = bool(norm) and (
            norm in title_n or any(t in title_n for t in tokens)
        )
        instructor_hit = bool(norm) and (
            norm in inst_n or any(t in inst_n for t in tokens)
        )
        exact_title = bool(norm) and title_n == norm
        year_boost = 0 if o.academic_year == current_academic_year() else 1
        return (
            0 if same_slot and title_hit else 1,
            0 if exact_title else 1,
            0 if title_hit else 1,
            0 if instructor_hit else 1,
            0 if same_slot else 1,
            year_boost,
            o.title,
            o.pk,
        )

    offerings.sort(key=rank)
    return offerings[:limit]


def find_duplicate_candidates(
    *,
    title: str,
    instructor: str,
    day_of_week: int,
    period: int,
    period_kind: str,
    semester: str,
    academic_year: int,
    exclude_id: int | None = None,
    limit: int = 8,
) -> list[CourseOffering]:
    title_n = normalize_course_text(title)
    instructor_n = normalize_course_text(instructor)
    qs = active_offerings().filter(
        academic_year=academic_year,
        semester=semester,
        day_of_week=day_of_week,
        period=period,
        period_kind=period_kind,
    )
    if exclude_id:
        qs = qs.exclude(pk=exclude_id)

    strong = list(
        qs.filter(
            title_normalized=title_n,
            instructor_normalized=instructor_n,
        )[:limit]
    )
    if strong:
        return strong

    soft = []
    for offering in qs[:40]:
        o_title = offering.title_normalized or normalize_course_text(offering.title)
        if not title_n or not o_title:
            continue
        if title_n in o_title or o_title in title_n:
            soft.append(offering)
            continue
        shared = 0
        for a, b in zip(title_n, o_title):
            if a != b:
                break
            shared += 1
        if shared >= 4:
            soft.append(offering)
    return soft[:limit]


@transaction.atomic
def get_or_create_course(title: str) -> Course:
    title = sanitize_plain_text(title, max_len=MAX_TITLE_LEN)
    title_n = normalize_course_text(title)
    if not title_n:
        raise ValueError("title_required")
    existing = (
        Course.objects.select_for_update()
        .filter(title_normalized=title_n)
        .first()
    )
    if existing:
        return existing
    try:
        return Course.objects.create(title=title, title_normalized=title_n)
    except IntegrityError:
        return Course.objects.get(title_normalized=title_n)


def _validate_offering_inputs(
    *,
    title: str,
    instructor: str,
    academic_year: int,
    semester: str,
    day_of_week: int,
    period: int,
    period_kind: str,
    school: str,
    campus: str,
    room: str,
    credits: str,
) -> dict:
    title = sanitize_plain_text(title, max_len=MAX_TITLE_LEN)
    instructor = sanitize_plain_text(instructor, max_len=MAX_INSTRUCTOR_LEN)
    room = sanitize_plain_text(room, max_len=MAX_ROOM_LEN)
    credits = sanitize_plain_text(credits, max_len=MAX_CREDITS_LEN)
    school = sanitize_plain_text(school, max_len=50)
    campus = sanitize_plain_text(campus, max_len=40)

    if not title:
        raise ValueError("title_required")
    if not instructor:
        raise ValueError("instructor_required")
    academic_year = validate_academic_year(int(academic_year))
    if semester not in CourseOffering.Semester.values:
        raise ValueError("invalid_semester")
    if period_kind not in CourseOffering.PeriodKind.values:
        raise ValueError("invalid_period_kind")
    if day_of_week < 0 or day_of_week > 5:
        raise ValueError("invalid_day")
    if period_kind == CourseOffering.PeriodKind.PERIOD and not (1 <= period <= 5):
        raise ValueError("invalid_period")
    if period_kind == CourseOffering.PeriodKind.OD and not (1 <= period <= 2):
        raise ValueError("invalid_period")
    if school and school not in _FACULTY_VALUES:
        raise ValueError("invalid_school")
    if campus and campus not in _CAMPUS_VALUES:
        raise ValueError("invalid_campus")

    return {
        "title": title,
        "instructor": instructor,
        "academic_year": academic_year,
        "semester": semester,
        "day_of_week": day_of_week,
        "period": period,
        "period_kind": period_kind,
        "school": school,
        "campus": campus,
        "room": room,
        "credits": credits,
    }


@transaction.atomic
def create_offering(
    *,
    user: AbstractBaseUser,
    title: str,
    instructor: str,
    academic_year: int,
    semester: str,
    day_of_week: int,
    period: int,
    period_kind: str = CourseOffering.PeriodKind.PERIOD,
    school: str = "",
    campus: str = "",
    room: str = "",
    credits: str = "",
    force_create: bool = False,
) -> tuple[CourseOffering, list[CourseOffering]]:
    cleaned = _validate_offering_inputs(
        title=title,
        instructor=instructor,
        academic_year=academic_year,
        semester=semester,
        day_of_week=day_of_week,
        period=period,
        period_kind=period_kind,
        school=school,
        campus=campus,
        room=room,
        credits=credits,
    )

    duplicates = find_duplicate_candidates(
        title=cleaned["title"],
        instructor=cleaned["instructor"],
        day_of_week=cleaned["day_of_week"],
        period=cleaned["period"],
        period_kind=cleaned["period_kind"],
        semester=cleaned["semester"],
        academic_year=cleaned["academic_year"],
    )
    if duplicates and not force_create:
        return duplicates[0], duplicates

    # Exact identity already exists → never create a second active row
    exact = [
        d
        for d in duplicates
        if d.title_normalized == normalize_course_text(cleaned["title"])
        and d.instructor_normalized
        == normalize_course_text(cleaned["instructor"])
    ]
    if exact:
        return exact[0], exact

    course = get_or_create_course(cleaned["title"])
    try:
        with transaction.atomic():
            offering = CourseOffering.objects.create(
                course=course,
                academic_year=cleaned["academic_year"],
                semester=cleaned["semester"],
                title=cleaned["title"],
                title_normalized=normalize_course_text(cleaned["title"]),
                instructor=cleaned["instructor"],
                instructor_normalized=normalize_course_text(
                    cleaned["instructor"]
                ),
                day_of_week=cleaned["day_of_week"],
                period_kind=cleaned["period_kind"],
                period=cleaned["period"],
                school=cleaned["school"],
                campus=cleaned["campus"],
                room=cleaned["room"],
                credits=cleaned["credits"],
                created_by=user,
                source=CourseOffering.Source.USER,
                status=CourseOffering.Status.ACTIVE,
            )
    except IntegrityError:
        existing = find_duplicate_candidates(
            title=cleaned["title"],
            instructor=cleaned["instructor"],
            day_of_week=cleaned["day_of_week"],
            period=cleaned["period"],
            period_kind=cleaned["period_kind"],
            semester=cleaned["semester"],
            academic_year=cleaned["academic_year"],
        )
        if existing:
            return existing[0], existing
        raise
    return offering, []


@transaction.atomic
def enroll_user_in_offering(
    user: AbstractBaseUser,
    offering: CourseOffering,
    *,
    slot_key: str | None = None,
    keep_memo: bool = True,
) -> tuple[CourseEnrollment, TimetableSlot]:
    locked = CourseOffering.objects.select_for_update().get(pk=offering.pk)
    offering = resolve_canonical_offering(locked)
    if offering.pk != locked.pk:
        offering = CourseOffering.objects.select_for_update().get(pk=offering.pk)
        if offering.status != CourseOffering.Status.ACTIVE:
            raise ValueError("offering_inactive")

    target_key = (slot_key or offering.slot_key).strip()
    parsed = parse_slot_key(target_key)
    if parsed is None:
        raise ValueError("invalid_slot_key")

    # 開講の曜時限と異なるセルへの配置は拒否（データ整合性）
    if (
        parsed["day_index"] != offering.day_of_week
        or parsed["number"] != offering.period
        or parsed["kind"] != offering.period_kind
    ):
        raise ValueError("slot_mismatch")

    memo = ""
    if keep_memo:
        existing_slot = (
            TimetableSlot.objects.select_for_update()
            .filter(user=user, slot_key=target_key)
            .first()
        )
        if existing_slot:
            memo = existing_slot.memo or ""

    enrollment, _ = CourseEnrollment.objects.update_or_create(
        user=user,
        offering=offering,
        defaults={"role": CourseEnrollment.Role.CURRENT},
    )

    TimetableSlot.objects.filter(user=user, offering=offering).exclude(
        slot_key=target_key
    ).delete()

    conflict = (
        TimetableSlot.objects.select_for_update()
        .filter(user=user, slot_key=target_key)
        .exclude(offering_id=offering.pk)
        .first()
    )
    if conflict and conflict.offering_id:
        CourseEnrollment.objects.filter(
            user=user,
            offering_id=conflict.offering_id,
            role=CourseEnrollment.Role.CURRENT,
        ).update(role=CourseEnrollment.Role.PAST)

    credits = offering.credits or ""
    room = "" if parsed["kind"] == "od" else (offering.room or "")
    slot = upsert_timetable_slot(
        user,
        slot_key=target_key,
        name=offering.title,
        room=room,
        credits=credits,
        memo=memo,
        offering=offering,
    )
    if slot is None:
        raise ValueError("slot_save_failed")
    return enrollment, slot


@transaction.atomic
def remove_offering_from_timetable(
    user: AbstractBaseUser,
    offering: CourseOffering,
) -> None:
    offering_ids = {offering.pk}
    try:
        canonical = resolve_canonical_offering(offering)
        offering_ids.add(canonical.pk)
    except ValueError:
        pass
    CourseEnrollment.objects.filter(
        user=user, offering_id__in=offering_ids
    ).update(role=CourseEnrollment.Role.PAST)
    TimetableSlot.objects.filter(
        user=user, offering_id__in=offering_ids
    ).delete()


@transaction.atomic
def clear_slot_and_sync_enrollment(user: AbstractBaseUser, slot_key: str) -> None:
    slot = (
        TimetableSlot.objects.select_for_update()
        .filter(user=user, slot_key=slot_key)
        .first()
    )
    if slot and slot.offering_id:
        CourseEnrollment.objects.filter(
            user=user,
            offering_id=slot.offering_id,
            role=CourseEnrollment.Role.CURRENT,
        ).update(role=CourseEnrollment.Role.PAST)
    TimetableSlot.objects.filter(user=user, slot_key=slot_key).delete()


def enrollment_counts_for(offering_ids: list[int]) -> dict[int, int]:
    if not offering_ids:
        return {}
    rows = (
        CourseEnrollment.objects.filter(
            offering_id__in=offering_ids,
            role=CourseEnrollment.Role.CURRENT,
        )
        .values("offering_id")
        .annotate(c=Count("id"))
    )
    return {row["offering_id"]: row["c"] for row in rows}


@transaction.atomic
def merge_offerings(source: CourseOffering, target: CourseOffering) -> CourseOffering:
    """source → target へ統合。Admin 用。"""
    source = CourseOffering.objects.select_for_update().get(pk=source.pk)
    target = CourseOffering.objects.select_for_update().get(pk=target.pk)

    if source.pk == target.pk:
        return target
    if source.status == CourseOffering.Status.MERGED:
        raise ValueError("source_already_merged")
    if source.status == CourseOffering.Status.HIDDEN:
        raise ValueError("source_hidden")

    target = resolve_canonical_offering(target)

    if source.pk == target.pk:
        return target

    for enrollment in CourseEnrollment.objects.select_for_update().filter(
        offering=source
    ):
        existing = (
            CourseEnrollment.objects.select_for_update()
            .filter(user_id=enrollment.user_id, offering=target)
            .first()
        )
        if existing:
            if (
                enrollment.role == CourseEnrollment.Role.CURRENT
                and existing.role != CourseEnrollment.Role.CURRENT
            ):
                existing.role = CourseEnrollment.Role.CURRENT
                existing.save(update_fields=["role", "updated_at"])
            enrollment.delete()
        else:
            enrollment.offering = target
            enrollment.save(update_fields=["offering", "updated_at"])

    for review in CourseReview.objects.select_for_update().filter(offering=source):
        existing = (
            CourseReview.objects.select_for_update()
            .filter(user_id=review.user_id, offering=target)
            .first()
        )
        if existing:
            # Keep the newer / non-hidden review on target
            if review.is_hidden and not existing.is_hidden:
                review.delete()
            elif (not review.is_hidden and existing.is_hidden) or (
                review.updated_at >= existing.updated_at and not review.is_hidden
            ):
                existing.delete()
                review.offering = target
                review.save(update_fields=["offering", "updated_at"])
            else:
                review.delete()
        else:
            review.offering = target
            review.save(update_fields=["offering", "updated_at"])

    # Avoid unique (user, slot_key) collisions when both sides had different cells
    for slot in TimetableSlot.objects.select_for_update().filter(offering=source):
        conflict = (
            TimetableSlot.objects.select_for_update()
            .filter(user_id=slot.user_id, slot_key=slot.slot_key)
            .exclude(pk=slot.pk)
            .first()
        )
        if conflict and conflict.offering_id == target.pk:
            slot.delete()
            continue
        slot.offering = target
        slot.name = target.title
        if not slot.slot_key.startswith("od"):
            slot.room = target.room or slot.room
        slot.credits = target.credits or slot.credits
        slot.save(
            update_fields=["offering", "name", "room", "credits", "updated_at"]
        )

    source.status = CourseOffering.Status.MERGED
    source.merged_into = target
    source.save(update_fields=["status", "merged_into", "updated_at"])
    return target


def serialize_review(review: CourseReview) -> dict:
    return {
        "id": review.pk,
        "offering_id": review.offering_id,
        "overall_rating": review.overall_rating,
        "difficulty_rating": review.difficulty_rating,
        "workload_rating": review.workload_rating,
        "attendance_rating": review.attendance_rating,
        "exam_rating": review.exam_rating,
        "comment": review.comment or "",
        "updated_at": review.updated_at.isoformat(),
        "is_own": False,
    }


def review_averages(offering: CourseOffering) -> dict:
    agg = CourseReview.objects.filter(
        offering=offering, is_hidden=False
    ).aggregate(
        count=Count("id"),
        overall=Avg("overall_rating"),
        difficulty=Avg("difficulty_rating"),
        workload=Avg("workload_rating"),
        attendance=Avg("attendance_rating"),
        exam=Avg("exam_rating"),
    )
    count = agg["count"] or 0
    if count == 0:
        return {
            "count": 0,
            "overall": None,
            "difficulty": None,
            "workload": None,
            "attendance": None,
            "exam": None,
        }

    def round_or_none(value):
        return round(float(value), 1) if value is not None else None

    return {
        "count": count,
        "overall": round_or_none(agg["overall"]),
        "difficulty": round_or_none(agg["difficulty"]),
        "workload": round_or_none(agg["workload"]),
        "attendance": round_or_none(agg["attendance"]),
        "exam": round_or_none(agg["exam"]),
    }


def user_can_review(user: AbstractBaseUser, offering: CourseOffering) -> bool:
    return CourseEnrollment.objects.filter(
        user_id=user.pk,
        offering_id=offering.pk,
        role__in=[
            CourseEnrollment.Role.CURRENT,
            CourseEnrollment.Role.PAST,
        ],
    ).exists()


@transaction.atomic
def upsert_review(
    *,
    user: AbstractBaseUser,
    offering: CourseOffering,
    overall_rating: int,
    difficulty_rating: int,
    workload_rating: int,
    attendance_rating: int,
    exam_rating: int,
    comment: str = "",
) -> CourseReview:
    offering = resolve_canonical_offering(offering)
    if not user_can_review(user, offering):
        raise ValueError("enrollment_required")

    for value in (
        overall_rating,
        difficulty_rating,
        workload_rating,
        attendance_rating,
        exam_rating,
    ):
        if not isinstance(value, int) or value < 1 or value > 5:
            raise ValueError("invalid_rating")

    comment = sanitize_plain_text(comment, max_len=MAX_COMMENT_LEN)

    review, _ = CourseReview.objects.update_or_create(
        user=user,
        offering=offering,
        defaults={
            "overall_rating": overall_rating,
            "difficulty_rating": difficulty_rating,
            "workload_rating": workload_rating,
            "attendance_rating": attendance_rating,
            "exam_rating": exam_rating,
            "comment": comment,
            "is_hidden": False,
        },
    )
    return review
