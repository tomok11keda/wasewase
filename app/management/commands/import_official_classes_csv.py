"""Local / staging CSV import for OfficialClass (Option B).

Default is dry-run. Never invents subject_key. Does not create/merge CourseOffering.
Records import history for admin review.
"""

from __future__ import annotations

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from app.models import OfficialClass
from app.official_course_services import (
    PILOT_PUBLICATION_STATUS,
    import_official_classes_from_csv,
)


class Command(BaseCommand):
    help = (
        "Import OfficialClass rows from a pilot CSV. "
        "Defaults to dry-run (no OfficialClass writes). "
        "Use --commit to write. History is always recorded."
    )

    def add_arguments(self, parser):
        parser.add_argument("csv_path", type=str)
        parser.add_argument(
            "--dry-run",
            action="store_true",
            dest="force_dry_run",
            help="Force dry-run (default when --commit is omitted).",
        )
        parser.add_argument(
            "--commit",
            action="store_true",
            help="Actually write OfficialClass rows (still never touches CourseOffering).",
        )
        parser.add_argument(
            "--publication-status",
            default=PILOT_PUBLICATION_STATUS,
            choices=[c.value for c in OfficialClass.PublicationStatus],
            help="Default research_only. public is refused on --commit.",
        )
        parser.add_argument(
            "--no-history",
            action="store_true",
            help="Do not persist OfficialClassImportBatch (tests only).",
        )
        parser.add_argument(
            "--fail-on-reject",
            action="store_true",
            help="Exit non-zero if any row would be rejected.",
        )

    def handle(self, *args, **options):
        path = Path(options["csv_path"])
        if not path.is_file():
            raise CommandError(f"csv not found: {path}")

        if options["commit"] and options.get("force_dry_run"):
            raise CommandError("Use either --commit or --dry-run, not both.")

        dry_run = not options["commit"]
        status = options["publication_status"]

        if status == OfficialClass.PublicationStatus.PUBLIC and not dry_run:
            raise CommandError(
                "publication_status=public is refused on --commit. "
                "Keep research_only until legal clearance."
            )

        try:
            report = import_official_classes_from_csv(
                path,
                dry_run=dry_run,
                publication_status=status,
                record_history=not options["no_history"],
            )
        except ValueError as exc:
            raise CommandError(str(exc)) from exc

        payload = report.to_dict()
        results = payload.pop("results", [])
        payload["result_count"] = len(results)
        payload["dry_run"] = dry_run
        self.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2))

        if dry_run:
            self.stdout.write(
                self.style.NOTICE(
                    "dry-run only; OfficialClass not written "
                    f"(batch_id={report.batch_id})"
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f"committed OfficialClass rows (batch_id={report.batch_id}); "
                    "CourseOffering untouched"
                )
            )

        if options["fail_on_reject"] and report.would_reject:
            raise CommandError(f"rejected_rows={report.would_reject}")
