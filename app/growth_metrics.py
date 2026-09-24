"""Admin Growth Dashboard KPIs.

Verified Users matches Django Admin's User changelist filter 「有効」:
that label is the Japanese translation of AbstractUser.is_active, and
app.UserAdmin does not override list_filter, so it inherits
DjangoUserAdmin.list_filter including ``is_active``. OTP signup creates
users with is_active=False and flips it to True on verification. There
is no separate email_verified field.

University Verified Users = Verified Users whose UserProfile.department
is not one of NON_UNIVERSITY_DEPARTMENT_VALUES. Those values are the
stored choice keys (identical to the Japanese labels).

Period metrics use User.date_joined (registration time). Verification
completed-at is not stored, so period counts mean:
"registered in period and currently verified (is_active=True)".
"""

from __future__ import annotations

import calendar
from datetime import date as date_cls
from datetime import datetime, timedelta
from typing import Any

from django.db.models import Count, Q, QuerySet
from django.db.models.functions import TruncDate
from django.utils import timezone

from .models import User

# Stored UserProfile.department values (FACULTY_CHOICES value == label).
NON_UNIVERSITY_DEPARTMENT_VALUES: tuple[str, ...] = (
    "その他",
    "附属・系属校",
)

# (year, month) -> University Verified Users month-end target.
# Single source of truth for the dashboard, roadmap, and a future simulator.
UNIVERSITY_VERIFIED_MONTHLY_GOALS: dict[tuple[int, int], int] = {
    (2026, 9): 150,
    (2026, 10): 500,
    (2026, 11): 1500,
    (2026, 12): 3000,
    (2027, 1): 3500,
    (2027, 2): 4000,
    (2027, 3): 5000,
    (2027, 4): 8000,
    (2027, 5): 10000,
}

STATUS_REACHED = "Reached"
STATUS_CURRENT = "Current"
STATUS_UPCOMING = "Upcoming"
STATUS_OPEN = "Open"

DAILY_GROWTH_DAYS = 7


def verified_users_qs() -> QuerySet:
    """Same condition as Admin User list_filter is_active=True (「有効」)."""
    return User.objects.filter(is_active=True)


def university_verified_users_qs() -> QuerySet:
    """Verified users excluding その他 and 附属・系属校 departments.

    Users with no profile, blank department, 卒業生, or a faculty name
    are included (they are not in NON_UNIVERSITY_DEPARTMENT_VALUES).
    exclude(profile__department__in=...) uses a subquery, so missing
    profiles are not dropped.
    """
    return verified_users_qs().exclude(
        profile__department__in=NON_UNIVERSITY_DEPARTMENT_VALUES
    )


def _ratio_pct(numerator: int, denominator: int, places: int = 1) -> float | None:
    if denominator == 0:
        return None
    return round(numerator / denominator * 100, places)


def _format_pct(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value:.1f}%"


def _local_now() -> datetime:
    return timezone.localtime(timezone.now())


def _day_start(local_dt: datetime) -> datetime:
    return local_dt.replace(hour=0, minute=0, second=0, microsecond=0)


def _month_start(local_dt: datetime) -> datetime:
    return local_dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _period_starts(local_now: datetime) -> dict[str, datetime]:
    today = _day_start(local_now)
    return {
        "today": today,
        "last_7_days": today - timedelta(days=DAILY_GROWTH_DAYS - 1),
        "this_month": _month_start(local_now),
    }


def _aggregate_periods(qs: QuerySet, starts: dict[str, datetime]) -> dict[str, int]:
    """One COUNT query: total + today + last 7 days + this month."""
    result = qs.aggregate(
        total=Count("pk"),
        today=Count("pk", filter=Q(date_joined__gte=starts["today"])),
        last_7_days=Count("pk", filter=Q(date_joined__gte=starts["last_7_days"])),
        this_month=Count("pk", filter=Q(date_joined__gte=starts["this_month"])),
    )
    return {
        "total": int(result["total"] or 0),
        "today": int(result["today"] or 0),
        "last_7_days": int(result["last_7_days"] or 0),
        "this_month": int(result["this_month"] or 0),
    }


def _counts_by_local_date(qs: QuerySet, since: datetime, tz) -> dict:
    rows = (
        qs.filter(date_joined__gte=since)
        .annotate(day=TruncDate("date_joined", tzinfo=tz))
        .values("day")
        .annotate(n=Count("pk"))
    )
    out = {}
    for row in rows:
        day = row["day"]
        if day is None:
            continue
        if isinstance(day, datetime):
            day = day.date()
        elif not isinstance(day, date_cls):
            continue
        out[day] = int(row["n"] or 0)
    return out


def month_key(when: datetime) -> tuple[int, int]:
    local = timezone.localtime(when) if timezone.is_aware(when) else when
    return (local.year, local.month)


def goal_for_month(year: int, month: int) -> int | None:
    """Look up a month-end University Verified target. None if unset."""
    return UNIVERSITY_VERIFIED_MONTHLY_GOALS.get((year, month))


def remaining_to_goal(goal: int, current: int) -> int:
    return max(goal - current, 0)


