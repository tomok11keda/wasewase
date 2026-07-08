from django.db import migrations


def ensure_dm_message_is_read_column(apps, schema_editor):
    """0024 適用済みでも is_read 列が無い本番 DB を修復する。"""
    UserDirectMessage = apps.get_model("app", "UserDirectMessage")
    table = UserDirectMessage._meta.db_table
    with schema_editor.connection.cursor() as cursor:
        columns = {
            column.name
            for column in schema_editor.connection.introspection.get_table_description(
                cursor, table
            )
        }
    if "is_read" in columns:
        return
    field = UserDirectMessage._meta.get_field("is_read")
    schema_editor.add_field(UserDirectMessage, field)


class Migration(migrations.Migration):

    dependencies = [
        ("app", "0024_userdirectmessage_is_read"),
    ]

    operations = [
        migrations.RunPython(
            ensure_dm_message_is_read_column,
            migrations.RunPython.noop,
        ),
    ]
