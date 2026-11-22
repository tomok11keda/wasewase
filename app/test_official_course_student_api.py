"""Student OfficialClass search/enroll API tests."""

from __future__ import annotations

import csv
import json
import tempfile
from pathlib import Path

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, TransactionTestCase, override_settings

from app.course_services import create_offering, enroll_user_in_offering
from app.models import (
    CourseEnrollment,
    CourseOffering,
    CourseReview,
    OfficialClass,
    OfficialClassImportBatch,
    OfficialMeeting,
    TimetableSlot,
)
from app.official_course_services import (
    build_provisional_identity,
    import_official_classes_from_csv,
    meeting_fingerprint,
    set_canonical_offering,
)

User = get_user_model()


def _make_official(
    *,
    title: str = "公式ミクロ経済学",
    instructor: str = "公式 太郎",
    publication_status: str = OfficialClass.PublicationStatus.PUBLIC,
    school: str = "商学部",
    semester_code: str = "spring",
    needs_human_review: bool = False,
    is_cancelled: bool = False,
    day: int = 0,
    period: int = 2,
    class_no: str = "1",
) -> OfficialClass:
    identity = build_provisional_identity(
        academic_year=2026,
        school=school,
        semester_code=semester_code,
        title=title,
        haibun_class_no=class_no,
        instructor=instructor,
        meeting_fingerprints=[
            meeting_fingerprint(
                day_of_week=day,
                period=period,
                period_kind=CourseOffering.PeriodKind.PERIOD,
                raw=f"slot-{day}-{period}",
            )
        ],
    )
    official = OfficialClass.objects.create(
        academic_year=2026,
        school=school,
        title=title,
        title_normalized=title.casefold(),
        haibun_class_no=class_no,
        instructor=instructor,
        instructor_normalized=instructor.casefold(),
        semester_code=semester_code,
        semester_label="春学期" if semester_code == "spring" else semester_code,
        provisional_identity=identity,
        publication_status=publication_status,
        needs_human_review=needs_human_review,
        is_cancelled=is_cancelled,
    )
    if not is_cancelled:
        OfficialMeeting.objects.create(
            official_class=official,
            day_of_week=day,
            period=period,
            period_kind=CourseOffering.PeriodKind.PERIOD,
            raw="月2",
            fingerprint=f"p{period}-d{day}",
        )
    return official


