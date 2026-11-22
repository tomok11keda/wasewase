"""Local tests for Option B OfficialClass: identity, CSV dry-run, linking."""

from __future__ import annotations

import csv
import tempfile
from pathlib import Path

from django.contrib.auth import get_user_model
from django.test import TestCase, TransactionTestCase

from app.course_services import create_offering, enroll_user_in_offering
from app.models import (
    CourseEnrollment,
    CourseOffering,
    CourseReview,
    OfficialClass,
    OfficialClassImportBatch,
    OfficialMeeting,
    OfferingOfficialLink,
    TimetableSlot,
)
from app.official_course_services import (
    CanonicalOfferingRequired,
    MultipleOfferingsForOfficial,
    build_provisional_identity,
    classify_pilot_csv_row,
    create_offering_from_official,
    dry_run_import_official_classes,
    enrollment_readiness,
    import_official_classes_from_csv,
    link_offering_to_official,
    meeting_fingerprint,
    official_link_conflict_summary,
    resolve_enrollment_offering,
    set_canonical_offering,
)

User = get_user_model()

CSV_FIELDS = [
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


def _row(**overrides) -> dict[str, str]:
    base = {k: "" for k in CSV_FIELDS}
    base.update(
        {
            "pilot_row_id": "test001",
            "academic_year": "2026",
            "school": "商学部",
            "section": "専門基礎科目(必修)",
            "title": "基礎数学",
            "haibun_class_no": "1",
            "instructor": "渡邊 展也",
            "semester_code": "spring",
            "semester_label": "春学期",
            "meeting_1_raw": "火3",
            "meeting_1_day": "1",
            "meeting_1_period": "3",
            "meeting_1_period_kind": "period",
            "modality_raw": "対面",
            "is_cancelled": "False",
            "needs_human_review": "False",
            "extraction_ok": "True",
            "source_extract_line": "10",
        }
    )
    base.update(overrides)
    return base


def _write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


class ProvisionalIdentityTests(TestCase):
    def test_stable_and_prefixed(self):
        a = build_provisional_identity(
            academic_year=2026,
            school="商学部",
            semester_code="spring",
            title="基礎数学",
            haibun_class_no="1",
            instructor="渡邊 展也",
            meeting_fingerprints=["p3-d1"],
        )
        b = build_provisional_identity(
            academic_year=2026,
            school="商学部",
            semester_code="spring",
            title="基礎数学",
            haibun_class_no="1",
            instructor="渡邊　展也",  # fullwidth space → NFKC
            meeting_fingerprints=["p3-d1"],
        )
        self.assertTrue(a.startswith("haibun:v1:"))
        self.assertEqual(a, b)

    def test_does_not_invent_subject_key_fields(self):
        """Identity builder never takes or emits syllabus keys."""
        identity = build_provisional_identity(
            academic_year=2026,
            school="商学部",
            semester_code="spring",
            title="基礎数学",
            haibun_class_no="1",
            instructor="渡邊 展也",
            meeting_fingerprints=["p3-d1"],
        )
        self.assertNotIn("subject", identity)
        self.assertEqual(len(identity), len("haibun:v1:") + 20)

    def test_meeting_fingerprint_od(self):
        self.assertEqual(
            meeting_fingerprint(
                day_of_week=None,
                period=None,
                period_kind=CourseOffering.PeriodKind.OD,
                raw="無",
            ),
            "od",
        )


class ClassifyRowTests(TestCase):
    def test_rejects_slot_as_title(self):
        reasons = classify_pilot_csv_row(_row(title="火4"))
        self.assertIn("garbage_slot_as_title", reasons)

    def test_rejects_fragment_titles(self):
        self.assertIn(
            "garbage_title_fragment",
            classify_pilot_csv_row(_row(title="Researchers")),
        )

    def test_rejects_missing_required_and_bad_semester(self):
        reasons = classify_pilot_csv_row(
            _row(title="", school="", semester_code="winter", academic_year="")
        )
        self.assertIn("missing_title", reasons)
        self.assertIn("missing_school", reasons)
        self.assertIn("missing_academic_year", reasons)
        self.assertIn("invalid_semester_code", reasons)

    def test_rejects_invalid_day_period(self):
        reasons = classify_pilot_csv_row(
            _row(
                meeting_1_day="9",
                meeting_1_period="3",
                meeting_1_period_kind="period",
            )
        )
        self.assertIn("invalid_day_of_week_1", reasons)

    def test_rejects_missing_meetings_for_active(self):
        reasons = classify_pilot_csv_row(
            _row(
                meeting_1_raw="",
                meeting_1_day="",
                meeting_1_period="",
                meeting_1_period_kind="",
                is_cancelled="False",
            )
        )
        self.assertIn("missing_meetings", reasons)

    def test_allows_cancelled_without_meetings(self):
        reasons = classify_pilot_csv_row(
            _row(
                meeting_1_raw="",
                meeting_1_day="",
                meeting_1_period="",
                meeting_1_period_kind="",
                is_cancelled="True",
            )
        )
        self.assertEqual(reasons, [])


class DryRunImportTests(TestCase):
    def test_dry_run_does_not_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "pilot.csv"
            _write_csv(path, [_row(), _row(pilot_row_id="dup", title="火4")])
            report = dry_run_import_official_classes(path)
            self.assertEqual(report.would_create, 1)
            self.assertEqual(report.would_reject, 1)
            self.assertEqual(OfficialClass.objects.count(), 0)

    def test_import_creates_class_and_meetings(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "pilot.csv"
            _write_csv(
                path,
                [
                    _row(
                        meeting_2_raw="金3",
                        meeting_2_day="4",
                        meeting_2_period="3",
                        meeting_2_period_kind="period",
                    )
                ],
            )
            report = import_official_classes_from_csv(path, dry_run=False)
            self.assertEqual(report.would_create, 1)
            self.assertEqual(OfficialClass.objects.count(), 1)
            official = OfficialClass.objects.get()
            self.assertEqual(official.publication_status, "research_only")
            self.assertEqual(official.subject_key, "")
            self.assertEqual(official.syllabus_class_code, "")
            self.assertTrue(official.provisional_identity.startswith("haibun:v1:"))
            self.assertEqual(OfficialMeeting.objects.filter(official_class=official).count(), 2)

    def test_duplicate_identity_in_file_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "pilot.csv"
            # Same identity fields → same provisional key
            _write_csv(path, [_row(pilot_row_id="a"), _row(pilot_row_id="b")])
            report = dry_run_import_official_classes(path)
            self.assertEqual(report.would_create, 1)
            self.assertEqual(report.would_skip_duplicate, 1)

    def test_second_import_is_unchanged_when_identical(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "pilot.csv"
            _write_csv(path, [_row()])
            import_official_classes_from_csv(path, dry_run=False, record_history=False)
            report = dry_run_import_official_classes(path)
            self.assertEqual(report.would_unchanged, 1)
            self.assertEqual(report.would_create, 0)
            self.assertEqual(OfficialClass.objects.count(), 1)

    def test_reimport_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "pilot.csv"
            _write_csv(path, [_row()])
            import_official_classes_from_csv(path, dry_run=False, record_history=False)
            import_official_classes_from_csv(path, dry_run=False, record_history=False)
            self.assertEqual(OfficialClass.objects.count(), 1)
            self.assertEqual(OfficialMeeting.objects.count(), 1)

    def test_dry_run_records_history_without_official_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "pilot.csv"
            _write_csv(path, [_row()])
            report = import_official_classes_from_csv(path, dry_run=True)
            self.assertEqual(OfficialClass.objects.count(), 0)
            self.assertIsNotNone(report.batch_id)
            batch = OfficialClassImportBatch.objects.get(pk=report.batch_id)
            self.assertTrue(batch.dry_run)
            self.assertEqual(batch.status, OfficialClassImportBatch.Status.DRY_RUN)
            self.assertEqual(batch.rows.count(), 1)

    def test_commit_refuses_public_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "pilot.csv"
            _write_csv(path, [_row()])
            with self.assertRaises(ValueError):
                import_official_classes_from_csv(
                    path,
                    dry_run=False,
                    publication_status=OfficialClass.PublicationStatus.PUBLIC,
                    record_history=False,
                )


class OfficialLinkResolveTests(TransactionTestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="official-pilot@ex.com", password="pass12345"
        )
        self.official = OfficialClass.objects.create(
            academic_year=2026,
            school="商学部",
            title="ミクロ経済学",
            title_normalized="ミクロ経済学",
            haibun_class_no="1",
            instructor="佐藤",
            instructor_normalized="佐藤",
            semester_code="spring",
            semester_label="春学期",
            provisional_identity="haibun:v1:testmicro001",
            publication_status=OfficialClass.PublicationStatus.RESEARCH_ONLY,
        )
        OfficialMeeting.objects.create(
            official_class=self.official,
            day_of_week=0,
            period=2,
            period_kind=CourseOffering.PeriodKind.PERIOD,
            raw="月2",
            fingerprint="p2-d0",
        )

    def test_create_from_official_sets_canonical_and_link(self):
        offering = create_offering_from_official(self.official, actor=self.user)
        self.official.refresh_from_db()
        self.assertEqual(self.official.canonical_offering_id, offering.pk)
        self.assertEqual(offering.source, CourseOffering.Source.OFFICIAL)
        link = OfferingOfficialLink.objects.get(offering=offering)
        self.assertEqual(link.official_class_id, self.official.pk)
        self.assertEqual(
            link.match_method,
            OfferingOfficialLink.MatchMethod.CREATED_FROM_OFFICIAL,
        )

    def test_resolve_prefers_canonical(self):
        offering = create_offering_from_official(self.official, actor=self.user)
        resolved = resolve_enrollment_offering(self.official)
        self.assertEqual(resolved.pk, offering.pk)

    def _user_offering(self, *, instructor: str) -> CourseOffering:
        # Distinct instructor strings → distinct active offerings (uniq constraint),
        # both later linked manually to the same OfficialClass.
        offering, _ = create_offering(
            user=self.user,
            title="ミクロ経済学",
            instructor=instructor,
            academic_year=2026,
            semester="spring",
            day_of_week=0,
            period=2,
            force_create=True,
        )
        return offering

    def test_pending_canonical_without_explicit_set(self):
        readiness = enrollment_readiness(self.official)
        self.assertEqual(readiness["status"], "pending_canonical")
        self.assertFalse(readiness["ready"])
        with self.assertRaises(CanonicalOfferingRequired):
            resolve_enrollment_offering(self.official, create_if_missing=False)

    def test_multiple_links_without_canonical_raises(self):
        a = self._user_offering(instructor="佐藤")
        b = self._user_offering(instructor="佐藤 一郎")
        link_offering_to_official(a, self.official)
        link_offering_to_official(b, self.official)
        summary = official_link_conflict_summary(self.official)
        self.assertEqual(summary["active_linked_count"], 2)
        self.assertTrue(summary["needs_manual_canonical"])
        self.assertFalse(summary["auto_merge_allowed"])
        self.assertEqual(enrollment_readiness(self.official)["status"], "conflict")
        with self.assertRaises(MultipleOfferingsForOfficial):
            resolve_enrollment_offering(self.official, create_if_missing=False)

    def test_set_canonical_is_explicit_and_does_not_create_extra(self):
        offering = self._user_offering(instructor="佐藤")
        before = CourseOffering.objects.count()
        set_canonical_offering(self.official, offering)
        self.official.refresh_from_db()
        self.assertEqual(self.official.canonical_offering_id, offering.pk)
        self.assertEqual(CourseOffering.objects.count(), before)
        self.assertTrue(
            OfferingOfficialLink.objects.filter(
                offering=offering, official_class=self.official
            ).exists()
        )

    def test_setting_canonical_does_not_merge_offerings(self):
        a = self._user_offering(instructor="佐藤")
        b = self._user_offering(instructor="佐藤 一郎")
        link_offering_to_official(a, self.official)
        link_offering_to_official(b, self.official, set_as_canonical=True)
        self.official.refresh_from_db()
        self.assertEqual(self.official.canonical_offering_id, b.pk)
        self.assertEqual(
            CourseOffering.objects.filter(
                status=CourseOffering.Status.ACTIVE, title_normalized="ミクロ経済学"
            ).count(),
            2,
        )
        enroll_user_in_offering(self.user, resolve_enrollment_offering(self.official))
        self.assertEqual(
            CourseEnrollment.objects.filter(user=self.user, offering=b).count(),
            1,
        )
        # Offering A still exists independently (no auto-merge).
        self.assertTrue(
            CourseOffering.objects.filter(
                pk=a.pk, status=CourseOffering.Status.ACTIVE
            ).exists()
        )


class PilotCsvSmokeTests(TestCase):
    """Optional smoke against the research CSV when present."""

    def test_research_csv_dry_run_if_present(self):
        path = (
            Path(__file__).resolve().parents[1]
            / "research"
            / "course_master_pilot"
            / "derived"
            / "soc_2026_commerce_pilot_classes.csv"
        )
        if not path.exists():
            self.skipTest("pilot csv not present")
        report = dry_run_import_official_classes(path)
        self.assertGreaterEqual(report.total_rows, 50)
        self.assertLessEqual(report.total_rows, 150)
        self.assertEqual(report.would_reject, 0)
        self.assertEqual(OfficialClass.objects.count(), 0)
        self.assertEqual(
            report.would_create
            + report.would_update
            + report.would_unchanged
            + report.would_skip_duplicate,
            report.total_rows,
        )


class ExistingUserDataIsolationTests(TransactionTestCase):
    """CSV import / official linking must not mutate existing user course data."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="existing-course@ex.com", password="pass12345"
        )
        self.offering, _ = create_offering(
            user=self.user,
            title="既存マーケティング論",
            instructor="山田",
            academic_year=2026,
            semester="spring",
            day_of_week=1,
            period=3,
            force_create=True,
        )
        enroll_user_in_offering(self.user, self.offering)
        CourseReview.objects.create(
            user=self.user,
            offering=self.offering,
            overall_rating=4,
            difficulty_rating=3,
            workload_rating=3,
            attendance_rating=2,
            exam_rating=3,
            comment="既存口コミ",
        )
        self.offering.refresh_from_db()
        self.snapshot = {
            "offering_id": self.offering.pk,
            "offering_status": self.offering.status,
            "offering_title": self.offering.title,
            "chat_room_id": self.offering.chat_room_id,
            "enrollment_ids": list(
                CourseEnrollment.objects.filter(user=self.user).values_list(
                    "id", "offering_id", "role"
                )
            ),
            "slot_ids": list(
                TimetableSlot.objects.filter(user=self.user).values_list(
                    "id", "offering_id", "slot_key"
                )
            ),
            "review_ids": list(
                CourseReview.objects.filter(user=self.user).values_list(
                    "id", "offering_id", "comment"
                )
            ),
            "offering_count": CourseOffering.objects.count(),
        }

    def test_import_does_not_touch_existing_timetable_talk_or_reviews(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "pilot.csv"
            _write_csv(path, [_row(title="公式だけ数学")])
            # dry-run then commit
            import_official_classes_from_csv(path, dry_run=True)
            import_official_classes_from_csv(path, dry_run=False)
            # re-import idempotent
            import_official_classes_from_csv(path, dry_run=False)

        self.offering.refresh_from_db()
        self.assertEqual(self.offering.pk, self.snapshot["offering_id"])
        self.assertEqual(self.offering.status, self.snapshot["offering_status"])
        self.assertEqual(self.offering.title, self.snapshot["offering_title"])
        self.assertEqual(self.offering.chat_room_id, self.snapshot["chat_room_id"])
        self.assertEqual(
            list(
                CourseEnrollment.objects.filter(user=self.user).values_list(
                    "id", "offering_id", "role"
                )
            ),
            self.snapshot["enrollment_ids"],
        )
        self.assertEqual(
            list(
                TimetableSlot.objects.filter(user=self.user).values_list(
                    "id", "offering_id", "slot_key"
                )
            ),
            self.snapshot["slot_ids"],
        )
        self.assertEqual(
            list(
                CourseReview.objects.filter(user=self.user).values_list(
                    "id", "offering_id", "comment"
                )
            ),
            self.snapshot["review_ids"],
        )
        # OfficialClass created, but no new/merged CourseOffering from import.
        self.assertEqual(
            CourseOffering.objects.count(), self.snapshot["offering_count"]
        )
        self.assertEqual(OfficialClass.objects.count(), 1)
        self.assertIsNone(OfficialClass.objects.get().canonical_offering_id)
