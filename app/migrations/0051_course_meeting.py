# CourseMeeting CreateModel is SeparateDatabaseAndState so production tables
# created by AppConfig.ready() ensure_* do not conflict with migrate.
# Remaining ops (AddField meeting, RunPython, offering unique) always apply to DB.

from django.db import migrations, models
import django.db.models.deletion


def create_course_meeting_if_missing(apps, schema_editor):
    Model = apps.get_model("app", "CourseMeeting")
    table = Model._meta.db_table
    existing = set(schema_editor.connection.introspection.table_names())
    if table in existing:
        return
    schema_editor.create_model(Model)


def forwards_backfill_and_merge(apps, schema_editor):
    CourseOffering = apps.get_model("app", "CourseOffering")
    CourseMeeting = apps.get_model("app", "CourseMeeting")
    TimetableSlot = apps.get_model("app", "TimetableSlot")
    CourseEnrollment = apps.get_model("app", "CourseEnrollment")
    CourseReview = apps.get_model("app", "CourseReview")
    CourseAttendanceRecord = apps.get_model("app", "CourseAttendanceRecord")
    CourseCalendarException = apps.get_model("app", "CourseCalendarException")

    # 1) Backfill one meeting per offering from denormalized schedule
    for offering in CourseOffering.objects.all().iterator():
        CourseMeeting.objects.get_or_create(
            offering_id=offering.pk,
            day_of_week=offering.day_of_week,
            period_kind=offering.period_kind,
            period=offering.period,
        )

    # 2) Link slots to meetings
    meeting_map = {
        (m.offering_id, m.day_of_week, m.period_kind, m.period): m
        for m in CourseMeeting.objects.all()
    }
    for slot in TimetableSlot.objects.exclude(offering_id=None).iterator():
        offering = CourseOffering.objects.filter(pk=slot.offering_id).first()
        if not offering:
            continue
        key = (
            offering.pk,
            offering.day_of_week,
            offering.period_kind,
            offering.period,
        )
        # Prefer meeting matching slot_key
        matched = None
        for m in CourseMeeting.objects.filter(offering_id=offering.pk):
            prefix = "od" if m.period_kind == "od" else "p"
            if slot.slot_key == f"{prefix}{m.period}-d{m.day_of_week}":
                matched = m
                break
        if matched is None:
            matched = meeting_map.get(key)
        if matched:
            TimetableSlot.objects.filter(pk=slot.pk).update(meeting_id=matched.pk)

    # 3) Merge active offerings that share identity (title/instructor/year/semester)
    groups = {}
    for offering in CourseOffering.objects.filter(status="active").order_by("pk"):
        key = (
            offering.title_normalized,
            offering.instructor_normalized,
            offering.academic_year,
            offering.semester,
        )
        groups.setdefault(key, []).append(offering)

    for _key, rows in groups.items():
        if len(rows) < 2:
            continue
        target = rows[0]
        for source in rows[1:]:
            # meetings
            for m in CourseMeeting.objects.filter(offering_id=source.pk):
                CourseMeeting.objects.get_or_create(
                    offering_id=target.pk,
                    day_of_week=m.day_of_week,
                    period_kind=m.period_kind,
                    period=m.period,
                )
            CourseMeeting.objects.filter(offering_id=source.pk).delete()

            # enrollments
            for enrollment in CourseEnrollment.objects.filter(offering_id=source.pk):
                existing = CourseEnrollment.objects.filter(
                    user_id=enrollment.user_id, offering_id=target.pk
                ).first()
                if existing:
                    if enrollment.role == "current" and existing.role != "current":
                        existing.role = "current"
                        existing.save(update_fields=["role", "updated_at"])
                    enrollment.delete()
                else:
                    enrollment.offering_id = target.pk
                    enrollment.save(update_fields=["offering_id", "updated_at"])

            # reviews
            for review in CourseReview.objects.filter(offering_id=source.pk):
                existing = CourseReview.objects.filter(
                    user_id=review.user_id, offering_id=target.pk
                ).first()
                if existing:
                    review.delete()
                else:
                    review.offering_id = target.pk
                    review.save(update_fields=["offering_id", "updated_at"])

            # attendance
            for row in CourseAttendanceRecord.objects.filter(offering_id=source.pk):
                if CourseAttendanceRecord.objects.filter(
                    user_id=row.user_id, offering_id=target.pk, date=row.date
                ).exists():
                    row.delete()
                else:
                    row.offering_id = target.pk
                    row.save(update_fields=["offering_id", "updated_at"])

            # calendar exceptions
            for row in CourseCalendarException.objects.filter(offering_id=source.pk):
                if CourseCalendarException.objects.filter(
                    user_id=row.user_id, offering_id=target.pk, date=row.date
                ).exists():
                    row.delete()
                else:
                    row.offering_id = target.pk
                    row.save(update_fields=["offering_id", "updated_at"])

            # slots
            for slot in TimetableSlot.objects.filter(offering_id=source.pk):
                conflict = (
                    TimetableSlot.objects.filter(
                        user_id=slot.user_id, slot_key=slot.slot_key
                    )
                    .exclude(pk=slot.pk)
                    .first()
                )
                if conflict and conflict.offering_id == target.pk:
                    slot.delete()
                    continue
                slot.offering_id = target.pk
                slot.name = target.title
                slot.save(update_fields=["offering_id", "name", "updated_at"])

            source.status = "merged"
            source.merged_into_id = target.pk
            source.save(update_fields=["status", "merged_into_id", "updated_at"])

        # sync primary schedule on target
        first = (
            CourseMeeting.objects.filter(offering_id=target.pk)
            .order_by("day_of_week", "period_kind", "period", "pk")
            .first()
        )
        if first:
            target.day_of_week = first.day_of_week
            target.period_kind = first.period_kind
            target.period = first.period
            target.save(
                update_fields=["day_of_week", "period_kind", "period", "updated_at"]
            )


