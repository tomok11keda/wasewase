"""Official course master (Option B): provisional identity, CSV dry-run import, linking.

Never invents syllabus subject_key / class codes.
Never auto-merges CourseOffering / course talks.
"""

from __future__ import annotations

import csv
import hashlib
import re
import unicodedata
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable

from django.contrib.auth.base_user import AbstractBaseUser
from django.db import transaction
from django.db.models import Count
from django.utils import timezone

from .course_meeting_services import ensure_meetings_for_offering
from .course_services import get_or_create_course, normalize_course_text
from .models import (
    CourseEnrollment,
    CourseMeeting,
    CourseOffering,
    OfficialClass,
    OfficialClassImportBatch,
    OfficialClassImportRow,
    OfficialMeeting,
    OfferingOfficialLink,
)

PROVISIONAL_PREFIX = "haibun:v1:"
PILOT_PUBLICATION_STATUS = OfficialClass.PublicationStatus.RESEARCH_ONLY

ALLOWED_SEMESTER_CODES = frozenset(
    {
        "spring",
        "fall",
        "full",
        "spring_q",
        "summer_q",
        "fall_q",
        "winter_q",
        "summer_intensive",
    }
)
ALLOWED_PERIOD_KINDS = frozenset(
    {
        CourseOffering.PeriodKind.PERIOD,
        CourseOffering.PeriodKind.OD,
        "period",
        "od",
    }
)


def _nfkc(value: str | None) -> str:
    return unicodedata.normalize("NFKC", (value or "")).strip()


def normalize_official_text(value: str | None) -> str:
    text = _nfkc(value)
    text = re.sub(r"\s+", " ", text)
    return text.casefold()


def meeting_fingerprint(
    *,
    day_of_week: int | None,
    period: int | None,
    period_kind: str,
    raw: str = "",
) -> str:
    if period_kind == CourseOffering.PeriodKind.OD or (
        day_of_week is None and period is None and raw in {"無", "なし"}
    ):
        return "od"
    if day_of_week is None or period is None:
        return f"raw:{normalize_official_text(raw)}" if raw else ""
    prefix = "od" if period_kind == CourseOffering.PeriodKind.OD else "p"
    return f"{prefix}{int(period)}-d{int(day_of_week)}"


def build_provisional_identity(
    *,
    academic_year: int,
    school: str,
    semester_code: str,
    title: str,
    haibun_class_no: str,
    instructor: str,
    meeting_fingerprints: Iterable[str],
) -> str:
    """Deterministic identity from published haibun fields only.

    This is NOT a syllabus subject_key. It is a content hash key that can be
    replaced later when official subject_key + class_code become available.
    """
    meetings = sorted({m for m in meeting_fingerprints if m})
    parts = [
        str(int(academic_year)),
        normalize_official_text(school),
        normalize_official_text(semester_code),
        normalize_official_text(title),
        normalize_official_text(haibun_class_no),
        normalize_official_text(instructor),
        ";".join(meetings),
    ]
    body = "|".join(parts)
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()[:20]
    return f"{PROVISIONAL_PREFIX}{digest}"


def map_semester_to_offering(semester_code: str) -> str | None:
    """Map official semester codes onto CourseOffering.Semester when possible."""
    code = normalize_official_text(semester_code)
    mapping = {
        "spring": CourseOffering.Semester.SPRING,
        "fall": CourseOffering.Semester.FALL,
        "full": CourseOffering.Semester.FULL,
        # Quarter / intensive: keep searchable on OfficialClass, but canonical
        # CourseOffering uses nearest parent term only when explicitly mapped.
        "spring_q": CourseOffering.Semester.SPRING,
        "summer_q": CourseOffering.Semester.SPRING,
        "fall_q": CourseOffering.Semester.FALL,
        "winter_q": CourseOffering.Semester.FALL,
        "summer_intensive": CourseOffering.Semester.SPRING,
    }
    return mapping.get(code)


@dataclass
class ImportRowResult:
    line_no: int
    action: str
    provisional_identity: str = ""
    title: str = ""
    reasons: list[str] = field(default_factory=list)


