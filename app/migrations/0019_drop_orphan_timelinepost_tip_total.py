"""本番 DB に残った tip_total カラムを削除する（0007 未適用時の救済）。"""

from django.db import migrations


def _timelinepost_column_names(schema_editor):
    connection = schema_editor.connection
    table = "app_timelinepost"
    with connection.cursor() as cursor:
        return {
            column.name
            for column in connection.introspection.get_table_description(cursor, table)
        }


def drop_orphan_tip_total_column(apps, schema_editor):
    columns = _timelinepost_column_names(schema_editor)
    if "tip_total" not in columns:
        return
    if "like_count" not in columns:
        return
    schema_editor.execute(
        schema_editor.sql_delete_column
        % {
            "table": schema_editor.quote_name("app_timelinepost"),
            "column": schema_editor.quote_name("tip_total"),
        }
    )


class Migration(migrations.Migration):

    dependencies = [
        ("app", "0018_timelinepost_like_count_db_default"),
    ]

    operations = [
        migrations.RunPython(
            drop_orphan_tip_total_column,
            migrations.RunPython.noop,
        ),
    ]
