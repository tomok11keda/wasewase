from django.db import migrations


def ensure_userprofile_is_timetable_public_column(apps, schema_editor):
    """0031 適用済みでも is_timetable_public 列が無い本番 DB を修復する。"""
    UserProfile = apps.get_model("app", "UserProfile")
    table = UserProfile._meta.db_table
    with schema_editor.connection.cursor() as cursor:
        columns = {
            column.name
            for column in schema_editor.connection.introspection.get_table_description(
                cursor, table
            )
        }
    if "is_timetable_public" in columns:
        return
    field = UserProfile._meta.get_field("is_timetable_public")
    schema_editor.add_field(UserProfile, field)


class Migration(migrations.Migration):

    dependencies = [
        ("app", "0031_userprofile_is_timetable_public"),
    ]

    operations = [
        migrations.RunPython(
            ensure_userprofile_is_timetable_public_column,
            migrations.RunPython.noop,
        ),
    ]
