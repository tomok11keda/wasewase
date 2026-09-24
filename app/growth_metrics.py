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

# (year, month) -> University Verified Users target. Add later months here.
UNIVERSITY_VERIFIED_MONTHLY_GOALS: dict[tuple[int, int], int] = {
    (2026, 9): 150,
}

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


def _goal_payload(local_now: datetime, university_total: int) -> dict[str, Any] | None:
    key = (local_now.year, local_now.month)
    target = UNIVERSITY_VERIFIED_MONTHLY_GOALS.get(key)
    if target is None:
        return None
    pct = _ratio_pct(university_total, target)
    remaining = max(0, target - university_total)
    bar_pct = 0.0 if target == 0 else min(100.0, (university_total / target) * 100)
    return {
        "year": key[0],
        "month": key[1],
        "label": f"{calendar.month_name[key[1]]} Goal",
        "target": target,
        "current": university_total,
        "pct": pct,
        "pct_display": _format_pct(pct),
        "remaining": remaining,
        "bar_pct": bar_pct,
    }


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
        "goal": _goal_payload(local_now, university["total"]),
        "daily": daily,
    }