def backwards_noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("app", "0050_course_attendance_record"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.CreateModel(
                    name="CourseMeeting",
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
                            "day_of_week",
                            models.PositiveSmallIntegerField(
                                help_text="0=月 … 5=土", verbose_name="曜日"
                            ),
                        ),
                        (
                            "period_kind",
                            models.CharField(
                                choices=[("period", "通常限"), ("od", "オンデマンド")],
                                default="period",
                                max_length=16,
                                verbose_name="時限種別",
                            ),
                        ),
                        ("period", models.PositiveSmallIntegerField(verbose_name="時限")),
                        ("created_at", models.DateTimeField(auto_now_add=True)),
                        ("updated_at", models.DateTimeField(auto_now=True)),
                        (
                            "offering",
                            models.ForeignKey(
                                on_delete=django.db.models.deletion.CASCADE,
                                related_name="meetings",
                                to="app.courseoffering",
                                verbose_name="開講授業",
                            ),
                        ),
                    ],
                    options={
                        "verbose_name": "授業ミーティング",
                        "verbose_name_plural": "授業ミーティング",
                        "ordering": ["day_of_week", "period_kind", "period", "pk"],
                    },
                ),
                migrations.AddIndex(
                    model_name="coursemeeting",
                    index=models.Index(
                        fields=["day_of_week", "period_kind", "period"],
                        name="app_coursem_day_of__7e2a1b_idx",
                    ),
                ),
                migrations.AddConstraint(
                    model_name="coursemeeting",
                    constraint=models.UniqueConstraint(
                        fields=("offering", "day_of_week", "period_kind", "period"),
                        name="unique_course_meeting_per_offering_slot",
                    ),
                ),
            ],
            database_operations=[],
        ),
        migrations.RunPython(
            create_course_meeting_if_missing,
            migrations.RunPython.noop,
        ),
        migrations.AddField(
            model_name="timetableslot",
            name="meeting",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="timetable_slots",
                to="app.coursemeeting",
                verbose_name="授業ミーティング",
            ),
        ),
        migrations.RunPython(forwards_backfill_and_merge, backwards_noop),
        migrations.RemoveConstraint(
            model_name="courseoffering",
            name="uniq_active_course_offering_identity",
        ),
        migrations.AddConstraint(
            model_name="courseoffering",
            constraint=models.UniqueConstraint(
                condition=models.Q(("status", "active")),
                fields=(
                    "title_normalized",
                    "instructor_normalized",
                    "academic_year",
                    "semester",
                ),
                name="uniq_active_course_offering_identity",
            ),
        ),
        migrations.AlterField(
            model_name="courseoffering",
            name="day_of_week",
            field=models.PositiveSmallIntegerField(
                help_text="0=月 … 5=土（代表ミーティングの非正規化）",
                verbose_name="代表曜日",
            ),
        ),
        migrations.AlterField(
            model_name="courseoffering",
            name="period",
            field=models.PositiveSmallIntegerField(verbose_name="代表時限"),
        ),
        migrations.AlterField(
            model_name="courseoffering",
            name="period_kind",
            field=models.CharField(
                choices=[("period", "通常限"), ("od", "オンデマンド")],
                default="period",
                max_length=16,
                verbose_name="代表時限種別",
            ),
        ),
    ]
