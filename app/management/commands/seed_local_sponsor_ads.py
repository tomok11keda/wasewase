"""ローカル検証用の架空スポンサー広告を投入する。

本番・Render では実行できない（DEBUG 必須 + 明示フラグ）。
架空在庫を本番に載せないためのガード。
"""

from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from app.models import SponsoredAd, SponsoredAdPlacement


class Command(BaseCommand):
    help = "Seed fictional sponsor ads for local QA only (DEBUG required)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Replace existing local-seed ads with the same titles.",
        )

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError(
                "Refusing to seed: DEBUG is False (not a local environment)."
            )
        if getattr(settings, "IS_RENDER", False) or getattr(
            settings, "RENDER", False
        ):
            raise CommandError("Refusing to seed on Render.")
        if not getattr(settings, "WASE_SPONSOR_ADS_ENABLED", False):
            self.stdout.write(
                self.style.WARNING(
                    "WASE_SPONSOR_ADS_ENABLED is False — inventory will be "
                    "created but not served until the flag is enabled."
                )
            )

        now = timezone.now()
        specs = [
            {
                "kind": SponsoredAd.Kind.SPONSORED,
                "sponsor_name": "架空カフェ合同会社",
                "title": "【検証用】キャンパス近くの勉強カフェ",
                "description": "ローカル検証専用の架空スポンサーです。本番掲載禁止。",
                "cta_url": "https://example.com/fictional-cafe",
                "placements": [
                    SponsoredAdPlacement.Placement.HOME_FEED,
                    SponsoredAdPlacement.Placement.DISCOVER_FEATURED,
                ],
            },
            {
                "kind": SponsoredAd.Kind.INTERNAL_PROMOTION,
                "sponsor_name": "わせわせ運営",
                "title": "【検証用】公式からのお知らせサンプル",
                "description": "ローカル検証用の公式プロモーション枠です。",
                "cta_url": "https://example.com/fictional-official",
                "placements": [SponsoredAdPlacement.Placement.DISCOVER_FEATURED],
            },
        ]

        created = 0
        for spec in specs:
            placements = spec.pop("placements")
            existing = SponsoredAd.objects.filter(title=spec["title"]).first()
            if existing and options["force"]:
                existing.delete()
                existing = None
            if existing:
                self.stdout.write(f"skip existing: {spec['title']}")
                continue
            ad = SponsoredAd.objects.create(
                **spec,
                is_active=True,
                starts_at=now - timedelta(hours=1),
                ends_at=now + timedelta(days=30),
                priority=10,
                admin_notes="seed_local_sponsor_ads — fictional / local only",
                cta_label="詳しく見る",
            )
            for key in placements:
                SponsoredAdPlacement.objects.create(
                    ad=ad, placement=key, is_enabled=True
                )
            created += 1
            self.stdout.write(self.style.SUCCESS(f"created ad#{ad.pk}: {ad.title}"))

        self.stdout.write(self.style.SUCCESS(f"done. created={created}"))
