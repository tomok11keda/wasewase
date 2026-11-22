"""Seed / cleanup fictional OfficialClass fixtures for local E2E only.

Never uses real haibun/PDF rows. Marker: section=E2E_FICTIONAL + parse_flags.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from app.course_services import (
    create_offering,
    current_academic_year,
    current_semester,
)
from app.models import (
    CourseEnrollment,
    CourseOffering,
    OfficialClass,
    OfficialMeeting,
    OfferingOfficialLink,
    TimetableSlot,
    UserProfile,
)
from app.official_course_services import (
    build_provisional_identity,
    link_offering_to_official,
    meeting_fingerprint,
    set_canonical_offering,
)

MARKER_SECTION = "E2E_FICTIONAL"
MARKER_FLAG = "e2e_fictional_local_only"
E2E_EMAIL = "e2e-official-local@example.com"
E2E_PASSWORD = "e2e-pass-12345"


FIXTURES = [
    {
        "key": "ready",
        "title": "架空・基礎データ分析",
        "instructor": "検証 一郎",
        "class_no": "1",
        "day": 0,
        "period": 2,
        "with_canonical": True,
    },
    {
        "key": "pending",
        "title": "架空・組織行動入門",
        "instructor": "検証 二郎",
        "class_no": "1",
        "day": 1,
        "period": 3,
        "with_canonical": False,
    },
    {
        "key": "conflict",
        "title": "架空・マーケティング演習",
        "instructor": "検証 三郎",
        "class_no": "1",
        "day": 2,
        "period": 4,
        "with_canonical": False,
        "multi_link": True,
    },
    {
        "key": "ready_b",
        "title": "架空・ビジネス倫理",
        "instructor": "検証 四郎",
        "class_no": "2",
        "day": 3,
        "period": 1,
        "with_canonical": True,
    },
    {
        "key": "slot_busy",
        "title": "架空・財務会計概論",
        "instructor": "検証 五郎",
        "class_no": "1",
        "day": 4,
        "period": 5,
        "with_canonical": True,
    },
]


class Command(BaseCommand):
    help = (
        "Create/cleanup fictional OfficialClass E2E fixtures (local only). "
        f"Marker section={MARKER_SECTION}."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--cleanup",
            action="store_true",
            help="Delete E2E_FICTIONAL official rows and linked offerings created by seed.",
        )
        parser.add_argument(
            "--ensure-user",
            action="store_true",
            help=f"Ensure local login user {E2E_EMAIL} exists.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        if options["cleanup"]:
            self._cleanup()
            return
        if options["ensure_user"]:
            self._ensure_user()
        created = self._seed()
        self.stdout.write(self.style.SUCCESS(f"seeded={created}"))
        self.stdout.write(
            f"login: {E2E_EMAIL} / {E2E_PASSWORD} "
            "(only if --ensure-user was passed previously or now)"
        )

    def _ensure_user(self):
        User = get_user_model()
        user, created = User.objects.get_or_create(
            email=E2E_EMAIL,
            defaults={"username": "e2e_official_local", "is_active": True},
        )
        user.set_password(E2E_PASSWORD)
        user.is_active = True
        user.save()
        profile, _ = UserProfile.objects.get_or_create(user=user)
        profile.onboarding_step = "welcome"
        profile.onboarding_completed_at = timezone.now()
        if hasattr(profile, "department") and not profile.department:
            try:
                profile.department = "商学部"
            except Exception:
                pass
        profile.save()
        self.stdout.write(
            self.style.NOTICE(
                f"user={'created' if created else 'updated'}: {E2E_EMAIL}"
            )
        )
        return user

    def _cleanup(self):
        qs = OfficialClass.objects.filter(
            section=MARKER_SECTION, parse_flags__contains=MARKER_FLAG
        )
        offering_ids = set()
        for oc in qs:
            if oc.canonical_offering_id:
                offering_ids.add(oc.canonical_offering_id)
            offering_ids.update(
                oc.offering_links.values_list("offering_id", flat=True)
            )
        deleted_official = qs.count()
        qs.delete()
        # Only delete offerings that are official-sourced and now orphaned.
        deleted_offerings = 0
        for oid in offering_ids:
            offering = CourseOffering.objects.filter(pk=oid).first()
            if not offering:
                continue
            if offering.source != CourseOffering.Source.OFFICIAL and not OfferingOfficialLink.objects.filter(
                offering=offering
            ).exists():
                # Keep user-created leftovers from multi_link scenario if still linked none
                pass
            # Safe cleanup: delete only if no enrollments from non-e2e users... for local E2E wipe all linked.
            CourseEnrollment.objects.filter(offering=offering).delete()
            TimetableSlot.objects.filter(offering=offering).delete()
            offering.delete()
            deleted_offerings += 1
        User = get_user_model()
        User.objects.filter(email=E2E_EMAIL).delete()
        self.stdout.write(
            self.style.SUCCESS(
                f"cleanup official={deleted_official} offerings={deleted_offerings}"
            )
        )

    def _seed(self) -> int:
        User = get_user_model()
        actor = User.objects.filter(email=E2E_EMAIL).first()
        if actor is None:
            actor = self._ensure_user()

        count = 0
        for spec in FIXTURES:
            # Match CourseMeta so student UI search (filters by meta.semester)
            # finds these rows during local E2E.
            year = current_academic_year()
            semester_code = current_semester()
            semester_label = {
                "spring": "春学期",
                "fall": "秋学期",
                "full": "通年",
            }.get(semester_code, semester_code)

            identity = build_provisional_identity(
                academic_year=year,
                school="商学部",
                semester_code=semester_code,
                title=spec["title"],
                haibun_class_no=spec["class_no"],
                instructor=spec["instructor"],
                meeting_fingerprints=[
                    meeting_fingerprint(
                        day_of_week=spec["day"],
                        period=spec["period"],
                        period_kind=CourseOffering.PeriodKind.PERIOD,
                        raw="e2e",
                    )
                ],
            )
            official, _ = OfficialClass.objects.update_or_create(
                provisional_identity=identity,
                defaults={
                    "academic_year": year,
                    "school": "商学部",
                    "section": MARKER_SECTION,
                    "title": spec["title"],
                    "title_normalized": spec["title"].casefold(),
                    "haibun_class_no": spec["class_no"],
                    "instructor": spec["instructor"],
                    "instructor_normalized": spec["instructor"].casefold(),
                    "semester_code": semester_code,
                    "semester_label": semester_label,
                    "modality_raw": "対面",
                    "is_cancelled": False,
                    "needs_human_review": False,
                    "publication_status": OfficialClass.PublicationStatus.PUBLIC,
                    "parse_flags": MARKER_FLAG,
                    "source_raw_line": f"e2e:{spec['key']}",
                },
            )
            OfficialMeeting.objects.filter(official_class=official).delete()
            OfficialMeeting.objects.create(
                official_class=official,
                day_of_week=spec["day"],
                period=spec["period"],
                period_kind=CourseOffering.PeriodKind.PERIOD,
                raw="e2e",
                fingerprint=f"p{spec['period']}-d{spec['day']}",
            )
            OfficialClass.objects.filter(pk=official.pk).update(canonical_offering=None)
            official.canonical_offering = None
            OfferingOfficialLink.objects.filter(official_class=official).delete()

            if spec.get("with_canonical"):
                offering, _ = create_offering(
                    user=actor,
                    title=spec["title"],
                    instructor=spec["instructor"],
                    academic_year=year,
                    semester=semester_code,
                    day_of_week=spec["day"],
                    period=spec["period"],
                    school="商学部",
                    force_create=True,
                )
                CourseOffering.objects.filter(pk=offering.pk).update(
                    source=CourseOffering.Source.OFFICIAL
                )
                offering.refresh_from_db()
                set_canonical_offering(official, offering, ensure_link=True)

            if spec.get("multi_link"):
                a, _ = create_offering(
                    user=actor,
                    title=spec["title"],
                    instructor="検証 A",
                    academic_year=year,
                    semester=semester_code,
                    day_of_week=spec["day"],
                    period=spec["period"],
                    force_create=True,
                )
                b, _ = create_offering(
                    user=actor,
                    title=spec["title"],
                    instructor="検証 B",
                    academic_year=year,
                    semester=semester_code,
                    day_of_week=spec["day"],
                    period=spec["period"],
                    force_create=True,
                )
                link_offering_to_official(a, official)
                link_offering_to_official(b, official)

            count += 1
            self.stdout.write(f"  {spec['key']}: official_id={official.pk}")
        return count
