from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    """Optional organization-event lottery results. Depends on unapplied 0072."""

    dependencies = [
        ("app", "0072_organization_event"),
    ]

    operations = [
        migrations.CreateModel(
            name="OrganizationEventLottery",
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
                        choices=[("completed", "確定")],
                        db_index=True,
                        default="completed",
                        max_length=16,
                        verbose_name="状態",
                    ),
                ),
                (
                    "applicant_count",
                    models.PositiveIntegerField(verbose_name="申込者数"),
                ),
                (
                    "eligible_count",
                    models.PositiveIntegerField(verbose_name="抽選対象者数"),
                ),
                (
                    "excluded_count",
                    models.PositiveIntegerField(verbose_name="除外者数"),
                ),
                (
                    "winner_count",
                    models.PositiveIntegerField(verbose_name="当選人数"),
                ),
                (
                    "executed_at",
                    models.DateTimeField(
                        auto_now_add=True, db_index=True, verbose_name="抽選日時"
                    ),
                ),
                (
                    "shared_at",
                    models.DateTimeField(
                        blank=True, null=True, verbose_name="共有日時"
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "event",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="lottery",
                        to="app.organizationevent",
                        verbose_name="イベント",
                    ),
                ),
                (
                    "executed_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="organization_event_lotteries_executed",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="実行者",
                    ),
                ),
                (
                    "shared_message",
                    models.OneToOneField(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="organization_event_lottery_share",
                        to="app.chatmessage",
                        verbose_name="共有メッセージ",
                    ),
                ),
            ],
            options={
                "verbose_name": "新歓イベント抽選",
                "verbose_name_plural": "新歓イベント抽選",
            },
        ),
        migrations.CreateModel(
            name="OrganizationEventLotteryEntry",
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
                    "result",
                    models.CharField(
                        choices=[
                            ("selected", "当選"),
                            ("not_selected", "落選"),
                            ("excluded", "対象外"),
                        ],
                        db_index=True,
                        max_length=16,
                        verbose_name="結果",
                    ),
                ),
                (
                    "exclusion_note",
                    models.CharField(
                        blank=True,
                        default="",
                        max_length=100,
                        verbose_name="除外備考",
                    ),
                ),
                (
                    "display_name_snapshot",
                    models.CharField(
                        max_length=120, verbose_name="表示名スナップショット"
                    ),
                ),
                (
                    "username_snapshot",
                    models.CharField(
                        blank=True,
                        default="",
                        max_length=150,
                        verbose_name="ユーザー名スナップショット",
                    ),
                ),
                (
                    "avatar_url_snapshot",
                    models.CharField(
                        blank=True,
                        default="",
                        max_length=500,
                        verbose_name="アバタースナップショット",
                    ),
                ),
                (
                    "initial_snapshot",
                    models.CharField(
                        blank=True,
                        default="",
                        max_length=8,
                        verbose_name="イニシャルスナップショット",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "lottery",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="entries",
                        to="app.organizationeventlottery",
                        verbose_name="抽選",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="organization_event_lottery_entries",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="ユーザー",
                    ),
                ),
            ],
            options={
                "verbose_name": "新歓イベント抽選結果",
                "verbose_name_plural": "新歓イベント抽選結果",
            },
        ),
        migrations.AddIndex(
            model_name="organizationeventlottery",
            index=models.Index(
                fields=["executed_at"], name="app_organiz_execute_2d59f0_idx"
            ),
        ),
        migrations.AddConstraint(
            model_name="organizationeventlottery",
            constraint=models.CheckConstraint(
                condition=models.Q(("status__in", ["completed"])),
                name="app_org_event_lottery_status_valid",
            ),
        ),
        migrations.AddConstraint(
            model_name="organizationeventlottery",
            constraint=models.CheckConstraint(
                condition=models.Q(("winner_count__lte", models.F("eligible_count"))),
                name="app_org_event_lottery_winner_lte_eligible",
            ),
        ),
        migrations.AddConstraint(
            model_name="organizationeventlottery",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    excluded_count=models.F("applicant_count")
                    - models.F("eligible_count")
                ),
                name="app_org_event_lottery_excluded_matches",
            ),
        ),
        migrations.AddIndex(
            model_name="organizationeventlotteryentry",
            index=models.Index(
                fields=["lottery", "result"],
                name="app_organiz_lottery_0bbf5d_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="organizationeventlotteryentry",
            index=models.Index(
                fields=["user", "result"],
                name="app_organiz_user_id_078b1f_idx",
            ),
        ),
        migrations.AddConstraint(
            model_name="organizationeventlotteryentry",
            constraint=models.UniqueConstraint(
                condition=models.Q(("user__isnull", False)),
                fields=("lottery", "user"),
                name="uniq_organization_event_lottery_user",
            ),
        ),
        migrations.AddConstraint(
            model_name="organizationeventlotteryentry",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("result__in", ["selected", "not_selected", "excluded"])
                ),
                name="app_org_event_lottery_entry_result_valid",
            ),
        ),
    ]
