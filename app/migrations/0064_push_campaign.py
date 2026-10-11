# 運営コミュニティスレッド一斉プッシュのキャンペーン監査ログ。

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("app", "0063_comment_parent_comment"),
    ]

    operations = [
        migrations.CreateModel(
            name="PushCampaign",
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
                    "campaign_key",
                    models.CharField(
                        max_length=80, unique=True, verbose_name="キャンペーンキー"
                    ),
                ),
                (
                    "thread_id_snapshot",
                    models.PositiveIntegerField(verbose_name="スレッドID"),
                ),
                (
                    "community_slug",
                    models.SlugField(max_length=80, verbose_name="コミュニティslug"),
                ),
                (
                    "title",
                    models.CharField(max_length=80, verbose_name="通知タイトル"),
                ),
                (
                    "body",
                    models.CharField(max_length=200, verbose_name="通知本文"),
                ),
                (
                    "link",
                    models.CharField(max_length=255, verbose_name="ディープリンク"),
                ),
                (
                    "mode",
                    models.CharField(
                        choices=[
                            ("test", "テスト端末"),
                            ("broadcast", "一斉配信"),
                        ],
                        max_length=16,
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("ready", "準備済み"),
                            ("sending", "送信中"),
                            ("completed", "完了"),
                        ],
                        db_index=True,
                        default="ready",
                        max_length=16,
                    ),
                ),
                ("eligible_user_count", models.PositiveIntegerField(default=0)),
                ("token_count", models.PositiveIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("finished_at", models.DateTimeField(blank=True, null=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="created_push_campaigns",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "thread",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="push_campaigns",
                        to="app.communitythread",
                    ),
                ),
            ],
            options={
                "verbose_name": "プッシュキャンペーン",
                "verbose_name_plural": "プッシュキャンペーン",
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="PushCampaignRecipient",
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
                            ("pending", "未送信"),
                            ("sending", "送信中"),
                            ("sent", "送信済み"),
                            ("failed", "失敗"),
                            ("unknown", "結果不明"),
                        ],
                        db_index=True,
                        default="pending",
                        max_length=16,
                    ),
                ),
                ("success_count", models.PositiveIntegerField(default=0)),
                ("reason", models.CharField(blank=True, max_length=64)),
                ("claimed_at", models.DateTimeField(blank=True, null=True)),
                ("finished_at", models.DateTimeField(blank=True, null=True)),
                (
                    "campaign",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="recipients",
                        to="app.pushcampaign",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="push_campaign_receipts",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "プッシュキャンペーン送信対象",
                "verbose_name_plural": "プッシュキャンペーン送信対象",
            },
        ),
        migrations.AddConstraint(
            model_name="pushcampaignrecipient",
            constraint=models.UniqueConstraint(
                fields=("campaign", "user"),
                name="app_pushcampaignrecipient_campaign_user_uniq",
            ),
        ),
        migrations.AddIndex(
            model_name="pushcampaignrecipient",
            index=models.Index(
                fields=["campaign", "status"],
                name="app_push_rcpt_camp_status_idx",
            ),
        ),
    ]
