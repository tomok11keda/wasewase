"""複数 CourseMeeting での Offering 作成テスト。"""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase

from app.course_services import create_offering, enroll_user_in_offering
from app.models import (
    CourseEnrollment,
    CourseMeeting,
    CourseOffering,
    TimetableSlot,
)
from app.timetable_services import upsert_timetable_slot

User = get_user_model()


class MultiMeetingCreateTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            email="mm-a@ex.com", password="pass12345"
        )
        self.client.force_login(self.user)

    def test_create_two_meetings_one_enrollment_two_slots(self):
        res = self.client.post(
            "/api/v1/courses/offerings/",
            data={
                "title": "週2作成テスト",
                "instructor": "教員E",
                "academic_year": 2026,
                "semester": "spring",
                "day_of_week": 1,
                "period": 2,
                "period_kind": "period",
                "meetings": [
                    {"day_of_week": 1, "period": 2, "period_kind": "period"},
                    {"day_of_week": 3, "period": 3, "period_kind": "period"},
                ],
                "enroll": True,
            },
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 200, res.content)
        data = res.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["meeting_count"], 2)
        offering_id = data["offering"]["id"]
        self.assertEqual(len(data["offering"]["meetings"]), 2)
        self.assertEqual(
            CourseEnrollment.objects.filter(
                user=self.user, offering_id=offering_id
            ).count(),
            1,
        )
        keys = set(
            TimetableSlot.objects.filter(
                user=self.user, offering_id=offering_id
            ).values_list("slot_key", flat=True)
        )
        self.assertEqual(keys, {"p2-d1", "p3-d3"})
        self.assertEqual(len(data.get("slots") or []), 2)

    def test_duplicate_meeting_specs_deduped(self):
        offering, _ = create_offering(
            user=self.user,
            title="重複Meeting防止",
            instructor="教員F",
            academic_year=2026,
            semester="spring",
            day_of_week=0,
            period=1,
            force_create=True,
            meetings=[
                {"day_of_week": 0, "period": 1, "period_kind": "period"},
                {"day_of_week": 0, "period": 1, "period_kind": "period"},
            ],
        )
        self.assertEqual(
            CourseMeeting.objects.filter(offering=offering).count(), 1
        )

    def test_slot_conflict_blocks_create_enroll(self):
        upsert_timetable_slot(
            self.user,
            slot_key="p3-d3",
            name="既存授業",
            room="",
            credits="",
            memo="",
        )
        res = self.client.post(
            "/api/v1/courses/offerings/",
            data={
                "title": "衝突テスト",
                "instructor": "教員G",
                "academic_year": 2026,
                "semester": "spring",
                "meetings": [
                    {"day_of_week": 1, "period": 2, "period_kind": "period"},
                    {"day_of_week": 3, "period": 3, "period_kind": "period"},
                ],
                "enroll": True,
            },
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 409, res.content)
        self.assertEqual(res.json()["error"], "slot_conflict")
        self.assertFalse(
            CourseOffering.objects.filter(title="衝突テスト").exists()
        )

    def test_single_meeting_still_works(self):
        res = self.client.post(
            "/api/v1/courses/offerings/",
            data={
                "title": "週1作成",
                "instructor": "教員H",
                "academic_year": 2026,
                "semester": "spring",
                "day_of_week": 2,
                "period": 4,
                "period_kind": "period",
                "enroll": True,
            },
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(res.json()["meeting_count"], 1)
        self.assertEqual(
            TimetableSlot.objects.filter(user=self.user).count(), 1
        )
