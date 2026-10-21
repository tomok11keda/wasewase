import django.db.models.deletion
import django.db.models.functions.text
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("app", "0066_user_is_operator_verified"),
    ]

    operations = [
        migrations.CreateModel(
            name="Organization",
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
                ("name", models.CharField(max_length=100, verbose_name="団体名")),
                (
                    "slug",
                    models.SlugField(
                        help_text="URL 等で使う一意な識別子。公開後は原則変更しません。",
                        max_length=80,
                        unique=True,
                        verbose_name="識別子",
                    ),
                ),
                ("description", models.TextField(blank=True, verbose_name="団体説明")),
                (
                    "avatar",
                    models.ImageField(
                        blank=True,
                        null=True,
                        upload_to="organization_avatars/",
                        verbose_name="団体アイコン",
                    ),
                ),
                (
                    "category",
                    models.CharField(
                        choices=[
                            ("circle", "サークル"),
                            ("student_group", "学生団体"),
                            ("committee", "委員会・実行委員会"),
                            ("project", "プロジェクト"),
                            ("other", "その他"),
                        ],
                        db_index=True,
                        default="other",
                        max_length=20,
                        verbose_name="カテゴリ",
                    ),
                ),
                (
                    "instagram_url",
                    models.URLField(
                        blank=True, default="", verbose_name="Instagram URL"
                    ),
                ),
                (
                    "website_url",
                    models.URLField(
                        blank=True, default="", verbose_name="Webサイト URL"
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("draft", "下書き"),
                            ("active", "利用可能"),
                            ("suspended", "利用停止"),
                        ],
                        db_index=True,
                        default="draft",
                        help_text="draft=未公開の作成途中、active=利用可能、suspended=利用停止。",
                        max_length=16,
                        verbose_name="状態",
                    ),
                ),
                (
                    "is_listed",
                    models.BooleanField(
                        db_index=True,
                        default=False,
                        help_text="false のときは一覧・検索に出しません。status とは独立です。",
                        verbose_name="一覧・検索に表示する",
                    ),
                ),
                (
                    "is_verified",
                    models.BooleanField(
                        db_index=True,
                        default=False,
                        help_text=(
                            "WASEWASE運営が確認した学生団体として扱います。"
                            "個人アカウントの運営認証バッジ、コミュニティ掲示板の公式認証、"
                            "大学公認を意味しません。"
                        ),
                        verbose_name="運営確認済み団体",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "学生団体",
                "verbose_name_plural": "学生団体",
                "ordering": ["name"],
            },
        ),
        migrations.CreateModel(
            name="OrganizationMember",
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
                    "role",
                    models.CharField(
                        choices=[
                            ("owner", "代表管理者"),
                            ("admin", "管理者"),
                            ("member", "メンバー"),
                        ],
                        db_index=True,
                        default="admin",
                        max_length=16,
                        verbose_name="役割",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="memberships",
                        to="app.organization",
                        verbose_name="団体",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        help_text="個人アカウント。退会時は所属行のみ消え、団体本体は残します。",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="organization_memberships",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="ユーザー",
                    ),
                ),
            ],
            options={
                "verbose_name": "学生団体メンバー",
                "verbose_name_plural": "学生団体メンバー",
                "ordering": ["created_at", "pk"],
            },
        ),
        migrations.AddIndex(
            model_name="organization",
            index=models.Index(
                fields=["status", "is_listed"],
                name="app_organiz_status_9a8428_idx",
            ),
        ),
        migrations.AddConstraint(
            model_name="organization",
            constraint=models.UniqueConstraint(
                django.db.models.functions.text.Lower("slug"),
                name="app_organization_slug_lower_uniq",
            ),
        ),
        migrations.AddConstraint(
            model_name="organization",
            constraint=models.CheckConstraint(
                condition=models.Q(status__in=["draft", "active", "suspended"]),
                name="app_organization_status_valid",
            ),
        ),
        migrations.AddConstraint(
            model_name="organizationmember",
            constraint=models.UniqueConstraint(
                fields=("organization", "user"),
                name="uniq_organization_member_user",
            ),
        ),
        migrations.AddConstraint(
            model_name="organizationmember",
            constraint=models.CheckConstraint(
                condition=models.Q(role__in=["owner", "admin", "member"]),
                name="app_organization_member_role_valid",
            ),
        ),
    ]