@dataclass
class ImportDryRunReport:
    source_path: str
    total_rows: int = 0
    would_create: int = 0
    would_update: int = 0
    would_skip_duplicate: int = 0
    would_reject: int = 0
    would_unchanged: int = 0
    results: list[ImportRowResult] = field(default_factory=list)
    batch_id: int | None = None
    source_sha256: str = ""
    dry_run: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _parse_optional_int(value: str) -> int | None:
    value = _nfkc(value)
    if value == "":
        return None
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError("invalid_integer") from exc


def _row_meetings(row: dict[str, str]) -> tuple[list[dict[str, Any]], list[str]]:
    """Parse meeting columns; return (meetings, validation_errors)."""
    meetings: list[dict[str, Any]] = []
    errors: list[str] = []
    for idx in (1, 2):
        raw = _nfkc(row.get(f"meeting_{idx}_raw") or "")
        day_raw = row.get(f"meeting_{idx}_day") or ""
        period_raw = row.get(f"meeting_{idx}_period") or ""
        kind = _nfkc(row.get(f"meeting_{idx}_period_kind") or "")
        if not raw and not day_raw and not period_raw and not kind:
            continue
        if not raw and (day_raw or period_raw or kind):
            errors.append(f"meeting_{idx}_raw_missing")
            continue
        if not kind:
            kind = (
                CourseOffering.PeriodKind.OD
                if raw in {"無", "なし"}
                else CourseOffering.PeriodKind.PERIOD
            )
        if kind not in ALLOWED_PERIOD_KINDS:
            errors.append(f"invalid_period_kind_{idx}")
            continue
        try:
            day = _parse_optional_int(day_raw)
            period = _parse_optional_int(period_raw)
        except ValueError:
            errors.append(f"invalid_meeting_int_{idx}")
            continue
        if kind == CourseOffering.PeriodKind.PERIOD:
            if day is None or period is None:
                errors.append(f"missing_day_or_period_{idx}")
                continue
            if day < 0 or day > 6:
                errors.append(f"invalid_day_of_week_{idx}")
                continue
            if period < 1 or period > 7:
                errors.append(f"invalid_period_{idx}")
                continue
        elif kind == CourseOffering.PeriodKind.OD:
            if day is not None and (day < 0 or day > 6):
                errors.append(f"invalid_day_of_week_{idx}")
                continue
            if period is not None and (period < 1 or period > 7):
                errors.append(f"invalid_period_{idx}")
                continue
        meetings.append(
            {
                "raw": raw,
                "day_of_week": day,
                "period": period,
                "period_kind": kind,
                "fingerprint": meeting_fingerprint(
                    day_of_week=day,
                    period=period,
                    period_kind=kind,
                    raw=raw,
                ),
            }
        )
    return meetings, errors


def classify_pilot_csv_row(row: dict[str, str]) -> list[str]:
    """Return reject reasons; empty means importable (possibly review-flagged)."""
    reasons: list[str] = []
    title = _nfkc(row.get("title") or "")
    school = _nfkc(row.get("school") or "")
    year_raw = _nfkc(row.get("academic_year") or "")
    semester = _nfkc(row.get("semester_code") or "")
    cancelled = (row.get("is_cancelled") or "").lower() == "true"

    if not title:
        reasons.append("missing_title")
    if not school:
        reasons.append("missing_school")
    if not year_raw:
        reasons.append("missing_academic_year")
    else:
        try:
            year = int(year_raw)
            if year < 2000 or year > 2100:
                reasons.append("invalid_academic_year")
        except ValueError:
            reasons.append("invalid_academic_year")

    if not semester:
        reasons.append("missing_semester_code")
    elif semester not in ALLOWED_SEMESTER_CODES:
        reasons.append("invalid_semester_code")

    if title in {"Researchers"}:
        reasons.append("garbage_title_fragment")
    if (
        title.startswith("Working on Empirical Data for Management")
        and "Researchers" not in title
    ):
        reasons.append("garbage_title_fragment")
    if re.fullmatch(r"[月火水木金土日]\s*[1-7]", title):
        reasons.append("garbage_slot_as_title")

    flags = [f for f in (row.get("parse_flags") or "").split(",") if f]
    if "merged_title_suspect" in flags:
        reasons.append("merged_title_suspect")

    # Invented official keys are rejected (must stay blank unless later feed).
    if _nfkc(row.get("subject_key") or "") and "invented" in (
        row.get("parse_flags") or ""
    ):
        reasons.append("invented_subject_key_forbidden")

    meetings, meeting_errors = _row_meetings(row)
    reasons.extend(meeting_errors)
    if not cancelled and not meetings:
        reasons.append("missing_meetings")

    return reasons


