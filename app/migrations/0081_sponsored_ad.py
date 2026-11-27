# Sponsored ads / official promotions (schema only — no seed inventory).

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("app", "0080_pushcampaign_timeline_post"),
    ]

    operations = [
        migrations.CreateModel(
            name="SponsoredAd",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "kind",
                    models.CharField(
                        choices=[
                            ("internal_promotion", "公式プロモーション"),
                            ("sponsored", "外部スポンサー"),
                        ],
                        db_index=True,
                        default="sponsored",
                        max_length=32,
                        verbose_name="種別",
                    ),
                ),
                (
                    "sponsor_name",
                    models.CharField(max_length=80, verbose_name="スポンサー名"),
                ),
                ("title", models.CharField(max_length=120, verbose_name="タイトル")),
                (
                    "description",
                    models.TextField(blank=True, default="", verbose_name="説明"),
                ),
                (
                    "image",
                    models.ImageField(
                        blank=True,
                        help_text="任意。カード用の横長画像を推奨。",
                        null=True,
                        upload_to="sponsor_ads/",
                        verbose_name="画像",
                    ),
                ),
                (
                    "cta_url",
                    models.URLField(
                        help_text="外部リンクは HTTPS 必須。",
                        max_length=500,
                        verbose_name="CTAリンク",
                    ),
                ),
                (
                    "cta_label",
                    models.CharField(
                        default="詳しく見る",
                        max_length=40,
                        verbose_name="CTAラベル",
                    ),
                ),
                (
                    "is_active",
                    models.BooleanField(
                        db_index=True,
                        default=False,
                        help_text="OFF のあいだはどの掲載場所にも出さない。",
                        verbose_name="公開中",
                    ),
                ),
                (
                    "starts_at",
                    models.DateTimeField(db_index=True, verbose_name="掲載開始"),
                ),
                (
                    "ends_at",
                    models.DateTimeField(db_index=True, verbose_name="掲載終了"),
                ),
                (
                    "priority",
                    models.PositiveSmallIntegerField(
                        default=100,
                        help_text="小さいほど優先。同掲載場所で複数あるときの並び。",
                        verbose_name="優先度",
                    ),
                ),
                (
                    "admin_notes",
                    models.TextField(
                        blank=True,
                        default="",
                        help_text="ユーザーには表示しない。",
                        verbose_name="内部メモ",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "スポンサー広告",
                "verbose_name_plural": "スポンサー広告",
                "ordering": ["priority", "pk"],
            },
        ),
        migrations.CreateModel(
            name="SponsoredAdPlacement",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "placement",
                    models.CharField(
                        choices=[
                            ("home_feed", "ホームフィード"),
                            ("discover_featured", "見つける・おすすめサービス"),
                            ("flea_banner", "フリマバナー（将来）"),
                            ("courses_feed", "授業フィード（将来）"),
                            ("timetable", "時間割（将来）"),
                        ],
                        db_index=True,
                        max_length=32,
                        verbose_name="掲載場所",
                    ),
                ),
                (
                    "is_enabled",
                    models.BooleanField(
                        db_index=True,
                        default=True,
                        verbose_name="この枠で有効",
                    ),
                ),
                (
                    "impression_count",
                    models.PositiveIntegerField(default=0, verbose_name="表示回数"),
                ),
                (
                    "click_count",
                    models.PositiveIntegerField(default=0, verbose_name="クリック数"),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "ad",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="placements",
                        to="app.sponsoredad",
                        verbose_name="広告",
                    ),
                ),
            ],
            options={
                "verbose_name": "スポンサー広告の掲載枠",
                "verbose_name_plural": "スポンサー広告の掲載枠",
            },
        ),
        migrations.AddIndex(
            model_name="sponsoredad",
            index=models.Index(
                fields=["is_active", "starts_at", "ends_at"],
                name="app_sponsor_is_acti_78e015_idx",
            ),
        ),
        migrations.AddConstraint(
            model_name="sponsoredad",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("kind__in", ["internal_promotion", "sponsored"])
                ),
                name="app_sponsor_ad_kind_valid",
            ),
        ),
        migrations.AddConstraint(
            model_name="sponsoredad",
            constraint=models.CheckConstraint(
                condition=models.Q(("ends_at__gt", models.F("starts_at"))),
                name="app_sponsor_ad_ends_after_starts",
            ),
        ),
        migrations.AddIndex(
            model_name="sponsoredadplacement",
            index=models.Index(
                fields=["placement", "is_enabled"],
                name="app_sponsor_placeme_2b75f7_idx",
            ),
        ),
        migrations.AddConstraint(
            model_name="sponsoredadplacement",
            constraint=models.UniqueConstraint(
                fields=("ad", "placement"),
                name="uniq_sponsor_ad_placement",
            ),
        ),
        migrations.AddConstraint(
            model_name="sponsoredadplacement",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    (
                        "placement__in",
                        [
                            "home_feed",
                            "discover_featured",
                            "flea_banner",
                            "courses_feed",
                            "timetable",
                        ],
                    )
                ),
                name="app_sponsor_ad_placement_valid",
            ),
        ),
    ]
