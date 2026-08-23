"""Course discovery for Community hub."""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.utils import timezone

from app.course_discover_services import build_course_discover_payload
from app.course_services import create_offering, enroll_user_in_offering
from app.models import (
    ChatMessage,
    ChatRoom,
    CourseEnrollment,
    CourseOffering,
    CourseReview,
)

User = get_user_model()


class CourseDiscoverTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            email="disc-a@ex.com", password="pass12345"
        )
        self.other = User.objects.create_user(
            email="disc-b@ex.com", password="pass12345"
        )
        self.offering, _ = create_offering(
            user=self.user,
            title="ディスカバリー授業",
            instructor="教員D",
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
        CourseReview.objects.create(
            user=self.user,
            offering=self.offering,
            overall_rating=4,
            difficulty_rating=3,
            workload_rating=3,
            attendance_rating=3,
            exam_rating=3,
            comment="good",
        )
        room = ChatRoom.objects.create(kind=ChatRoom.Kind.COURSE)
        self.offering.chat_room = room
        self.offering.save(update_fields=["chat_room", "updated_at"])
        ChatMessage.objects.create(
            room=room, sender=self.user, body="hello talk"
        )
        ChatMessage.objects.create(
            room=room,
            sender=self.user,
            body="hidden",
            is_hidden=True,
        )
        ChatMessage.objects.create(
            room=room,
            sender=self.user,
            body="deleted",
            deleted_at=timezone.now(),
        )

    def test_discover_api_sections(self):
        self.client.force_login(self.user)
        res = self.client.get("/api/v1/courses/discover/")
        self.assertEqual(res.status_code, 200, res.content)
        data = res.json()
        self.assertTrue(data["ok"])
        enrolled_ids = [c["id"] for c in data["enrolled"]]
        self.assertIn(self.offering.pk, enrolled_ids)
        active_ids = [c["id"] for c in data["active"]]
        self.assertIn(self.offering.pk, active_ids)
        popular_ids = [c["id"] for c in data["popular"]]
        self.assertIn(self.offering.pk, popular_ids)

        card = next(c for c in data["enrolled"] if c["id"] == self.offering.pk)
        self.assertEqual(len(card["meetings"]), 2)
        self.assertIn("・", card["schedule_label"])
        self.assertEqual(card["review_count"], 1)
        self.assertEqual(card["review_overall"], 4.0)
        self.assertGreaterEqual(card["enrollment_count"], 1)
        self.assertEqual(card["talk_recent_count"], 1)
        self.assertNotIn("absence", card)
        self.assertNotIn("attendance", card)
        self.assertNotIn("absence_count", card)

    def test_hidden_and_merged_excluded(self):
        self.offering.status = CourseOffering.Status.HIDDEN
        self.offering.save(update_fields=["status", "updated_at"])
        payload = build_course_discover_payload(self.user)
        self.assertNotIn(
            self.offering.pk, [c["id"] for c in payload["enrolled"]]
        )
        self.assertNotIn(
            self.offering.pk, [c["id"] for c in payload["active"]]
        )
        self.assertNotIn(
            self.offering.pk, [c["id"] for c in payload["popular"]]
        )

    def test_anonymous_has_no_enrolled(self):
        res = self.client.get("/api/v1/courses/discover/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["enrolled"], [])

    def test_single_card_for_multi_meeting(self):
        payload = build_course_discover_payload(self.user)
        popular = [c for c in payload["popular"] if c["id"] == self.offering.pk]
        self.assertEqual(len(popular), 1)
        self.assertEqual(len(popular[0]["meetings"]), 2)

    def test_talk_activity_ignores_hidden_deleted(self):
        payload = build_course_discover_payload(self.user)
        card = next(c for c in payload["active"] if c["id"] == self.offering.pk)
        self.assertEqual(card["talk_recent_count"], 1)
