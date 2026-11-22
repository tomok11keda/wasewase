"""Local E2E-style integration scenarios for official course enroll.

Uses fictional public OfficialClass rows only (no haibun/PDF data).
"""

from __future__ import annotations

import json

from django.contrib.auth import get_user_model
from django.test import Client, TransactionTestCase, override_settings

from app.course_chat_services import join_course_talk
from app.course_services import create_offering, enroll_user_in_offering
from app.models import (
    CourseEnrollment,
    CourseOffering,
    OfficialClass,
    OfficialMeeting,
    TimetableSlot,
)
from app.official_course_services import (
    build_provisional_identity,
    link_offering_to_official,
    meeting_fingerprint,
    set_canonical_offering,
)
from app.timetable_services import upsert_timetable_slot

User = get_user_model()


def _official(
    *,
    title: str,
    instructor: str,
    class_no: str,
    day: int,
    period: int,
    public: bool = True,
) -> OfficialClass:
    identity = build_provisional_identity(
        academic_year=2026,
        school="商学部",
        semester_code="spring",
        title=title,
        haibun_class_no=class_no,
        instructor=instructor,
        meeting_fingerprints=[
            meeting_fingerprint(
                day_of_week=day,
                period=period,
                period_kind=CourseOffering.PeriodKind.PERIOD,
                raw="e2e",
            )
        ],
    )
    official = OfficialClass.objects.create(
        academic_year=2026,
        school="商学部",
        section="E2E_FICTIONAL",
        title=title,
        title_normalized=title.casefold(),
        haibun_class_no=class_no,
        instructor=instructor,
        instructor_normalized=instructor.casefold(),
        semester_code="spring",
        semester_label="春学期",
        provisional_identity=identity,
        publication_status=(
            OfficialClass.PublicationStatus.PUBLIC
            if public
            else OfficialClass.PublicationStatus.RESEARCH_ONLY
        ),
        parse_flags="e2e_fictional_local_only",
        needs_human_review=False,
        is_cancelled=False,
    )
    OfficialMeeting.objects.create(
        official_class=official,
        day_of_week=day,
        period=period,
        period_kind=CourseOffering.PeriodKind.PERIOD,
        raw="e2e",
        fingerprint=f"p{period}-d{day}",
    )
    return official


