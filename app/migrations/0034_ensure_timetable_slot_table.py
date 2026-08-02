from django.db import migrations


def ensure_timetable_slot_table(apps, schema_editor):
    """0033 適用済みでもテーブルが無い本番 DB を修復する。"""
    from app.timetable_services import ensure_timetable_slot_table as ensure_table

    ensure_table()


class Migration(migrations.Migration):

    dependencies = [
        ("app", "0033_timetable_slot"),
    ]

    operations = [
        migrations.RunPython(
            ensure_timetable_slot_table,
            migrations.RunPython.noop,
        ),
    ]
