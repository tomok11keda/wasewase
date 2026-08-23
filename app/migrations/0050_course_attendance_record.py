from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("app", "0049_course_calendar_exception"),
    ]

    operations = [
        migrations.CreateModel(
            name="CourseAttendanceRecord",
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
                ("date", models.DateField(db_index=True, verbose_name="対象日")),
                (
                    "status",
                    models.CharField(
                        choices=[("absent", "欠席")],
                        db_index=True,
                        default="absent",
                        max_length=20,
                        verbose_name="状態",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "offering",
                    models.ForeignKey(
                        help_text="その日の開催スロットに対応する Offering",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="attendance_records",
                        to="app.courseoffering",
                        verbose_name="開講授業",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="course_attendance_records",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="ユーザー",
                    ),
                ),
            ],
            options={
                "verbose_name": "授業欠席記録",
                "verbose_name_plural": "授業欠席記録",
                "ordering": ["-date", "-pk"],
            },
        ),
        migrations.AddIndex(
            model_name="courseattendancerecord",
            index=models.Index(
                fields=["user", "date"], name="app_coursea_user_id_d1c2a0_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="courseattendancerecord",
            index=models.Index(
                fields=["user", "status"], name="app_coursea_user_id_8f3e1b_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="courseattendancerecord",
            index=models.Index(
                fields=["offering", "date"], name="app_coursea_offerin_4a9c2d_idx"
            ),
        ),
        migrations.AddConstraint(
            model_name="courseattendancerecord",
            constraint=models.UniqueConstraint(
                fields=("user", "offering", "date"),
                name="unique_course_attendance_per_day",
            ),
        ),
    ]