@override_settings(
    WASE_OFFICIAL_CLASS_STUDENT_UI=True,
    WASE_OFFICIAL_CLASS_PILOT_SCHOOLS=["商学部"],
)
class OfficialCourseE2EIntegrationTests(TransactionTestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            email="e2e-int@example.com", password="pass12345"
        )
        self.client.force_login(self.user)

        self.ready = _official(
            title="架空・基礎データ分析",
            instructor="検証 一郎",
            class_no="1",
            day=0,
            period=2,
        )
        self.ready_offering, _ = create_offering(
            user=self.user,
            title=self.ready.title,
            instructor=self.ready.instructor,
            academic_year=2026,
            semester="spring",
            day_of_week=0,
            period=2,
            force_create=True,
        )
        set_canonical_offering(self.ready, self.ready_offering)

        self.pending = _official(
            title="架空・組織行動入門",
            instructor="検証 二郎",
            class_no="1",
            day=1,
            period=3,
        )

        self.conflict = _official(
            title="架空・マーケティング演習",
            instructor="検証 三郎",
            class_no="1",
            day=2,
            period=4,
        )
        a, _ = create_offering(
            user=self.user,
            title=self.conflict.title,
            instructor="検証 A",
            academic_year=2026,
            semester="spring",
            day_of_week=2,
            period=4,
            force_create=True,
        )
        b, _ = create_offering(
            user=self.user,
            title=self.conflict.title,
            instructor="検証 B",
            academic_year=2026,
            semester="spring",
            day_of_week=2,
            period=4,
            force_create=True,
        )
        link_offering_to_official(a, self.conflict)
        link_offering_to_official(b, self.conflict)

        self.slot_busy = _official(
            title="架空・財務会計概論",
            instructor="検証 五郎",
            class_no="1",
            day=4,
            period=5,
        )
        self.slot_busy_offering, _ = create_offering(
            user=self.user,
            title=self.slot_busy.title,
            instructor=self.slot_busy.instructor,
            academic_year=2026,
            semester="spring",
            day_of_week=4,
            period=5,
            force_create=True,
        )
        set_canonical_offering(self.slot_busy, self.slot_busy_offering)

        # Occupy Friday 5th with free-text slot for conflict case.
        upsert_timetable_slot(
            self.user,
            slot_key="p5-d4",
            name="既存自由入力",
            room="",
            credits="",
            memo="",
            offering=None,
        )

    def _post(self, url, payload=None):
        return self.client.post(
            url,
            data=json.dumps(payload or {}),
            content_type="application/json",
        )

    def test_search_lists_fictional_public_only(self):
        research = _official(
            title="架空・非公開科目",
            instructor="秘匿",
            class_no="9",
            day=0,
            period=1,
            public=False,
        )
        res = self.client.get("/api/v1/courses/official/", {"q": "架空"})
        self.assertEqual(res.status_code, 200)
        ids = {row["id"] for row in res.json()["results"]}
        self.assertIn(self.ready.pk, ids)
        self.assertIn(self.pending.pk, ids)
        self.assertNotIn(research.pk, ids)
        # research_only never appears even with exact title
        exact = self.client.get(
            "/api/v1/courses/official/", {"q": "架空・非公開科目"}
        )
        self.assertEqual(exact.json()["results"], [])

    def test_ready_enroll_and_course_talk(self):
        res = self._post(
            f"/api/v1/courses/official/{self.ready.pk}/enroll/",
            {"slot_key": "p2-d0"},
        )
        self.assertEqual(res.status_code, 200, res.content)
        data = res.json()
        self.assertEqual(data["offering"]["id"], self.ready_offering.pk)
        self.assertEqual(data["slot"]["offering_id"], self.ready_offering.pk)
        self.assertTrue(
            CourseEnrollment.objects.filter(
                user=self.user, offering=self.ready_offering
            ).exists()
        )
        # Course talk connection uses same offering
        room, membership, _created = join_course_talk(
            self.user, self.ready_offering
        )
        self.assertIsNotNone(room.pk)
        self.assertEqual(membership.user_id, self.user.pk)
        talk = self._post(f"/api/v1/courses/offerings/{self.ready_offering.pk}/talk/")
        self.assertEqual(talk.status_code, 200, talk.content)
        self.assertTrue(talk.json()["ok"])
        self.assertEqual(talk.json()["offering"]["id"], self.ready_offering.pk)

    def test_pending_canonical_friendly_message(self):
        res = self._post(f"/api/v1/courses/official/{self.pending.pk}/enroll/")
        self.assertEqual(res.status_code, 409)
        body = res.json()
        self.assertEqual(body["error"], "pending_canonical")
        self.assertIn("準備中", body.get("message", ""))
        self.assertEqual(CourseOffering.objects.filter(title=self.pending.title).count(), 0)

    def test_conflict_friendly_message(self):
        res = self._post(f"/api/v1/courses/official/{self.conflict.pk}/enroll/")
        self.assertEqual(res.status_code, 409)
        body = res.json()
        self.assertEqual(body["error"], "conflict")
        self.assertIn("複数", body.get("message", ""))

    def test_existing_enrollment_idempotent(self):
        first = self._post(
            f"/api/v1/courses/official/{self.ready.pk}/enroll/",
            {"slot_key": "p2-d0"},
        )
        second = self._post(
            f"/api/v1/courses/official/{self.ready.pk}/enroll/",
            {"slot_key": "p2-d0"},
        )
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(
            CourseEnrollment.objects.filter(
                user=self.user, offering=self.ready_offering
            ).count(),
            1,
        )

    def test_slot_conflict_with_free_text(self):
        res = self._post(
            f"/api/v1/courses/official/{self.slot_busy.pk}/enroll/",
            {"slot_key": "p5-d4"},
        )
        self.assertEqual(res.status_code, 409, res.content)
        body = res.json()
        self.assertEqual(body["error"], "slot_conflict")
        self.assertIn("すでに別の授業", body.get("message", ""))
        # Free-text slot preserved
        slot = TimetableSlot.objects.get(user=self.user, slot_key="p5-d4")
        self.assertEqual(slot.name, "既存自由入力")
        self.assertIsNone(slot.offering_id)

    def test_search_exposes_enrollable_flags(self):
        res = self.client.get("/api/v1/courses/official/", {"q": "架空・組織行動"})
        row = res.json()["results"][0]
        self.assertFalse(row["enrollable"])
        self.assertEqual(row["enrollment_status"], "pending_canonical")

        res2 = self.client.get("/api/v1/courses/official/", {"q": "架空・基礎データ"})
        row2 = res2.json()["results"][0]
        self.assertTrue(row2["enrollable"])
        self.assertEqual(row2["enrollment_status"], "ready")


@override_settings(WASE_OFFICIAL_CLASS_STUDENT_UI=False)
class OfficialCourseE2EFlagOffTests(TransactionTestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            email="e2e-flagoff@example.com", password="pass12345"
        )
        self.client.force_login(self.user)

    def test_flag_off_hides_official_keeps_community_and_create(self):
        meta = self.client.get("/api/v1/courses/meta/").json()
        self.assertFalse(meta["official_class_search_enabled"])
        self.assertEqual(
            self.client.get("/api/v1/courses/official/").status_code, 404
        )
        search = self.client.get("/api/v1/courses/search/", {"q": "x"})
        self.assertEqual(search.status_code, 200)
        create = self.client.post(
            "/api/v1/courses/offerings/",
            data=json.dumps(
                {
                    "title": "自由入力互換授業",
                    "instructor": "テスト",
                    "academic_year": 2026,
                    "semester": "spring",
                    "day_of_week": 0,
                    "period": 1,
                    "period_kind": "period",
                    "enroll": True,
                    "force_create": True,
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(create.status_code, 200, create.content)
        self.assertTrue(create.json()["ok"])
