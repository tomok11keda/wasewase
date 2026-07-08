from django.db import migrations


def ensure_dm_read_state_table(apps, schema_editor):
    """0022 適用済みでも既読テーブルが無い本番 DB を修復する。"""
    ReadState = apps.get_model("app", "UserDirectMessageReadState")
    table = ReadState._meta.db_table
    connection = schema_editor.connection
    with connection.cursor() as cursor:
        if table in connection.introspection.table_names(cursor):
            return
    schema_editor.create_model(ReadState)


class Migration(migrations.Migration):

    dependencies = [
        ("app", "0022_userdirectmessagereadstate"),
    ]

    operations = [
        migrations.RunPython(
            ensure_dm_read_state_table,
            migrations.RunPython.noop,
        ),
    ]