def monthly_goal_items() -> list[tuple[tuple[int, int], int]]:
    return sorted(UNIVERSITY_VERIFIED_MONTHLY_GOALS.items())


def milestone_status(
    key: tuple[int, int],
    *,
    current_key: tuple[int, int],
    current_count: int,
    goal: int,
) -> str:
    """Reached / Current / Upcoming (Open = past month not yet reached)."""
    if current_count >= goal:
        return STATUS_REACHED
    if key == current_key:
        return STATUS_CURRENT
    if key > current_key:
        return STATUS_UPCOMING
    return STATUS_OPEN


def _progress_payload(
    *,
    year: int,
    month: int,
    target: int,
    current: int,
    label: str,
) -> dict[str, Any]:
    pct = _ratio_pct(current, target)
    remaining = remaining_to_goal(target, current)
    bar_pct = 0.0 if target == 0 else min(100.0, (current / target) * 100)
    return {
        "year": year,
        "month": month,
        "label": label,
        "target": target,
        "target_display": f"{target:,}",
        "current": current,
        "current_display": f"{current:,}",
        "pct": pct,
        "pct_display": _format_pct(pct),
        "remaining": remaining,
        "remaining_display": f"{remaining:,}",
        "bar_pct": bar_pct,
    }


def current_month_goal_payload(
    when: datetime, university_total: int
) -> dict[str, Any] | None:
    year, month = month_key(when)
    target = goal_for_month(year, month)
    if target is None:
        return None
    return _progress_payload(
        year=year,
        month=month,
        target=target,
        current=university_total,
        label=f"{calendar.month_name[month]} Goal",
    )


def next_major_milestone_payload(
    when: datetime, university_total: int
) -> dict[str, Any] | None:
    """Earliest configured goal after the current calendar month."""
    current_key = month_key(when)
    for key, target in monthly_goal_items():
        if key > current_key:
            return _progress_payload(
                year=key[0],
                month=key[1],
                target=target,
                current=university_total,
                label="Next Major Milestone",
            )
    return None


def build_goal_roadmap(
    when: datetime, university_total: int
) -> list[dict[str, Any]]:
    """Month-end milestones derived only from UNIVERSITY_VERIFIED_MONTHLY_GOALS."""
    current_key = month_key(when)
    rows: list[dict[str, Any]] = []
    previous_goal: int | None = None
    for key, goal in monthly_goal_items():
        required = None if previous_goal is None else goal - previous_goal
        remaining = remaining_to_goal(goal, university_total)
        status = milestone_status(
            key,
            current_key=current_key,
            current_count=university_total,
            goal=goal,
        )
        rows.append(
            {
                "year": key[0],
                "month": key[1],
                "label": f"{calendar.month_abbr[key[1]]} {key[0]}",
                "goal": goal,
                "goal_display": f"{goal:,}",
                "required_growth": required,
                "required_growth_display": (
                    "—" if required is None else f"+{required:,}"
                ),
                "remaining": remaining,
                "remaining_display": f"{remaining:,}",
                "status": status,
                "is_current_month": key == current_key,
            }
        )
        previous_goal = goal
    return rows


def _goal_payload(local_now: datetime, university_total: int) -> dict[str, Any] | None:
    return current_month_goal_payload(local_now, university_total)


def build_growth_dashboard() -> dict[str, Any]:
    """Aggregate KPIs for the Admin dashboard. No per-user fetch, no PII."""
    local_now = _local_now()
    tz = timezone.get_current_timezone()
    starts = _period_starts(local_now)

    verified = _aggregate_periods(verified_users_qs(), starts)
    university = _aggregate_periods(university_verified_users_qs(), starts)

    share = _ratio_pct(university["total"], verified["total"])
    week_start = starts["last_7_days"]
    verified_by_day = _counts_by_local_date(verified_users_qs(), week_start, tz)
    university_by_day = _counts_by_local_date(
        university_verified_users_qs(), week_start, tz
    )

    today_date = starts["today"].date()
    daily = []
    for offset in range(DAILY_GROWTH_DAYS - 1, -1, -1):
        day = today_date - timedelta(days=offset)
        daily.append(
            {
                "date": day,
                "label": f"{day.strftime('%b')} {day.day}",
                "university": university_by_day.get(day, 0),
                "verified": verified_by_day.get(day, 0),
            }
        )

    return {
        "verified_count": verified["total"],
        "university_count": university["total"],
        "university_share_pct": share,
        "university_share_display": _format_pct(share),
        "verified_today": verified["today"],
        "verified_last_7_days": verified["last_7_days"],
        "verified_this_month": verified["this_month"],
        "university_today": university["today"],
        "university_last_7_days": university["last_7_days"],
        "university_this_month": university["this_month"],
        "period_note": (
            "Registered in period and currently verified. "
            "Verification-completed-at is not stored; date_joined is used."
        ),
        "excluded_departments": NON_UNIVERSITY_DEPARTMENT_VALUES,
        "goal": current_month_goal_payload(local_now, university["total"]),
        "next_major": next_major_milestone_payload(local_now, university["total"]),
        "roadmap": build_goal_roadmap(local_now, university["total"]),
        "daily": daily,
    }
