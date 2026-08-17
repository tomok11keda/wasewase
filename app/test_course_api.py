"""Course master / enrollment / review API tests."""
from django.contrib.auth import get_user_model
from django.test import Client, TestCase

from app.course_services import (
    create_offering,
    enroll_user_in_offering,
    merge_offerings,
    normalize_course_text,
    search_offerings,
)
from app.models import (
    CourseEnrollment,
    CourseOffering,
    CourseReview,
    TimetableSlot,
)

User = get_user_model()


class CourseNormalizeTests(TestCase):
    def test_normalize_fullwidth_and_spaces(self):
        self.assertEqual(
            normalize_course_text("  マーケティング　論  "),
            normalize_course_text("マーケティング 論"),
        )
        self.assertEqual(
            normalize_course_text("Yamada Taro"),
            normalize_course_text("yamada  taro"),
        )


class CourseApiTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            email="course-a@ex.com", password="pass12345"
        )
        self.other = User.objects.create_user(
            email="course-b@ex.com", password="pass12345"
        )
        self.client.force_login(self.user)

    def _create(self, **overrides):
        payload = {
            "title": "マーケティング論",
            "instructor": "山田 太郎",
            "academic_year": 2026,
            "semester": "spring",
            "day_of_week": 0,
            "period": 2,
            "period_kind": "period",
            "room": "11-501",
            "credits": "2",
            "enroll": True,
            "force_create": True,
        }
        payload.update(overrides)
        return self.client.post(
            "/api/v1/courses/offerings/",
            data=payload,
            content_type="application/json",
        )

    def test_create_enroll_and_slot_sync(self):
        res = self._create()
        self.assertEqual(res.status_code, 200, res.content)
        data = res.json()
        self.assertTrue(data["ok"])
        offering_id = data["offering"]["id"]
        self.assertEqual(data["slot"]["slot_key"], "p2-d0")
        self.assertEqual(data["slot"]["offering_id"], offering_id)
        self.assertEqual(
            TimetableSlot.objects.filter(
                user=self.user, offering_id=offering_id
            ).count(),
            1,
        )
        self.assertEqual(
            CourseEnrollment.objects.filter(
                user=self.user,
                offering_id=offering_id,
                role=CourseEnrollment.Role.CURRENT,
            ).count(),
            1,
        )

    def test_duplicate_enrollment_unique(self):
        res = self._create()
        offering_id = res.json()["offering"]["id"]
        again = self.client.post(
            f"/api/v1/courses/offerings/{offering_id}/enroll/",
            data={},
            content_type="application/json",
        )
        self.assertEqual(again.status_code, 200)
        self.assertEqual(
            CourseEnrollment.objects.filter(
                user=self.user, offering_id=offering_id
            ).count(),
            1,
        )

    def test_search_ranks_same_slot(self):
        create_offering(
            user=self.user,
            title="ミクロ経済学",
            instructor="佐藤",
            academic_year=2026,
            semester="spring",
            day_of_week=0,
            period=2,
            force_create=True,
        )
        create_offering(
            user=self.user,
            title="ミクロ経済学特論",
            instructor="鈴木",
            academic_year=2026,
            semester="spring",
            day_of_week=2,
            period=3,
            force_create=True,
        )
        results = search_offerings(q="ミクロ", day_of_week=0, period=2, limit=10)
        self.assertGreaterEqual(len(results), 1)
        self.assertEqual(results[0].day_of_week, 0)
        self.assertEqual(results[0].period, 2)

    def test_duplicate_candidates_block_create(self):
        first = self._create(force_create=True)
        self.assertEqual(first.status_code, 200)
        second = self._create(force_create=False, enroll=False)
        self.assertEqual(second.status_code, 409)
        self.assertEqual(second.json()["error"], "duplicate_candidates")
        self.assertTrue(second.json()["duplicates"])

    def test_unenroll_marks_past_and_clears_slot(self):
        res = self._create()
        offering_id = res.json()["offering"]["id"]
        out = self.client.post(
            f"/api/v1/courses/offerings/{offering_id}/unenroll/",
            data={},
            content_type="application/json",
        )
        self.assertEqual(out.status_code, 200)
        self.assertFalse(
            TimetableSlot.objects.filter(
                user=self.user, offering_id=offering_id
            ).exists()
        )
        enrollment = CourseEnrollment.objects.get(
            user=self.user, offering_id=offering_id
        )
        self.assertEqual(enrollment.role, CourseEnrollment.Role.PAST)

    def test_free_text_slot_still_works(self):
        res = self.client.post(
            "/api/timetable/slot/",
            data={
                "slot_key": "p1-d1",
                "name": "自由記述ゼミ",
                "room": "3-201",
                "credits": "2",
                "memo": "memo",
            },
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 200)
        entry = res.json()["entry"]
        self.assertEqual(entry["name"], "自由記述ゼミ")
        self.assertIsNone(entry.get("offering_id"))
        slot = TimetableSlot.objects.get(user=self.user, slot_key="p1-d1")
        self.assertIsNone(slot.offering_id)

    def test_enrollment_count_and_detail(self):
        res = self._create()
        offering_id = res.json()["offering"]["id"]
        self.client.force_login(self.other)
        self.client.post(
            f"/api/v1/courses/offerings/{offering_id}/enroll/",
            data={},
            content_type="application/json",
        )
        detail = self.client.get(f"/api/v1/courses/offerings/{offering_id}/")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()["offering"]["enrollment_count"], 2)

    def test_merge_moves_enrollment_and_review(self):
        a, _ = create_offering(
            user=self.user,
            title="統計学A",
            instructor="田中",
            academic_year=2026,
            semester="spring",
            day_of_week=1,
            period=1,
            force_create=True,
        )
        # Same conceptual class entered with a soft difference that still
        # needs admin merge (different instructor spelling → separate rows)
        b, dups = create_offering(
            user=self.user,
            title="統計学A",
            instructor="田中 一郎",
            academic_year=2026,
            semester="spring",
            day_of_week=1,
            period=1,
            force_create=True,
        )
        self.assertFalse(dups)
        self.assertNotEqual(a.pk, b.pk)
        enroll_user_in_offering(self.user, a)
        CourseReview.objects.create(
            user=self.user,
            offering=a,
            overall_rating=4,
            difficulty_rating=3,
            workload_rating=3,
            attendance_rating=2,
            exam_rating=3,
            comment="good",
        )
        merge_offerings(a, b)
        a.refresh_from_db()
        self.assertEqual(a.status, CourseOffering.Status.MERGED)
        self.assertEqual(a.merged_into_id, b.pk)
        self.assertTrue(
            CourseEnrollment.objects.filter(user=self.user, offering=b).exists()
        )
        self.assertTrue(
            CourseReview.objects.filter(user=self.user, offering=b).exists()
        )
        self.assertFalse(
            CourseEnrollment.objects.filter(user=self.user, offering=a).exists()
        )

    def test_review_create_and_unique(self):
        res = self._create()
        offering_id = res.json()["offering"]["id"]
        payload = {
            "overall_rating": 5,
            "difficulty_rating": 2,
            "workload_rating": 3,
            "attendance_rating": 4,
            "exam_rating": 3,
            "comment": "わかりやすい",
        }
        r1 = self.client.post(
            f"/api/v1/courses/offerings/{offering_id}/reviews/",
            data=payload,
            content_type="application/json",
        )
        self.assertEqual(r1.status_code, 200, r1.content)
        r2 = self.client.post(
            f"/api/v1/courses/offerings/{offering_id}/reviews/",
            data={**payload, "overall_rating": 4},
            content_type="application/json",
        )
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(
            CourseReview.objects.filter(
                user=self.user, offering_id=offering_id
            ).count(),
            1,
        )
        self.assertEqual(
            CourseReview.objects.get(
                user=self.user, offering_id=offering_id
            ).overall_rating,
            4,
        )

    def test_review_requires_enrollment(self):
        res = self._create(enroll=False, force_create=True)
        offering_id = res.json()["offering"]["id"]
        bad = self.client.post(
            f"/api/v1/courses/offerings/{offering_id}/reviews/",
            data={
                "overall_rating": 5,
                "difficulty_rating": 2,
                "workload_rating": 3,
                "attendance_rating": 4,
                "exam_rating": 3,
                "comment": "x",
            },
            content_type="application/json",
        )
        self.assertEqual(bad.status_code, 403)
        self.assertEqual(bad.json()["error"], "enrollment_required")

    def test_enroll_rejects_slot_mismatch(self):
        res = self._create(enroll=False, force_create=True)
        offering_id = res.json()["offering"]["id"]
        bad = self.client.post(
            f"/api/v1/courses/offerings/{offering_id}/enroll/",
            data={"slot_key": "p5-d5"},
            content_type="application/json",
        )
        self.assertEqual(bad.status_code, 400)
        self.assertEqual(bad.json()["error"], "slot_mismatch")

    def test_create_aligns_schedule_to_slot_key(self):
        """FE meta race: body day/period may still be defaults while slot_key is set.

        Production cold-start made this common; create must prefer slot_key.
        """
        res = self._create(
            day_of_week=0,
            period=1,
            slot_key="p5-d4",
            force_create=True,
            title="生産専用レース再現",
            instructor="検証 太郎",
        )
        self.assertEqual(res.status_code, 200, res.content)
        data = res.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["offering"]["day_of_week"], 4)
        self.assertEqual(data["offering"]["period"], 5)
        self.assertEqual(data["slot"]["slot_key"], "p5-d4")
        self.assertEqual(
            TimetableSlot.objects.filter(
                user=self.user, slot_key="p5-d4", offering_id=data["offering"]["id"]
            ).count(),
            1,
        )

    def test_invalid_academic_year_rejected(self):
        res = self._create(academic_year=1999, force_create=True, enroll=False)
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["error"], "invalid_academic_year")

    def test_hidden_offering_not_visible(self):
        res = self._create(force_create=True)
        offering_id = res.json()["offering"]["id"]
        CourseOffering.objects.filter(pk=offering_id).update(
            status=CourseOffering.Status.HIDDEN
        )
        detail = self.client.get(f"/api/v1/courses/offerings/{offering_id}/")
        self.assertEqual(detail.status_code, 404)

    def test_unique_active_identity_blocks_race(self):
        a, _ = create_offering(
            user=self.user,
            title="線形代数",
            instructor="高橋",
            academic_year=2026,
            semester="spring",
            day_of_week=3,
            period=2,
            force_create=True,
        )
        b, dups = create_offering(
            user=self.user,
            title="線形代数",
            instructor="高橋",
            academic_year=2026,
            semester="spring",
            day_of_week=3,
            period=2,
            force_create=True,
        )
        self.assertEqual(a.pk, b.pk)
        self.assertTrue(dups)
        self.assertEqual(
            CourseOffering.objects.filter(
                title_normalized=a.title_normalized,
                status=CourseOffering.Status.ACTIVE,
            ).count(),
            1,
        )

    def test_past_enrollment_can_review(self):
        res = self._create(force_create=True)
        offering_id = res.json()["offering"]["id"]
        self.client.post(
            f"/api/v1/courses/offerings/{offering_id}/unenroll/",
            data={},
            content_type="application/json",
        )
        ok = self.client.post(
            f"/api/v1/courses/offerings/{offering_id}/reviews/",
            data={
                "overall_rating": 4,
                "difficulty_rating": 3,
                "workload_rating": 3,
                "attendance_rating": 3,
                "exam_rating": 3,
                "comment": "過去履修レビュー",
            },
            content_type="application/json",
        )
        self.assertEqual(ok.status_code, 200, ok.content)

    def test_meta_endpoint(self):
        res = self.client.get("/api/v1/courses/meta/")
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()["ok"])
        self.assertIn("academic_year", res.json())
        self.assertIn("semesters", res.json())
        self.assertIn("academic_year_min", res.json())
        self.assertIn("academic_year_max", res.json())
