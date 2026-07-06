from django.db import migrations


def ensure_userprofile_avatar_column(apps, schema_editor):
    """0020 適用済みでも avatar 列が無い本番 DB を修復する。"""
    UserProfile = apps.get_model("app", "UserProfile")
    table = UserProfile._meta.db_table
    with schema_editor.connection.cursor() as cursor:
        columns = {
            column.name
            for column in schema_editor.connection.introspection.get_table_description(
                cursor, table
            )
        }
    if "avatar" in columns:
        return
    field = UserProfile._meta.get_field("avatar")
    schema_editor.add_field(UserProfile, field)


class Migration(migrations.Migration):

    dependencies = [
        ("app", "0020_userprofile_avatar"),
    ]

    operations = [
        migrations.RunPython(
            ensure_userprofile_avatar_column,
            migrations.RunPython.noop,
        ),
    ]
