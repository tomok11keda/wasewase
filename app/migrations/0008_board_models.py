import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def seed_threads(apps, schema_editor):
    CourseThread = apps.get_model("app", "CourseThread")
    samples = [
        ("線形代数Ⅰ", "山田太郎", "政治経済学部", "期末試験の範囲まとめ募集中"),
        ("憲法", "佐藤花子", "法学部", "レポートの引用形式について"),
        ("マーケティング論", "鈴木一郎", "商学部", "グループワークの分担相談"),
        ("教育心理学", "田中次郎", "教育学部", "実習の持ち物リスト"),
    ]
    for course, prof, faculty, desc in samples:
        CourseThread.objects.get_or_create(
            course_name=course,
            professor_name=prof,
            defaults={"faculty": faculty, "description": desc},
        )


class Migration(migrations.Migration):

    dependencies = [
        ("app", "0007_product_course_name_product_professor_name_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="CourseThread",
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
                ("course_name", models.CharField(max_length=120)),
                ("professor_name", models.CharField(blank=True, max_length=120)),
                (
                    "faculty",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("政治経済学部", "政治経済学部"),
                            ("法学部", "法学部"),
                            ("商学部", "商学部"),
                            ("教育学部", "教育学部"),
                            ("文学部", "文学部"),
                            ("文化構想学部", "文化構想学部"),
                        ],
                        max_length=50,
                    ),
                ),
                ("description", models.CharField(blank=True, max_length=300)),
                ("god_boost_count", models.PositiveIntegerField(default=0)),
                ("tip_total", models.PositiveIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("last_activity", models.DateTimeField(auto_now=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="created_threads",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"ordering": ["-god_boost_count", "-last_activity"]},
        ),
        migrations.CreateModel(
            name="ThreadPost",
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
                ("body", models.TextField(max_length=1000)),
                ("is_god_pick", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "author",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="thread_posts",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "thread",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="posts",
                        to="app.coursethread",
                    ),
                ),
            ],
            options={"ordering": ["-is_god_pick", "-created_at"]},
        ),
        migrations.CreateModel(
            name="ThreadTip",
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
                ("amount", models.PositiveIntegerField(default=1)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "thread",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="tips",
                        to="app.coursethread",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="thread_tips",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="GodButtonUse",
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
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "post",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="god_uses",
                        to="app.threadpost",
                    ),
                ),
                (
                    "thread",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="god_uses",
                        to="app.coursethread",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="god_button_uses",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.RunPython(seed_threads, migrations.RunPython.noop),
    ]
