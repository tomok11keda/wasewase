# Generated manually for CalendarEvent

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("app", "0043_dm_message_request"),
    ]

    operations = [
        migrations.CreateModel(
            name="CalendarEvent",
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
                ("title", models.CharField(max_length=120, verbose_name="予定名")),
                ("date", models.DateField(db_index=True, verbose_name="日付")),
                (
                    "start_time",
                    models.TimeField(
                        blank=True, null=True, verbose_name="開始時刻"
                    ),
                ),
                (
                    "end_time",
                    models.TimeField(
                        blank=True, null=True, verbose_name="終了時刻"
                    ),
                ),
                ("memo", models.TextField(blank=True, verbose_name="メモ")),
                (
                    "category",
                    models.CharField(
                        choices=[
                            ("class", "授業"),
                            ("assignment", "課題"),
                            ("exam", "テスト"),
                            ("seminar", "ゼミ"),
                            ("club", "サークル"),
                            ("other", "その他"),
                        ],
                        db_index=True,
                        default="other",
                        max_length=20,
                        verbose_name="カテゴリ",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="calendar_events",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="ユーザー",
                    ),
                ),
            ],
            options={
                "verbose_name": "カレンダー予定",
                "verbose_name_plural": "カレンダー予定",
                "ordering": ["date", "start_time", "pk"],
            },
        ),
        migrations.AddIndex(
            model_name="calendarevent",
            index=models.Index(
                fields=["user", "date"], name="app_calenda_user_id_7c8a1d_idx"
            ),
        ),
    ]