def load_pilot_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _identity_for_row(row: dict[str, str], meetings: list[dict[str, Any]]) -> str:
    year_raw = _nfkc(row.get("academic_year") or "") or "0"
    try:
        year = int(year_raw)
    except ValueError:
        year = 0
    return build_provisional_identity(
        academic_year=year,
        school=row.get("school") or "",
        semester_code=row.get("semester_code") or "",
        title=row.get("title") or "",
        haibun_class_no=row.get("haibun_class_no") or "",
        instructor=row.get("instructor") or "",
        meeting_fingerprints=[m["fingerprint"] for m in meetings],
    )


def _official_defaults_from_row(
    row: dict[str, str], *, publication_status: str
) -> dict[str, Any]:
    return {
        "academic_year": int(_nfkc(row.get("academic_year") or "0") or 0),
        "school": _nfkc(row.get("school") or ""),
        "section": _nfkc(row.get("section") or ""),
        "title": _nfkc(row.get("title") or ""),
        "title_normalized": normalize_official_text(row.get("title") or ""),
        "haibun_class_no": _nfkc(row.get("haibun_class_no") or ""),
        "instructor": _nfkc(row.get("instructor") or ""),
        "instructor_normalized": normalize_official_text(row.get("instructor") or ""),
        "semester_code": _nfkc(row.get("semester_code") or ""),
        "semester_label": _nfkc(row.get("semester_label") or ""),
        "credits": _nfkc(row.get("credits") or ""),
        "modality_raw": _nfkc(row.get("modality_raw") or ""),
        "is_cancelled": (row.get("is_cancelled") or "").lower() == "true",
        # Never invent: store blank if empty; do not synthesize.
        "subject_key": _nfkc(row.get("subject_key") or ""),
        "syllabus_class_code": _nfkc(row.get("syllabus_class_code") or ""),
        "course_code": _nfkc(row.get("course_code") or ""),
        "source_url": _nfkc(row.get("source_url") or ""),
        "source_listing_page": _nfkc(row.get("source_listing_page") or ""),
        "source_extract_line": int(_nfkc(row.get("source_extract_line") or "0") or 0),
        "source_raw_line": (row.get("source_raw_line") or "")[:2000],
        "parse_flags": _nfkc(row.get("parse_flags") or ""),
        "needs_human_review": (row.get("needs_human_review") or "").lower() == "true",
        "publication_status": publication_status,
    }


def _payload_fingerprint(defaults: dict[str, Any], meetings: list[dict[str, Any]]) -> str:
    parts = [
        str(defaults.get(k, ""))
        for k in (
            "academic_year",
            "school",
            "section",
            "title",
            "haibun_class_no",
            "instructor",
            "semester_code",
            "semester_label",
            "credits",
            "modality_raw",
            "is_cancelled",
            "parse_flags",
            "needs_human_review",
            "publication_status",
        )
    ]
    meeting_parts = [
        f"{m.get('fingerprint')}:{m.get('raw')}:{m.get('period_kind')}"
        for m in meetings
    ]
    body = "|".join(parts + meeting_parts)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def _existing_payload_fingerprint(official: OfficialClass) -> str:
    meetings = [
        {
            "fingerprint": m.fingerprint,
            "raw": m.raw,
            "period_kind": m.period_kind,
        }
        for m in official.meetings.order_by("id")
    ]
    defaults = {
        "academic_year": official.academic_year,
        "school": official.school,
        "section": official.section,
        "title": official.title,
        "haibun_class_no": official.haibun_class_no,
        "instructor": official.instructor,
        "semester_code": official.semester_code,
        "semester_label": official.semester_label,
        "credits": official.credits,
        "modality_raw": official.modality_raw,
        "is_cancelled": official.is_cancelled,
        "parse_flags": official.parse_flags,
        "needs_human_review": official.needs_human_review,
        "publication_status": official.publication_status,
    }
    return _payload_fingerprint(defaults, meetings)


