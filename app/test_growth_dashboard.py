"""Growth Dashboard KPIs and Admin access."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .constants import FACULTY_CHOICES
from .growth_metrics import (
    NON_UNIVERSITY_DEPARTMENT_VALUES,
    STATUS_CURRENT,
    STATUS_REACHED,
    STATUS_UPCOMING,
    UNIVERSITY_VERIFIED_MONTHLY_GOALS,
    build_goal_roadmap,
    build_growth_dashboard,
    current_month_goal_payload,
    goal_for_month,
    remaining_to_goal,
    university_verified_users_qs,
    verified_users_qs,
)
from .models import UserProfile

User = get_user_model()
TOKYO = ZoneInfo("Asia/Tokyo")


def _aware(year, month, day, hour=12, minute=0):
    return datetime(year, month, day, hour, minute, tzinfo=TOKYO)


def _make_user(
    *,
    email: str,
    is_active: bool = True,
    department: str | None = "商学部",
    date_joined=None,
    is_staff: bool = False,
    username: str | None = None,
):
    kwargs = {
        "email": email,
        "password": "pass12345",
        "is_active": is_active,
        "is_staff": is_staff,
    }
    if username:
        kwargs["username"] = username
    if date_joined is not None:
        kwargs["date_joined"] = date_joined
    user = User.objects.create_user(**kwargs)
    if date_joined is not None:
        user.date_joined = date_joined
        user.save(update_fields=["date_joined"])
    if department is not None:
        UserProfile.objects.update_or_create(
            user=user,
            defaults={"department": department},
        )
    return user


@override_settings(BROWSE_MODE_GATE_ENABLED=False)
class GrowthMetricsTests(TestCase):
    def test_faculty_choice_values_match_exclusion_keys(self):
        stored = {value for value, _label in FACULTY_CHOICES}
        for value in NON_UNIVERSITY_DEPARTMENT_VALUES:
            self.assertIn(value, stored)
        self.assertEqual(NON_UNIVERSITY_DEPARTMENT_VALUES, ("その他", "附属・系属校"))

    def test_verified_user_is_counted(self):
        _make_user(email="v1@waseda.jp", is_active=True, department="商学部")
        self.assertEqual(verified_users_qs().count(), 1)

    def test_inactive_user_is_not_counted(self):
        _make_user(email="pending@waseda.jp", is_active=False, department="商学部")
        data = build_growth_dashboard()
        self.assertEqual(data["verified_count"], 0)
        self.assertEqual(data["university_count"], 0)

    def test_faculty_verified_counts_as_university(self):
        _make_user(email="law@waseda.jp", is_active=True, department="法学部")
        self.assertEqual(university_verified_users_qs().count(), 1)

    def test_other_department_is_verified_but_not_university(self):
        _make_user(email="other@waseda.jp", is_active=True, department="その他")
        data = build_growth_dashboard()
        self.assertEqual(data["verified_count"], 1)
        self.assertEqual(data["university_count"], 0)

    def test_affiliated_school_is_verified_but_not_university(self):
        _make_user(
            email="affil@waseda.jp",
            is_active=True,
            department="附属・系属校",
        )
        data = build_growth_dashboard()
        self.assertEqual(data["verified_count"], 1)
        self.assertEqual(data["university_count"], 0)

    def test_university_share_calculation(self):
        _make_user(email="a@waseda.jp", department="商学部")
        _make_user(email="b@waseda.jp", department="法学部")
        _make_user(email="c@waseda.jp", department="その他")
        _make_user(email="d@waseda.jp", department="附属・系属校")
        data = build_growth_dashboard()
        self.assertEqual(data["verified_count"], 4)
        self.assertEqual(data["university_count"], 2)
        self.assertEqual(data["university_share_pct"], 50.0)
        self.assertEqual(data["university_share_display"], "50.0%")

    def test_university_share_zero_verified(self):
        data = build_growth_dashboard()
        self.assertEqual(data["verified_count"], 0)
        self.assertEqual(data["university_count"], 0)
        self.assertIsNone(data["university_share_pct"])
        self.assertEqual(data["university_share_display"], "—")

    def test_alumni_is_included_in_university_verified(self):
        _make_user(email="alum@waseda.jp", is_active=True, department="卒業生")
        data = build_growth_dashboard()
        self.assertEqual(data["verified_count"], 1)
        self.assertEqual(data["university_count"], 1)

    def test_blank_department_is_included_in_university_verified(self):
        _make_user(email="blank@waseda.jp", is_active=True, department="")
        data = build_growth_dashboard()
        self.assertEqual(data["verified_count"], 1)
        self.assertEqual(data["university_count"], 1)

    def test_missing_profile_is_included_in_university_verified(self):
        user = User.objects.create_user(
            email="noprof@waseda.jp",
            password="pass12345",
            is_active=True,
            username="noprof_user",
        )
        self.assertFalse(UserProfile.objects.filter(user=user).exists())
        data = build_growth_dashboard()
        self.assertEqual(data["verified_count"], 1)
        self.assertEqual(data["university_count"], 1)

    def test_share_one_decimal_like_example(self):
        for i in range(86):
            _make_user(
                email=f"uni{i}@waseda.jp",
                department="商学部",
                username=f"uni_{i:03d}",
            )
        for i in range(25):
            _make_user(
                email=f"oth{i}@waseda.jp",
                department="その他",
                username=f"oth_{i:03d}",
            )
        data = build_growth_dashboard()
        self.assertEqual(data["verified_count"], 111)
        self.assertEqual(data["university_count"], 86)
        self.assertEqual(data["university_share_display"], "77.5%")

    @patch("app.growth_metrics.timezone.now")
    def test_period_boundaries_use_date_joined(self, mock_now):
        mock_now.return_value = _aware(2026, 9, 23, 22, 0)

        today = _make_user(
            email="today@waseda.jp",
            department="商学部",
            date_joined=_aware(2026, 9, 23, 0, 0),
        )
        last_week_ok = _make_user(
            email="d17@waseda.jp",
            department="商学部",
            date_joined=_aware(2026, 9, 17, 0, 0),
        )
        last_week_out = _make_user(
            email="d16@waseda.jp",
            department="商学部",
            date_joined=_aware(2026, 9, 16, 23, 59),
        )
        month_ok = _make_user(
            email="sep1@waseda.jp",
            department="商学部",
            date_joined=_aware(2026, 9, 1, 0, 0),
        )
        month_out = _make_user(
            email="aug@waseda.jp",
            department="商学部",
            date_joined=_aware(2026, 8, 31, 23, 59),
        )
        inactive_today = _make_user(
            email="inactive-today@waseda.jp",
            is_active=False,
            department="商学部",
            date_joined=_aware(2026, 9, 23, 10, 0),
        )
        other_today = _make_user(
            email="other-today@waseda.jp",
            department="その他",
            date_joined=_aware(2026, 9, 23, 11, 0),
        )

        data = build_growth_dashboard()
        self.assertEqual(data["verified_today"], 2)  # today + other_today
        self.assertEqual(data["university_today"], 1)  # faculty today only
        self.assertEqual(data["verified_last_7_days"], 3)  # today, d17, other_today
        self.assertEqual(data["university_last_7_days"], 2)  # today, d17
        # Sep 16 is outside last 7 days but still in this month.
        self.assertEqual(data["verified_this_month"], 5)
        self.assertEqual(data["university_this_month"], 4)
        self.assertFalse(
            verified_users_qs()
            .filter(
                pk=last_week_out.pk,
                date_joined__gte=_aware(2026, 9, 17, 0, 0),
            )
            .exists()
        )
        self.assertTrue(verified_users_qs().filter(pk=month_ok.pk).exists())
        self.assertFalse(
            verified_users_qs()
            .filter(
                pk=month_out.pk,
                date_joined__gte=_aware(2026, 9, 1, 0, 0),
            )
            .exists()
        )
        self.assertFalse(verified_users_qs().filter(pk=inactive_today.pk).exists())
        self.assertIn("Registered in period and currently verified", data["period_note"])

        daily = {row["label"]: row for row in data["daily"]}
        self.assertEqual(list(daily)[0], "Sep 17")
        self.assertEqual(list(daily)[-1], "Sep 23")
        self.assertNotIn("Sep 16", daily)
        self.assertEqual(daily["Sep 23"]["verified"], 2)
        self.assertEqual(daily["Sep 23"]["university"], 1)
        self.assertEqual(daily["Sep 17"]["university"], 1)
        self.assertEqual(data["goal"]["label"], "September Goal")
        self.assertEqual(data["goal"]["target"], 150)
        self.assertEqual(
            data["goal"]["remaining"],
            150 - data["university_count"],
        )
        self.assertEqual(UNIVERSITY_VERIFIED_MONTHLY_GOALS[(2026, 9)], 150)


@override_settings(BROWSE_MODE_GATE_ENABLED=False)
class GrowthRoadmapTests(TestCase):
    def test_all_nine_month_goals_are_defined(self):
        expected = {
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
        self.assertEqual(UNIVERSITY_VERIFIED_MONTHLY_GOALS, expected)
        self.assertEqual(goal_for_month(2026, 9), 150)
        self.assertEqual(goal_for_month(2026, 10), 500)
        self.assertEqual(goal_for_month(2026, 12), 3000)
        self.assertEqual(goal_for_month(2027, 1), 3500)
        self.assertEqual(goal_for_month(2027, 5), 10000)
        self.assertIsNone(goal_for_month(2026, 8))
        self.assertIsNone(goal_for_month(2027, 6))

    def test_required_growth_is_difference_from_previous_goal(self):
        rows = build_goal_roadmap(_aware(2026, 9, 23), university_total=85)
        by_label = {row["label"]: row for row in rows}
        self.assertIsNone(by_label["Sep 2026"]["required_growth"])
        self.assertEqual(by_label["Sep 2026"]["required_growth_display"], "—")
        self.assertEqual(by_label["Oct 2026"]["required_growth"], 350)
        self.assertEqual(by_label["Nov 2026"]["required_growth"], 1000)
        self.assertEqual(by_label["Dec 2026"]["required_growth"], 1500)
        self.assertEqual(by_label["Jan 2027"]["required_growth"], 500)
        self.assertEqual(by_label["Feb 2027"]["required_growth"], 500)
        self.assertEqual(by_label["Mar 2027"]["required_growth"], 1000)
        self.assertEqual(by_label["Apr 2027"]["required_growth"], 3000)
        self.assertEqual(by_label["May 2027"]["required_growth"], 2000)

    def test_remaining_never_goes_negative(self):
        self.assertEqual(remaining_to_goal(150, 85), 65)
        self.assertEqual(remaining_to_goal(150, 150), 0)
        self.assertEqual(remaining_to_goal(150, 200), 0)
        rows = build_goal_roadmap(_aware(2026, 10, 1), university_total=600)
        self.assertTrue(all(row["remaining"] >= 0 for row in rows))
        self.assertEqual(rows[0]["remaining"], 0)  # Sep 150 already passed
        self.assertEqual(rows[1]["remaining"], 0)  # Oct 500 already passed
        self.assertEqual(rows[2]["remaining"], 900)  # Nov 1500

    @patch("app.growth_metrics.timezone.now")
    def test_current_month_goal_follows_local_calendar(self, mock_now):
        mock_now.return_value = _aware(2026, 9, 23, 22, 0)
        data = build_growth_dashboard()
        self.assertEqual(data["goal"]["label"], "September Goal")
        self.assertEqual(data["goal"]["target"], 150)

        mock_now.return_value = _aware(2026, 10, 5, 9, 0)
        data = build_growth_dashboard()
        self.assertEqual(data["goal"]["label"], "October Goal")
        self.assertEqual(data["goal"]["target"], 500)

        mock_now.return_value = _aware(2026, 12, 1, 0, 0)
        data = build_growth_dashboard()
        self.assertEqual(data["goal"]["label"], "December Goal")
        self.assertEqual(data["goal"]["target"], 3000)

        mock_now.return_value = _aware(2027, 1, 15, 12, 0)
        data = build_growth_dashboard()
        self.assertEqual(data["goal"]["label"], "January Goal")
        self.assertEqual(data["goal"]["target"], 3500)

        mock_now.return_value = _aware(2027, 5, 31, 23, 0)
        data = build_growth_dashboard()
        self.assertEqual(data["goal"]["label"], "May Goal")
        self.assertEqual(data["goal"]["target"], 10000)

    @patch("app.growth_metrics.timezone.now")
    def test_missing_month_goal_does_not_error(self, mock_now):
        mock_now.return_value = _aware(2026, 8, 1, 12, 0)
        data = build_growth_dashboard()
        self.assertIsNone(data["goal"])
        self.assertEqual(data["next_major"]["target"], 150)
        self.assertEqual(len(data["roadmap"]), 9)

        mock_now.return_value = _aware(2027, 6, 1, 12, 0)
        data = build_growth_dashboard()
        self.assertIsNone(data["goal"])
        self.assertIsNone(data["next_major"])
        self.assertEqual(data["verified_count"], 0)

    def test_status_reached_current_upcoming(self):
        rows = build_goal_roadmap(_aware(2026, 10, 12), university_total=160)
        by_label = {row["label"]: row for row in rows}
        self.assertEqual(by_label["Sep 2026"]["status"], STATUS_REACHED)
        self.assertEqual(by_label["Oct 2026"]["status"], STATUS_CURRENT)
        self.assertTrue(by_label["Oct 2026"]["is_current_month"])
        self.assertEqual(by_label["Nov 2026"]["status"], STATUS_UPCOMING)
        self.assertEqual(by_label["May 2027"]["status"], STATUS_UPCOMING)

        reached_current = build_goal_roadmap(
            _aware(2026, 9, 30), university_total=200
        )
        sep = next(r for r in reached_current if r["label"] == "Sep 2026")
        oct_row = next(r for r in reached_current if r["label"] == "Oct 2026")
        self.assertEqual(sep["status"], STATUS_REACHED)
        self.assertTrue(sep["is_current_month"])
        self.assertEqual(oct_row["status"], STATUS_UPCOMING)

    @patch("app.growth_metrics.timezone.now")
    def test_next_major_milestone_is_month_after_current(self, mock_now):
        mock_now.return_value = _aware(2026, 9, 23, 12, 0)
        _make_user(email="one@waseda.jp", department="商学部")
        data = build_growth_dashboard()
        self.assertEqual(data["next_major"]["label"], "Next Major Milestone")
        self.assertEqual(data["next_major"]["target"], 500)
        self.assertEqual(data["next_major"]["current"], 1)

    def test_current_month_goal_payload_helper_is_reusable(self):
        payload = current_month_goal_payload(_aware(2026, 11, 2), 80)
        self.assertEqual(payload["target"], 1500)
        self.assertEqual(payload["remaining"], 1420)
        self.assertEqual(payload["label"], "November Goal")
        self.assertIsNone(current_month_goal_payload(_aware(2027, 7, 1), 80))


@override_settings(BROWSE_MODE_GATE_ENABLED=False)
class GrowthDashboardAdminAccessTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_superuser(
            email="growth-admin@waseda.jp",
            password="pass12345",
        )
        self.member = User.objects.create_user(
            email="growth-member@waseda.jp",
            password="pass12345",
            username="growth_member",
            is_active=True,
        )
        UserProfile.objects.update_or_create(
            user=self.member,
            defaults={"department": "商学部"},
        )

    def test_anonymous_cannot_open_dashboard(self):
        for url in (reverse("admin:index"), reverse("admin:growth_dashboard")):
            response = self.client.get(url)
            self.assertEqual(response.status_code, 302)
            self.assertIn("/admin/login", response.url)

    def test_non_staff_cannot_open_dashboard(self):
        self.client.force_login(self.member)
        for url in (reverse("admin:index"), reverse("admin:growth_dashboard")):
            response = self.client.get(url)
            self.assertEqual(response.status_code, 302)
            self.assertIn("/admin/login", response.url)

    def test_staff_without_superuser_can_open_dashboard(self):
        staff_only = User.objects.create_user(
            email="growth-staff@waseda.jp",
            password="pass12345",
            username="growth_staff",
            is_staff=True,
            is_superuser=False,
            is_active=True,
        )
        self.client.force_login(staff_only)
        response = self.client.get(reverse("admin:growth_dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "WaseWase Growth Dashboard")

    def test_staff_sees_kpis_without_pii(self):
        self.client.force_login(self.staff)
        index = self.client.get(reverse("admin:index"))
        self.assertEqual(index.status_code, 200)
        self.assertContains(index, "WaseWase Growth Dashboard")
        self.assertContains(index, "University Verified Users")
        self.assertContains(index, "University Share")
        self.assertNotContains(index, "growth-member@waseda.jp")
        self.assertContains(
            index,
            "Registered in period and currently verified",
        )

        page = self.client.get(reverse("admin:growth_dashboard"))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "University Verified Users")
        self.assertContains(page, "University Verified Roadmap")
        self.assertNotContains(page, "growth-member@waseda.jp")

    def test_existing_user_changelist_still_works(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse("admin:app_user_changelist"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "growth-member@waseda.jp")
