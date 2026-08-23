"""授業欠席記録 + CourseMeeting 正規化テスト。"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.utils import timezone

from app.course_attendance_services import (
    absence_count,
    create_attendance_record,
)
from app.course_calendar_exception_services import create_course_calendar_exception
from app.course_meeting_services import list_meetings
from app.course_services import (
    clear_slot_and_sync_enrollment,
    create_offering,
    enroll_user_in_offering,
)
from app.models import (
    CourseAttendanceRecord,
    CourseEnrollment,
    CourseOffering,
    TimetableSlot,
)

User = get_user_model()


class CourseMeetingAttendanceTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            email="mtg-a@ex.com", password="pass12345"
        )
        self.other = User.objects.create_user(
            email="mtg-b@ex.com", password="pass12345"
        )
        self.client.force_login(self.user)

        self.offering, _ = create_offering(
            user=self.user,
            title="週2正規化テスト",
            instructor="教員C",
            academic_year=2026,
            semester="spring",
            day_of_week=1,
            period=2,
            force_create=True,
            meetings=[
                {"day_of_week": 1, "period": 2, "period_kind": "period"},
                {"day_of_week": 3, "period": 3, "period_kind": "period"},
            ],
        )
        enroll_user_in_offering(self.user, self.offering)

        today = timezone.localdate()
        self.tue = today - timedelta(days=((today.weekday() - 1) % 7))
        if self.tue > today:
            self.tue -= timedelta(days=7)
        self.thu = today - timedelta(days=((today.weekday() - 3) % 7))
        if self.thu > today:
            self.thu -= timedelta(days=7)
        if self.thu == self.tue:
            self.thu -= timedelta(days=7)

    def test_one_offering_two_meetings(self):
        meetings = list_meetings(self.offering)
        self.assertEqual(len(meetings), 2)
        self.assertEqual(
            CourseOffering.objects.filter(
                title_normalized=self.offering.title_normalized,
                instructor_normalized=self.offering.instructor_normalized,
                academic_year=2026,
                semester="spring",
                status=CourseOffering.Status.ACTIVE,
            ).count(),
            1,
        )

    def test_enroll_creates_two_slots(self):
        keys = set(
            TimetableSlot.objects.filter(
                user=self.user, offering=self.offering
            ).values_list("slot_key", flat=True)
        )
        self.assertEqual(keys, {"p2-d1", "p3-d3"})

    def test_shared_absence_count_on_same_offering(self):
        create_attendance_record(
            self.user,
            offering_id=self.offering.pk,
            date_raw=self.tue.isoformat(),
        )
        create_attendance_record(
            self.user,
            offering_id=self.offering.pk,
            date_raw=self.thu.isoformat(),
        )
        self.assertEqual(absence_count(self.user, self.offering), 2)
        detail = self.client.get(
            f"/api/v1/courses/offerings/{self.offering.pk}/"
        )
        self.assertEqual(detail.json()["attendance"]["absence_count"], 2)

    def test_duplicate_same_day_idempotent(self):
        a = create_attendance_record(
            self.user,
            offering_id=self.offering.pk,
            date_raw=self.tue.isoformat(),
        )
        b = create_attendance_record(
            self.user,
            offering_id=self.offering.pk,
            date_raw=self.tue.isoformat(),
        )
        self.assertEqual(a.pk, b.pk)
        self.assertEqual(
            CourseAttendanceRecord.objects.filter(
                user=self.user, offering=self.offering
            ).count(),
            1,
        )

    def test_adding_meeting_to_existing_via_create(self):
        offering2, dups = create_offering(
            user=self.user,
            title="週2正規化テスト",
            instructor="教員C",
            academic_year=2026,
            semester="spring",
            day_of_week=4,
            period=1,
            force_create=False,
        )
        self.assertEqual(offering2.pk, self.offering.pk)
        self.assertEqual(dups, [])
        days = {m.day_of_week for m in list_meetings(self.offering)}
        self.assertIn(4, days)
        self.assertEqual(len(list_meetings(self.offering)), 3)

    def test_clear_one_slot_keeps_enrollment(self):
        clear_slot_and_sync_enrollment(self.user, "p2-d1")
        self.assertTrue(
            CourseEnrollment.objects.filter(
                user=self.user,
                offering=self.offering,
                role=CourseEnrollment.Role.CURRENT,
            ).exists()
        )
        self.assertTrue(
            TimetableSlot.objects.filter(
                user=self.user, offering=self.offering, slot_key="p3-d3"
            ).exists()
        )

    def test_calendar_exception_blocks_absence(self):
        create_course_calendar_exception(
            self.user,
            offering_id=self.offering.pk,
            date_raw=self.tue.isoformat(),
        )
        with self.assertRaises(ValueError) as ctx:
            create_attendance_record(
                self.user,
                offering_id=self.offering.pk,
                date_raw=self.tue.isoformat(),
            )
        self.assertEqual(str(ctx.exception), "date_calendar_skipped")

    def test_other_user_cannot_view_attendance(self):
        create_attendance_record(
            self.user,
            offering_id=self.offering.pk,
            date_raw=self.tue.isoformat(),
        )
        other = Client()
        other.force_login(self.other)
        res = other.get(
            f"/api/v1/courses/offerings/{self.offering.pk}/attendance/"
        )
        self.assertEqual(res.status_code, 403)
        detail = other.get(f"/api/v1/courses/offerings/{self.offering.pk}/")
        self.assertNotIn("attendance", detail.json())

    def test_serialize_includes_meetings(self):
        res = self.client.get(f"/api/v1/courses/offerings/{self.offering.pk}/")
        self.assertEqual(res.status_code, 200)
        meetings = res.json()["offering"]["meetings"]
        self.assertEqual(len(meetings), 2)
        self.assertIn("・", res.json()["offering"]["schedule_label"])