def dry_run_import_official_classes(
    path: Path,
    *,
    publication_status: str = PILOT_PUBLICATION_STATUS,
) -> ImportDryRunReport:
    """Validate CSV against current DB without writing OfficialClass rows."""
    rows = load_pilot_csv_rows(path)
    report = ImportDryRunReport(
        source_path=str(path),
        total_rows=len(rows),
        source_sha256=file_sha256(path) if path.is_file() else "",
        dry_run=True,
    )
    seen_identities: set[str] = set()

    for idx, row in enumerate(rows, start=2):  # header is line 1
        meetings, _ = _row_meetings(row)
        reject = classify_pilot_csv_row(row)
        identity = _identity_for_row(row, meetings)
        title = _nfkc(row.get("title") or "")
        if reject:
            report.would_reject += 1
            report.results.append(
                ImportRowResult(
                    line_no=idx,
                    action="reject",
                    provisional_identity=identity,
                    title=title,
                    reasons=reject,
                )
            )
            continue
        if identity in seen_identities:
            report.would_skip_duplicate += 1
            report.results.append(
                ImportRowResult(
                    line_no=idx,
                    action="skip_duplicate_in_file",
                    provisional_identity=identity,
                    title=title,
                    reasons=["duplicate_in_csv"],
                )
            )
            continue
        seen_identities.add(identity)
        existing = OfficialClass.objects.filter(provisional_identity=identity).first()
        if existing:
            defaults = _official_defaults_from_row(
                row, publication_status=publication_status
            )
            if _payload_fingerprint(defaults, meetings) == _existing_payload_fingerprint(
                existing
            ):
                report.would_unchanged += 1
                report.results.append(
                    ImportRowResult(
                        line_no=idx,
                        action="unchanged",
                        provisional_identity=identity,
                        title=title,
                        reasons=[f"existing_id={existing.pk}"],
                    )
                )
            else:
                report.would_update += 1
                report.results.append(
                    ImportRowResult(
                        line_no=idx,
                        action="update",
                        provisional_identity=identity,
                        title=title,
                        reasons=[f"existing_id={existing.pk}"],
                    )
                )
        else:
            report.would_create += 1
            report.results.append(
                ImportRowResult(
                    line_no=idx,
                    action="create",
                    provisional_identity=identity,
                    title=title,
                    reasons=[],
                )
            )
    return report


def _persist_import_batch(
    report: ImportDryRunReport,
    *,
    dry_run: bool,
    publication_status: str,
    actor: AbstractBaseUser | None,
    status: str,
    error_message: str = "",
    identity_to_official: dict[str, OfficialClass] | None = None,
) -> OfficialClassImportBatch:
    identity_to_official = identity_to_official or {}
    batch = OfficialClassImportBatch.objects.create(
        source_path=report.source_path,
        source_sha256=report.source_sha256,
        dry_run=dry_run,
        publication_status=publication_status,
        status=status,
        total_rows=report.total_rows,
        created_count=report.would_create,
        updated_count=report.would_update,
        skipped_duplicate_count=report.would_skip_duplicate,
        rejected_count=report.would_reject,
        summary_json=json_dumps_report(report),
        error_message=error_message,
        started_by=actor if getattr(actor, "pk", None) else None,
        finished_at=timezone.now(),
    )
    row_objs = []
    for result in report.results:
        official = identity_to_official.get(result.provisional_identity)
        row_objs.append(
            OfficialClassImportRow(
                batch=batch,
                line_no=result.line_no,
                action=result.action,
                provisional_identity=result.provisional_identity,
                title=result.title[:200],
                reasons=",".join(result.reasons)[:500],
                official_class=official,
            )
        )
    OfficialClassImportRow.objects.bulk_create(row_objs, batch_size=500)
    report.batch_id = batch.pk
    return batch


def json_dumps_report(report: ImportDryRunReport) -> str:
    import json

    payload = report.to_dict()
    # Cap stored row detail for huge files
    if len(payload.get("results") or []) > 500:
        payload["results"] = payload["results"][:500]
        payload["results_truncated"] = True
    return json.dumps(payload, ensure_ascii=False)