@override_settings(
    WASE_OFFICIAL_CLASS_STUDENT_UI=True,
    WASE_OFFICIAL_CLASS_PILOT_SCHOOLS=["商学部"],
)
class OfficialStudentApiTests(TransactionTestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            email="official-student@ex.com", password="pass12345"
        )
        self.client.force_login(self.user)

    def _post(self, url, payload=None):
        return self.client.post(
            url,
            data=json.dumps(payload or {}),
            content_type="application/json",
        )

    def test_meta_exposes_feature_flag(self):
        res = self.client.get("/api/v1/courses/meta/")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data["official_class_search_enabled"])
        self.assertEqual(data["official_class_pilot_schools"], ["商学部"])

    def test_search_returns_only_public(self):
        public = _make_official(title="公開ミクロ", class_no="1")
        _make_official(
            title="研究用ミクロ",
            class_no="2",
            publication_status=OfficialClass.PublicationStatus.RESEARCH_ONLY,
        )
        _make_official(
            title="内部ミクロ",
            class_no="3",
            publication_status=OfficialClass.PublicationStatus.INTERNAL,
        )
        res = self.client.get("/api/v1/courses/official/", {"q": "ミクロ"})
        self.assertEqual(res.status_code, 200)
        ids = [row["id"] for row in res.json()["results"]]
        self.assertEqual(ids, [public.pk])

    def test_search_partial_match_and_filters(self):
        hit = _make_official(title="基礎統計学A", instructor="片山 東", day=1, period=3)
        _make_official(title="基礎数学", instructor="渡邊", day=0, period=2, class_no="9")
        res = self.client.get(
            "/api/v1/courses/official/",
            {
                "q": "統計",
                "day": 1,
                "period": 3,
                "semester": "spring",
                "year": 2026,
                "school": "商学部",
            },
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["total"], 1)
        self.assertEqual(data["results"][0]["id"], hit.pk)
        self.assertFalse(data["has_more"])

    def test_research_only_never_in_results_even_with_direct_query(self):
        research = _make_official(
            title="秘匿科目XYZ",
            publication_status=OfficialClass.PublicationStatus.RESEARCH_ONLY,
        )
        res = self.client.get("/api/v1/courses/official/", {"q": "秘匿科目XYZ"})
        self.assertEqual(res.json()["results"], [])
        enroll = self._post(f"/api/v1/courses/official/{research.pk}/enroll/")
        self.assertEqual(enroll.status_code, 404)

    def test_enroll_uses_canonical_offering(self):
        official = _make_official()
        offering, _ = create_offering(
            user=self.user,
            title=official.title,
            instructor=official.instructor,
            academic_year=2026,
            semester="spring",
            day_of_week=0,
            period=2,
            force_create=True,
        )
        set_canonical_offering(official, offering)
        res = self._post(
            f"/api/v1/courses/official/{official.pk}/enroll/",
            {"slot_key": "p2-d0"},
        )
        self.assertEqual(res.status_code, 200, res.content)
        data = res.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["offering"]["id"], offering.pk)
        self.assertEqual(
            CourseEnrollment.objects.filter(
                user=self.user, offering=offering
            ).count(),
            1,
        )

    def test_pending_canonical_returns_409(self):
        official = _make_official()
        res = self._post(f"/api/v1/courses/official/{official.pk}/enroll/")
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.json()["error"], "pending_canonical")
        self.assertEqual(CourseEnrollment.objects.count(), 0)
        self.assertEqual(CourseOffering.objects.count(), 0)

    def test_conflict_multiple_links_returns_409(self):
        official = _make_official()
        a, _ = create_offering(
            user=self.user,
            title=official.title,
            instructor="A教員",
            academic_year=2026,
            semester="spring",
            day_of_week=0,
            period=2,
            force_create=True,
        )
        b, _ = create_offering(
            user=self.user,
            title=official.title,
            instructor="B教員",
            academic_year=2026,
            semester="spring",
            day_of_week=0,
            period=2,
            force_create=True,
        )
        from app.official_course_services import link_offering_to_official

        link_offering_to_official(a, official)
        link_offering_to_official(b, official)
        res = self._post(f"/api/v1/courses/official/{official.pk}/enroll/")
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.json()["error"], "conflict")

    def test_duplicate_enroll_is_idempotent(self):
        official = _make_official()
        offering, _ = create_offering(
            user=self.user,
            title=official.title,
            instructor=official.instructor,
            academic_year=2026,
            semester="spring",
            day_of_week=0,
            period=2,
            force_create=True,
        )
        set_canonical_offering(official, offering)
        first = self._post(f"/api/v1/courses/official/{official.pk}/enroll/")
        second = self._post(f"/api/v1/courses/official/{official.pk}/enroll/")
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(
            CourseEnrollment.objects.filter(
                user=self.user, offering=offering
            ).count(),
            1,
        )

    def test_provisional_identity_changes_when_meeting_changes(self):
        a = build_provisional_identity(
            academic_year=2026,
            school="商学部",
            semester_code="spring",
            title="基礎数学",
            haibun_class_no="1",
            instructor="渡邊",
            meeting_fingerprints=["p2-d0"],
        )
        b = build_provisional_identity(
            academic_year=2026,
            school="商学部",
            semester_code="spring",
            title="基礎数学",
            haibun_class_no="1",
            instructor="渡邊",
            meeting_fingerprints=["p3-d0"],
        )
        self.assertNotEqual(a, b)

    def test_dry_run_history_does_not_create_official_or_offering(self):
        fields = [
            "pilot_row_id",
            "academic_year",
            "school",
            "section",
            "title",
            "haibun_class_no",
            "instructor",
            "semester_code",
            "semester_label",
            "credits",
            "meeting_1_raw",
            "meeting_1_day",
            "meeting_1_period",
            "meeting_1_period_kind",
            "meeting_2_raw",
            "meeting_2_day",
            "meeting_2_period",
            "meeting_2_period_kind",
            "modality_raw",
            "is_cancelled",
            "subject_key",
            "syllabus_class_code",
            "course_code",
            "source_url",
            "source_listing_page",
            "source_extract_line",
            "source_raw_line",
            "parse_flags",
            "needs_human_review",
            "extraction_ok",
        ]
        row = {k: "" for k in fields}
        row.update(
            {
                "pilot_row_id": "x",
                "academic_year": "2026",
                "school": "商学部",
                "title": "ドライラン科目",
                "haibun_class_no": "1",
                "instructor": "テスト",
                "semester_code": "spring",
                "meeting_1_raw": "火3",
                "meeting_1_day": "1",
                "meeting_1_period": "3",
                "meeting_1_period_kind": "period",
                "is_cancelled": "False",
                "needs_human_review": "False",
                "extraction_ok": "True",
                "source_extract_line": "1",
            }
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "t.csv"
            with path.open("w", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=fields)
                w.writeheader()
                w.writerow(row)
            report = import_official_classes_from_csv(path, dry_run=True)
        self.assertEqual(OfficialClass.objects.count(), 0)
        self.assertEqual(CourseOffering.objects.count(), 0)
        self.assertTrue(
            OfficialClassImportBatch.objects.filter(pk=report.batch_id).exists()
        )


@override_settings(WASE_OFFICIAL_CLASS_STUDENT_UI=False)
class OfficialStudentApiFlagOffTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            email="flag-off@ex.com", password="pass12345"
        )
        self.client.force_login(self.user)

    def test_search_and_enroll_disabled(self):
        res = self.client.get("/api/v1/courses/official/")
        self.assertEqual(res.status_code, 404)
        self.assertEqual(res.json()["error"], "feature_disabled")
        meta = self.client.get("/api/v1/courses/meta/").json()
        self.assertFalse(meta["official_class_search_enabled"])

    def test_community_search_still_works(self):
        res = self.client.get("/api/v1/courses/search/", {"q": "test"})
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()["ok"])


