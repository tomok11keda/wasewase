"""本番 DB に残った god_count カラムを削除する（0015 未適用・不整合時の救済）。"""

from django.db import migrations


def _timelinepost_column_names(schema_editor):
    connection = schema_editor.connection
    table = "app_timelinepost"
    with connection.cursor() as cursor:
        return {
            column.name
            for column in connection.introspection.get_table_description(cursor, table)
        }


def drop_orphan_god_count_columns(apps, schema_editor):
    columns = _timelinepost_column_names(schema_editor)
    for column_name in ("god_count", "gad_count"):
        if column_name not in columns:
            continue
        schema_editor.execute(
            schema_editor.sql_delete_column
            % {
                "table": schema_editor.quote_name("app_timelinepost"),
                "column": schema_editor.quote_name(column_name),
            }
        )


class Migration(migrations.Migration):

    dependencies = [
        ("app", "0016_remove_userprofile_level"),
    ]

    operations = [
        migrations.RunPython(
            drop_orphan_god_count_columns,
            migrations.RunPython.noop,
        ),
    ]
