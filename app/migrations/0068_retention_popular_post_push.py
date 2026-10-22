from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("app", "0067_organization_and_membership"),
    ]

    operations = [
        migrations.AddField(
            model_name="userprofile",
            name="last_seen_at",
            field=models.DateTimeField(
                blank=True,
                db_index=True,
                help_text="アプリ利用を観測した時刻。最大1時間に1回更新。User.last_login とは独立。",
                null=True,
                verbose_name="最終利用日時",
            ),
        ),
        migrations.CreateModel(
            name="RetentionPushSend",
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
                        choices=[("popular_post", "人気投稿")],
                        db_index=True,
                        default="popular_post",
                        max_length=32,
                        verbose_name="種類",
                    ),
                ),
                (
                    "object_id",
                    models.CharField(
                        blank=True,
                        default="",
                        help_text="popular_post では TimelinePost.pk。",
                        max_length=64,
                        verbose_name="対象ID",
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("sending", "送信中"),
                            ("sent", "送信済み"),
                            ("failed", "失敗"),
                            ("unknown", "結果不明"),
                        ],
                        db_index=True,
                        default="sending",
                        max_length=16,
                    ),
                ),
                (
                    "local_date",
                    models.DateField(
                        db_index=True, verbose_name="送信日（Asia/Tokyo）"
                    ),
                ),
                ("success_count", models.PositiveIntegerField(default=0)),
                ("reason", models.CharField(blank=True, max_length=64)),
                (
                    "link",
                    models.CharField(
                        blank=True, max_length=255, verbose_name="ディープリンク"
                    ),
                ),
                ("sent_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="retention_push_sends",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="ユーザー",
                    ),
                ),
            ],
            options={
                "verbose_name": "Retentionプッシュ送信",
                "verbose_name_plural": "Retentionプッシュ送信",
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="retentionpushsend",
            index=models.Index(
                fields=["user", "created_at"],
                name="app_rps_user_created_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="retentionpushsend",
            index=models.Index(
                fields=["user", "kind", "object_id"],
                name="app_rps_user_kind_obj_idx",
            ),
        ),
    ]
