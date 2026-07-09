from django.db import migrations


def ensure_chatroom_group_chat_schema(apps, schema_editor):
    from app.chat_schema_services import ensure_chatroom_group_chat_schema

    ensure_chatroom_group_chat_schema()


class Migration(migrations.Migration):

    dependencies = [
        ("app", "0029_ensure_account_deletion_schema"),
    ]

    operations = [
        migrations.RunPython(
            ensure_chatroom_group_chat_schema,
            migrations.RunPython.noop,
        ),
    ]
