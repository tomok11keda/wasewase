from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("app", "0023_ensure_dm_read_state_table"),
    ]

    operations = [
        migrations.AddField(
            model_name="userdirectmessage",
            name="is_read",
            field=models.BooleanField(
                default=False,
                help_text="1対1 DM では相手が既読にしたか。グループ化時は ReadReceipt 等へ移行予定。",
            ),
        ),
    ]