@transaction.atomic
def import_official_classes_from_csv(
    path: Path,
    *,
    dry_run: bool = True,
    publication_status: str = PILOT_PUBLICATION_STATUS,
    actor: AbstractBaseUser | None = None,
    record_history: bool = True,
) -> ImportDryRunReport:
    """Import OfficialClass rows. Default dry_run=True writes no OfficialClass.

    Never creates/merges CourseOffering. Never invents subject_key.
    Re-import is idempotent via provisional_identity.
    """
    if publication_status == OfficialClass.PublicationStatus.PUBLIC and not dry_run:
        raise ValueError("public_import_forbidden_without_clearance")

    report = dry_run_import_official_classes(
        path, publication_status=publication_status
    )
    report.dry_run = dry_run
    identity_to_official: dict[str, OfficialClass] = {}

    if dry_run:
        if record_history:
            _persist_import_batch(
                report,
                dry_run=True,
                publication_status=publication_status,
                actor=actor,
                status=OfficialClassImportBatch.Status.DRY_RUN,
            )
        return report

    try:
        rows = load_pilot_csv_rows(path)
        for row in rows:
            reject = classify_pilot_csv_row(row)
            if reject:
                continue
            meetings, meeting_errors = _row_meetings(row)
            if meeting_errors:
                continue
            identity = _identity_for_row(row, meetings)
            defaults = _official_defaults_from_row(
                row, publication_status=publication_status
            )
            # Preserve an already-set canonical_offering on update.
            obj, _created = OfficialClass.objects.update_or_create(
                provisional_identity=identity,
                defaults=defaults,
            )
            OfficialMeeting.objects.filter(official_class=obj).delete()
            for meeting in meetings:
                OfficialMeeting.objects.create(
                    official_class=obj,
                    day_of_week=meeting["day_of_week"],
                    period=meeting["period"],
                    period_kind=meeting["period_kind"],
                    raw=meeting["raw"],
                    fingerprint=meeting["fingerprint"],
                )
            identity_to_official[identity] = obj
        if record_history:
            _persist_import_batch(
                report,
                dry_run=False,
                publication_status=publication_status,
                actor=actor,
                status=OfficialClassImportBatch.Status.COMMITTED,
                identity_to_official=identity_to_official,
            )
    except Exception as exc:
        if record_history:
            _persist_import_batch(
                report,
                dry_run=False,
                publication_status=publication_status,
                actor=actor,
                status=OfficialClassImportBatch.Status.FAILED,
                error_message=str(exc)[:2000],
            )
        raise
    return report


def find_offering_match_candidates(
    official: OfficialClass, *, limit: int = 10
) -> list[CourseOffering]:
    """Heuristic candidates for manual linking — never auto-applied."""
    qs = CourseOffering.objects.filter(
        status=CourseOffering.Status.ACTIVE,
        academic_year=official.academic_year,
        title_normalized=official.title_normalized,
    )
    semester = map_semester_to_offering(official.semester_code)
    if semester:
        qs = qs.filter(semester=semester)
    if official.instructor_normalized:
        qs = qs.filter(instructor_normalized=official.instructor_normalized)
    return list(qs.order_by("pk")[:limit])


class MultipleOfferingsForOfficial(Exception):
    """Raised when enrollment cannot choose a canonical offering safely."""

    def __init__(self, official: OfficialClass, offering_ids: list[int]):
        self.official = official
        self.offering_ids = offering_ids
        super().__init__(
            f"official_class={official.pk} has multiple linked offerings: {offering_ids}"
        )


class CanonicalOfferingRequired(Exception):
    """Raised when enrollment is blocked until an admin sets canonical_offering."""

    def __init__(self, official: OfficialClass, *, reason: str = "pending_canonical"):
        self.official = official
        self.reason = reason
        super().__init__(f"official_class={official.pk} {reason}")


def linked_active_offerings(official: OfficialClass) -> list[CourseOffering]:
    links = (
        OfferingOfficialLink.objects.filter(official_class=official)
        .select_related("offering")
        .order_by("id")
    )
    out: list[CourseOffering] = []
    for link in links:
        offering = link.offering
        if offering.status == CourseOffering.Status.ACTIVE:
            out.append(offering)
    return out