@override_settings(
    WASE_OFFICIAL_CLASS_STUDENT_UI=True,
    WASE_OFFICIAL_CLASS_PILOT_SCHOOLS=["商学部"],
)
class OfficialEnrollIsolationTests(TransactionTestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            email="iso@ex.com", password="pass12345"
        )
        self.client.force_login(self.user)
        self.offering, _ = create_offering(
            user=self.user,
            title="既存自由入力授業",
            instructor="山田",
            academic_year=2026,
            semester="spring",
            day_of_week=4,
            period=5,
            force_create=True,
        )
        enroll_user_in_offering(self.user, self.offering)
        CourseReview.objects.create(
            user=self.user,
            offering=self.offering,
            overall_rating=5,
            difficulty_rating=3,
            workload_rating=3,
            attendance_rating=2,
            exam_rating=3,
            comment="既存レビュー",
        )
        self.offering.refresh_from_db()
        self.snap = {
            "offering_id": self.offering.pk,
            "chat_room_id": self.offering.chat_room_id,
            "title": self.offering.title,
            "enrollments": list(
                CourseEnrollment.objects.filter(user=self.user).values_list(
                    "id", "offering_id"
                )
            ),
            "slots": list(
                TimetableSlot.objects.filter(user=self.user).values_list(
                    "id", "offering_id", "slot_key"
                )
            ),
            "reviews": list(
                CourseReview.objects.filter(user=self.user).values_list(
                    "id", "comment"
                )
            ),
        }

    def test_official_enroll_does_not_break_existing_data(self):
        official = _make_official(title="別公式授業", day=0, period=1)
        canonical, _ = create_offering(
            user=self.user,
            title=official.title,
            instructor=official.instructor,
            academic_year=2026,
            semester="spring",
            day_of_week=0,
            period=1,
            force_create=True,
        )
        set_canonical_offering(official, canonical)
        res = self.client.post(
            f"/api/v1/courses/official/{official.pk}/enroll/",
            data=json.dumps({"slot_key": "p1-d0"}),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 200, res.content)

        self.offering.refresh_from_db()
        self.assertEqual(self.offering.pk, self.snap["offering_id"])
        self.assertEqual(self.offering.chat_room_id, self.snap["chat_room_id"])
        self.assertEqual(self.offering.title, self.snap["title"])
        self.assertEqual(
            list(
                CourseEnrollment.objects.filter(
                    user=self.user, offering=self.offering
                ).values_list("id", "offering_id")
            ),
            [row for row in self.snap["enrollments"] if row[1] == self.offering.pk],
        )
        self.assertEqual(
            list(
                CourseReview.objects.filter(user=self.user, offering=self.offering)
                .values_list("id", "comment")
            ),
            self.snap["reviews"],
        )
        # Existing free-text/offering slot remains.
        self.assertTrue(
            TimetableSlot.objects.filter(
                user=self.user, offering=self.offering
            ).exists()
        )


class OfficialUiSourceTests(TestCase):
    def test_course_add_sheet_has_official_tab_and_flag_gate(self):
        path = (
            Path(__file__).resolve().parents[1]
            / "frontend"
            / "src"
            / "features"
            / "courses"
            / "CourseAddSheet.tsx"
        )
        text = path.read_text(encoding="utf-8")
        self.assertIn("公式から選ぶ", text)
        self.assertIn("official_class_search_enabled", text)
        self.assertIn("enrollOfficialClass", text)
        self.assertIn("自由入力する", text)
