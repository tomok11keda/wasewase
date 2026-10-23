from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("app", "0069_timelinepost_organization"),
    ]

    operations = [
        migrations.AlterField(
            model_name="chatroom",
            name="kind",
            field=models.CharField(
                choices=[
                    ("product", "商品チャット"),
                    ("group", "グループチャット"),
                    ("course", "授業トーク"),
                    ("recruiting", "新歓チャット"),
                ],
                db_index=True,
                default="product",
                max_length=20,
            ),
        ),
        migrations.CreateModel(
            name="OrganizationRecruitingChat",
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
                ("name", models.CharField(max_length=120, verbose_name="チャット名")),
                (
                    "description",
                    models.TextField(blank=True, default="", verbose_name="説明"),
                ),
                (
                    "join_mode",
                    models.CharField(
                        choices=[("open", "自由参加"), ("approval", "承認制")],
                        db_index=True,
                        default="open",
                        max_length=16,
                        verbose_name="参加方式",
                    ),
                ),
                (
                    "listing_status",
                    models.CharField(
                        choices=[("open", "募集中"), ("closed", "募集停止")],
                        db_index=True,
                        default="open",
                        max_length=16,
                        verbose_name="募集状態",
                    ),
                ),
                (
                    "is_active",
                    models.BooleanField(
                        db_index=True,
                        default=True,
                        help_text="True の行は団体あたり1件。過去のチャットは False にして残す。",
                        verbose_name="有効な新歓チャット",
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
                        related_name="organization_recruiting_chats_created",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="作成者",
                    ),
                ),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="recruiting_chats",
                        to="app.organization",
                        verbose_name="団体",
                    ),
                ),
                (
                    "room",
                    models.OneToOneField(
                        help_text="kind=recruiting の ChatRoom。グループ／授業／商品チャットとは分離する。",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="organization_recruiting_chat",
                        to="app.chatroom",
                        verbose_name="チャットルーム",
                    ),
                ),
            ],
            options={
                "verbose_name": "新歓チャット",
                "verbose_name_plural": "新歓チャット",
                "ordering": ["-updated_at"],
            },
        ),
        migrations.CreateModel(
            name="OrganizationRecruitingChatApplication",
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
                            ("pending", "承認待ち"),
                            ("approved", "承認済み"),
                            ("rejected", "拒否"),
                            ("withdrawn", "退出・除外"),
                        ],
                        db_index=True,
                        default="pending",
                        max_length=16,
                        verbose_name="申請状態",
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(auto_now_add=True, verbose_name="申請日時"),
                ),
                (
                    "reviewed_at",
                    models.DateTimeField(
                        blank=True, null=True, verbose_name="審査日時"
                    ),
                ),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "recruiting_chat",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="applications",
                        to="app.organizationrecruitingchat",
                        verbose_name="新歓チャット",
                    ),
                ),
                (
                    "reviewed_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="recruiting_chat_reviews",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="審査者",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="recruiting_chat_applications",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="申請者",
                    ),
                ),
            ],
            options={
                "verbose_name": "新歓チャット参加申請",
                "verbose_name_plural": "新歓チャット参加申請",
                "ordering": ["-updated_at", "-pk"],
            },
        ),
        migrations.AddIndex(
            model_name="organizationrecruitingchat",
            index=models.Index(
                fields=["organization", "is_active"],
                name="app_organiz_organiz_40dd59_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="organizationrecruitingchatapplication",
            index=models.Index(
                fields=["recruiting_chat", "status"],
                name="app_organiz_recruit_839e04_idx",
            ),
        ),
        migrations.AddConstraint(
            model_name="organizationrecruitingchat",
            constraint=models.UniqueConstraint(
                condition=models.Q(is_active=True),
                fields=("organization",),
                name="uniq_org_active_recruiting_chat",
            ),
        ),
        migrations.AddConstraint(
            model_name="organizationrecruitingchat",
            constraint=models.CheckConstraint(
                condition=models.Q(join_mode__in=["open", "approval"]),
                name="app_recruiting_chat_join_mode_valid",
            ),
        ),
        migrations.AddConstraint(
            model_name="organizationrecruitingchat",
            constraint=models.CheckConstraint(
                condition=models.Q(listing_status__in=["open", "closed"]),
                name="app_recruiting_chat_listing_valid",
            ),
        ),
        migrations.AddConstraint(
            model_name="organizationrecruitingchatapplication",
            constraint=models.UniqueConstraint(
                fields=("recruiting_chat", "user"),
                name="uniq_recruiting_chat_application_user",
            ),
        ),
        migrations.AddConstraint(
            model_name="organizationrecruitingchatapplication",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    status__in=["pending", "approved", "rejected", "withdrawn"]
                ),
                name="app_recruiting_app_status_valid",
            ),
        ),
    ]