def enrollment_readiness(official: OfficialClass) -> dict[str, Any]:
    """Safe status for student enroll / admin queues. Never mutates data."""
    if official.is_cancelled:
        return {
            "status": "cancelled",
            "ready": False,
            "canonical_offering_id": official.canonical_offering_id,
            "active_linked_count": len(linked_active_offerings(official)),
        }
    if official.canonical_offering_id:
        canonical = CourseOffering.objects.filter(
            pk=official.canonical_offering_id,
            status=CourseOffering.Status.ACTIVE,
        ).first()
        if canonical:
            return {
                "status": "ready",
                "ready": True,
                "canonical_offering_id": canonical.pk,
                "active_linked_count": len(linked_active_offerings(official)),
            }
    linked = linked_active_offerings(official)
    if len(linked) > 1:
        return {
            "status": "conflict",
            "ready": False,
            "canonical_offering_id": None,
            "active_linked_count": len(linked),
            "active_linked_offering_ids": [o.pk for o in linked],
        }
    return {
        "status": "pending_canonical",
        "ready": False,
        "canonical_offering_id": None,
        "active_linked_count": len(linked),
        "active_linked_offering_ids": [o.pk for o in linked],
    }


def resolve_enrollment_offering(
    official: OfficialClass,
    *,
    create_if_missing: bool = False,
    actor: AbstractBaseUser | None = None,
) -> CourseOffering:
    """Pick the CourseOffering new users should join — without merging others.

    Priority:
    1) official.canonical_offering if active (required for student enroll)
    2) create_if_missing=True only for explicit admin tooling
       (never used by CSV import)
    3) otherwise pending_canonical / conflict errors — no silent create/merge
    """
    if official.is_cancelled:
        raise CanonicalOfferingRequired(official, reason="cancelled")

    if official.canonical_offering_id:
        canonical = CourseOffering.objects.filter(pk=official.canonical_offering_id).first()
        if canonical and canonical.status == CourseOffering.Status.ACTIVE:
            return canonical

    linked = linked_active_offerings(official)
    if len(linked) > 1:
        raise MultipleOfferingsForOfficial(official, [o.pk for o in linked])

    if create_if_missing:
        # Explicit admin path only — still does not merge existing offerings.
        return create_offering_from_official(official, actor=actor, set_canonical=True)

    raise CanonicalOfferingRequired(official, reason="pending_canonical")


@transaction.atomic
def set_canonical_offering(
    official: OfficialClass,
    offering: CourseOffering,
    *,
    ensure_link: bool = True,
    actor: AbstractBaseUser | None = None,
) -> OfficialClass:
    """Admin-explicit canonical selection. Does not merge or delete offerings."""
    official = OfficialClass.objects.select_for_update().get(pk=official.pk)
    offering = CourseOffering.objects.select_for_update().get(pk=offering.pk)
    if offering.status != CourseOffering.Status.ACTIVE:
        raise ValueError("offering_inactive")
    if ensure_link:
        OfferingOfficialLink.objects.update_or_create(
            offering=offering,
            defaults={
                "official_class": official,
                "match_method": OfferingOfficialLink.MatchMethod.MANUAL,
                "confidence": 1.0,
                "reviewed_at": timezone.now(),
            },
        )
    OfficialClass.objects.filter(pk=official.pk).update(canonical_offering=offering)
    official.canonical_offering = offering
    return official


