"""Local / staging CSV import for OfficialClass (Option B).

Default is dry-run. Never invents subject_key. Does not merge CourseOffering.
"""

from __future__ import annotations

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from app.official_course_services import (
    PILOT_PUBLICATION_STATUS,
    import_official_classes_from_csv,
)


class Command(BaseCommand):
    help = (
        "Import OfficialClass rows from a pilot CSV. "
        "Defaults to --dry-run (no DB writes)."
    )

    def add_arguments(self, parser):
        parser.add_argument("csv_path", type=str)
        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=True,
            help="Validate only (default).",
        )
        parser.add_argument(
            "--commit",
            action="store_true",
            help="Actually write OfficialClass rows (overrides --dry-run).",
        )
        parser.add_argument(
            "--publication-status",
            default=PILOT_PUBLICATION_STATUS,
            help="Default research_only. Do not set public without legal clearance.",
        )

    def handle(self, *args, **options):
        path = Path(options["csv_path"])
        if not path.is_file():
            raise CommandError(f"csv not found: {path}")
        dry_run = not options["commit"]
        status = options["publication_status"]
        if status == "public" and dry_run is False:
            self.stderr.write(
                self.style.WARNING(
                    "Refusing silent public import: pass publication_status only "
                    "after legal clearance; use research_only for pilot."
                )
            )
            if status == "public":
                raise CommandError(
                    "publication_status=public requires an explicit ops review; "
                    "use research_only for local pilot."
                )
        report = import_official_classes_from_csv(
            path,
            dry_run=dry_run,
            publication_status=status,
        )
        payload = report.to_dict()
        # Keep results short in stdout
        results = payload.pop("results", [])
        payload["result_count"] = len(results)
        payload["dry_run"] = dry_run
        self.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2))
        if dry_run:
            self.stdout.write(self.style.NOTICE("dry-run only; no rows written"))
