"""授業カレンダー例外（特定日スキップ / 復元）テスト。"""

from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.test import Client, TestCase

from app.course_calendar_exception_services import (
    create_course_calendar_exception,
    delete_course_calendar_exception,
    list_skipped_for_month,
)
from app.course_services import create_offering, enroll_user_in_offering
from app.models import (
    CourseCalendarException,
    CourseEnrollment,
    CourseOffering,
    TimetableSlot,
)

User = get_user_model()


class CourseCalendarExceptionTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            email="cce-a@ex.com", password="pass12345"
        )
        self.other = User.objects.create_user(
            email="cce-b@ex.com", password="pass12345"
        )
        self.client.force_login(self.user)
        self.offering, _ = create_offering(
            user=self.user,
            title="カレンダー例外テスト授業",
            instructor="教員A",
            academic_year=2026,
            semester="spring",
            day_of_week=0,  # 月曜
            period=2,
            force_create=True,
        )
        enroll_user_in_offering(self.user, self.offering)
        # 次の月曜日
        today = date.today()
        days_ahead = (0 - today.weekday()) % 7
        if days_ahead == 0:
            days_ahead = 7
        self.target = today + timedelta(days=days_ahead)
        self.prev_week = self.target - timedelta(days=7)
        self.next_week = self.target + timedelta(days=7)

    def test_skip_current_enrollment_and_month_payload(self):
        res = self.client.post(
            "/api/v1/calendar/course-exceptions/",
            data={
                "offering_id": self.offering.pk,
                "date": self.target.isoformat(),
                "status": "skipped",
            },
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 201, res.content)
        data = res.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["exception"]["date"], self.target.isoformat())
        self.assertEqual(data["exception"]["status"], "skipped")

        month = self.client.get(
            "/api/v1/calendar/events/",
            {"year": self.target.year, "month": self.target.month},
        )
        self.assertEqual(month.status_code, 200)
        skipped = month.json().get("course_exceptions") or []
        self.assertTrue(
            any(
                row["offering_id"] == self.offering.pk
                and row["date"] == self.target.isoformat()
                for row in skipped
            )
        )
        # 前後週は一覧に含まれない（その日だけ）
        dates = {
            row["date"]
            for row in skipped
            if row["offering_id"] == self.offering.pk
        }
        self.assertIn(self.target.isoformat(), dates)
        self.assertNotIn(self.prev_week.isoformat(), dates)
        self.assertNotIn(self.next_week.isoformat(), dates)

    def test_duplicate_is_idempotent(self):
        first = create_course_calendar_exception(
            self.user,
            offering_id=self.offering.pk,
            date_raw=self.target.isoformat(),
        )
        second = create_course_calendar_exception(
            self.user,
            offering_id=self.offering.pk,
            date_raw=self.target.isoformat(),
        )
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(
            CourseCalendarException.objects.filter(
                user=self.user, offering=self.offering, date=self.target
            ).count(),
            1,
        )

    def test_restore_deletes_exception(self):
        exc = create_course_calendar_exception(
            self.user,
            offering_id=self.offering.pk,
            date_raw=self.target.isoformat(),
        )
        res = self.client.post(
            f"/api/v1/calendar/course-exceptions/{exc.pk}/delete/",
            data={},
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 200, res.content)
        self.assertFalse(
            CourseCalendarException.objects.filter(pk=exc.pk).exists()
        )

    def test_cannot_delete_others_exception(self):
        exc = create_course_calendar_exception(
            self.user,
            offering_id=self.offering.pk,
            date_raw=self.target.isoformat(),
        )
        other_client = Client()
        other_client.force_login(self.other)
        res = other_client.post(
            f"/api/v1/calendar/course-exceptions/{exc.pk}/delete/",
            data={},
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 403)
        self.assertTrue(
            CourseCalendarException.objects.filter(pk=exc.pk).exists()
        )

    def test_unenrolled_cannot_skip(self):
        guest = User.objects.create_user(
            email="cce-guest@ex.com", password="pass12345"
        )
        guest_client = Client()
        guest_client.force_login(guest)
        res = guest_client.post(
            "/api/v1/calendar/course-exceptions/",
            data={
                "offering_id": self.offering.pk,
                "date": self.target.isoformat(),
                "status": "skipped",
            },
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.json().get("error"), "enrollment_required")

    def test_hidden_and_merged_rejected(self):
        self.offering.status = CourseOffering.Status.HIDDEN
        self.offering.save(update_fields=["status", "updated_at"])
        with self.assertRaises(ValueError) as ctx:
            create_course_calendar_exception(
                self.user,
                offering_id=self.offering.pk,
                date_raw=self.target.isoformat(),
            )
        self.assertEqual(str(ctx.exception), "offering_hidden")

        self.offering.status = CourseOffering.Status.MERGED
        self.offering.save(update_fields=["status", "updated_at"])
        with self.assertRaises(ValueError) as ctx2:
            create_course_calendar_exception(
                self.user,
                offering_id=self.offering.pk,
                date_raw=self.target.isoformat(),
            )
        self.assertEqual(str(ctx2.exception), "offering_merged")

    def test_skip_keeps_enrollment_and_slot(self):
        create_course_calendar_exception(
            self.user,
            offering_id=self.offering.pk,
            date_raw=self.target.isoformat(),
        )
        self.assertTrue(
            CourseEnrollment.objects.filter(
                user=self.user,
                offering=self.offering,
                role=CourseEnrollment.Role.CURRENT,
            ).exists()
        )
        self.assertTrue(
            TimetableSlot.objects.filter(
                user=self.user, offering=self.offering
            ).exists()
        )

    def test_invalid_date_rejected(self):
        res = self.client.post(
            "/api/v1/calendar/course-exceptions/",
            data={
                "offering_id": self.offering.pk,
                "date": "not-a-date",
                "status": "skipped",
            },
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json().get("error"), "date_invalid")

    def test_list_and_month_filter(self):
        create_course_calendar_exception(
            self.user,
            offering_id=self.offering.pk,
            date_raw=self.target.isoformat(),
        )
        listing = self.client.get("/api/v1/calendar/course-exceptions/")
        self.assertEqual(listing.status_code, 200)
        self.assertGreaterEqual(listing.json()["count"], 1)
        month_rows = list_skipped_for_month(
            self.user, self.target.year, self.target.month
        )
        self.assertTrue(
            any(row["date"] == self.target.isoformat() for row in month_rows)
        )
