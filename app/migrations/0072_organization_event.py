import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    """Organization recruiting events. Independent of CalendarEvent."""

    dependencies = [
        ("app", "0071_chatroominvitation_cancelled"),
    ]

    operations = [
        migrations.CreateModel(
            name="OrganizationEvent",
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
                ("title", models.CharField(max_length=120, verbose_name="イベント名")),
                (
                    "description",
                    models.TextField(blank=True, default="", verbose_name="説明"),
                ),
                (
                    "starts_at",
                    models.DateTimeField(db_index=True, verbose_name="開始日時"),
                ),
                ("ends_at", models.DateTimeField(verbose_name="終了日時")),
                ("venue_name", models.CharField(max_length=120, verbose_name="会場名")),
                (
                    "venue_address",
                    models.CharField(
                        blank=True,
                        default="",
                        max_length=200,
                        verbose_name="会場住所",
                    ),
                ),
                (
                    "registration_deadline",
                    models.DateTimeField(
                        blank=True, null=True, verbose_name="申込締切"
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("draft", "下書き"),
                            ("published", "公開"),
                            ("cancelled", "中止"),
                        ],
                        db_index=True,
                        default="draft",
                        max_length=16,
                        verbose_name="公開状態",
                    ),
                ),
                (
                    "registration_open",
                    models.BooleanField(
                        db_index=True, default=True, verbose_name="申込受付中"
                    ),
                ),
                (
                    "deleted_at",
                    models.DateTimeField(
                        blank=True,
                        db_index=True,
                        help_text="ソフト削除。公開一覧からは外す。",
                        null=True,
                        verbose_name="削除日時",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="organization_events_created",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="作成者",
                    ),
                ),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="events",
                        to="app.organization",
                        verbose_name="団体",
                    ),
                ),
            ],
            options={
                "verbose_name": "新歓イベント",
                "verbose_name_plural": "新歓イベント",
                "ordering": ["starts_at", "pk"],
            },
        ),
        migrations.CreateModel(
            name="OrganizationEventRegistration",
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
                    "status",
                    models.CharField(
                        choices=[
                            ("registered", "申込済み"),
                            ("cancelled", "取消"),
                        ],
                        db_index=True,
                        default="registered",
                        max_length=16,
                        verbose_name="申込状態",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "event",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="registrations",
                        to="app.organizationevent",
                        verbose_name="イベント",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="organization_event_registrations",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="申込者",
                    ),
                ),
            ],
            options={
                "verbose_name": "新歓イベント申込",
                "verbose_name_plural": "新歓イベント申込",
                "ordering": ["-updated_at", "-pk"],
            },
        ),
        migrations.AddIndex(
            model_name="organizationevent",
            index=models.Index(
                fields=["organization", "status", "starts_at"],
                name="app_organiz_organiz_7293db_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="organizationevent",
            index=models.Index(
                fields=["organization", "deleted_at", "starts_at"],
                name="app_organiz_organiz_d7755b_idx",
            ),
        ),
        migrations.AddConstraint(
            model_name="organizationevent",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("status__in", ["draft", "published", "cancelled"])
                ),
                name="app_org_event_status_valid",
            ),
        ),
        migrations.AddConstraint(
            model_name="organizationevent",
            constraint=models.CheckConstraint(
                condition=models.Q(("ends_at__gt", models.F("starts_at"))),
                name="app_org_event_ends_after_starts",
            ),
        ),
        migrations.AddIndex(
            model_name="organizationeventregistration",
            index=models.Index(
                fields=["event", "status"],
                name="app_organiz_event_i_ef0454_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="organizationeventregistration",
            index=models.Index(
                fields=["user", "status"],
                name="app_organiz_user_id_788fab_idx",
            ),
        ),
        migrations.AddConstraint(
            model_name="organizationeventregistration",
            constraint=models.UniqueConstraint(
                fields=("event", "user"),
                name="uniq_organization_event_registration_user",
            ),
        ),
        migrations.AddConstraint(
            model_name="organizationeventregistration",
            constraint=models.CheckConstraint(
                condition=models.Q(("status__in", ["registered", "cancelled"])),
                name="app_org_event_reg_status_valid",
            ),
        ),
    ]