@transaction.atomic
def create_offering_from_official(
    official: OfficialClass,
    *,
    actor: AbstractBaseUser | None = None,
    set_canonical: bool = True,
) -> CourseOffering:
    """Create a fresh CourseOffering mirroring OfficialClass (no merge)."""
    semester = map_semester_to_offering(official.semester_code)
    if semester is None:
        raise ValueError("unsupported_semester_for_offering")

    meetings = list(official.meetings.order_by("id"))
    if not meetings:
        raise ValueError("official_class_has_no_meetings")

    primary = meetings[0]
    day = primary.day_of_week if primary.day_of_week is not None else 0
    period = primary.period if primary.period is not None else 1
    period_kind = primary.period_kind or CourseOffering.PeriodKind.PERIOD
    if primary.fingerprint == "od":
        period_kind = CourseOffering.PeriodKind.OD
        period = period or 1

    course = get_or_create_course(official.title)
    offering = CourseOffering.objects.create(
        course=course,
        academic_year=official.academic_year,
        semester=semester,
        title=official.title,
        title_normalized=official.title_normalized
        or normalize_course_text(official.title),
        instructor=official.instructor or "未設定",
        instructor_normalized=official.instructor_normalized
        or normalize_course_text(official.instructor or "未設定"),
        day_of_week=day,
        period_kind=period_kind,
        period=period,
        school=official.school,
        campus="",
        room="",
        credits=official.credits,
        created_by=actor if getattr(actor, "pk", None) else None,
        source=CourseOffering.Source.OFFICIAL,
        status=CourseOffering.Status.ACTIVE,
    )
    specs = []
    for meeting in meetings:
        if meeting.fingerprint == "od" or meeting.period_kind == CourseOffering.PeriodKind.OD:
            specs.append(
                {
                    "day_of_week": meeting.day_of_week or 0,
                    "period": meeting.period or 1,
                    "period_kind": CourseOffering.PeriodKind.OD,
                }
            )
        elif meeting.day_of_week is not None and meeting.period is not None:
            specs.append(
                {
                    "day_of_week": meeting.day_of_week,
                    "period": meeting.period,
                    "period_kind": meeting.period_kind or CourseOffering.PeriodKind.PERIOD,
                }
            )
    if specs:
        ensure_meetings_for_offering(offering, specs)

    OfferingOfficialLink.objects.update_or_create(
        offering=offering,
        defaults={
            "official_class": official,
            "match_method": OfferingOfficialLink.MatchMethod.CREATED_FROM_OFFICIAL,
            "confidence": 1.0,
            "reviewed_at": timezone.now(),
        },
    )
    if set_canonical:
        OfficialClass.objects.filter(pk=official.pk).update(canonical_offering=offering)
        official.canonical_offering = offering
    return offering


@transaction.atomic
def link_offering_to_official(
    offering: CourseOffering,
    official: OfficialClass,
    *,
    match_method: str = OfferingOfficialLink.MatchMethod.MANUAL,
    confidence: float = 1.0,
    set_as_canonical: bool = False,
) -> OfferingOfficialLink:
    """Manual / reviewed link. Refuses to silently change canonical when conflicts exist."""
    offering = CourseOffering.objects.select_for_update().get(pk=offering.pk)
    official = OfficialClass.objects.select_for_update().get(pk=official.pk)
    if offering.status != CourseOffering.Status.ACTIVE:
        raise ValueError("offering_inactive")

    link, _ = OfferingOfficialLink.objects.update_or_create(
        offering=offering,
        defaults={
            "official_class": official,
            "match_method": match_method,
            "confidence": confidence,
            "reviewed_at": timezone.now(),
        },
    )
    if set_as_canonical:
        linked = linked_active_offerings(official)
        # Setting canonical does not merge other offerings.
        OfficialClass.objects.filter(pk=official.pk).update(canonical_offering=offering)
        official.canonical_offering = offering
        # Annotate conflict count for callers.
        link.confidence = confidence
        if len(linked) > 1:
            # Keep link; caller should schedule manual merge review.
            pass
    return link


def official_link_conflict_summary(official: OfficialClass) -> dict[str, Any]:
    linked = linked_active_offerings(official)
    return {
        "official_class_id": official.pk,
        "canonical_offering_id": official.canonical_offering_id,
        "active_linked_offering_ids": [o.pk for o in linked],
        "active_linked_count": len(linked),
        "needs_manual_canonical": len(linked) > 1 and not official.canonical_offering_id,
        "auto_merge_allowed": False,
    }


def count_enrollment_by_offering(offering_ids: list[int]) -> dict[int, int]:
    rows = (
        CourseEnrollment.objects.filter(offering_id__in=offering_ids)
        .values("offering_id")
        .annotate(c=Count("id"))
    )
    return {row["offering_id"]: row["c"] for row in rows}
