from django.db import migrations, models


class Migration(migrations.Migration):
    """Add cancelled to ChatRoomInvitation.status choices.

    SQLite/Postgres columns are already varchar without a CHECK constraint,
    so existing pending/accepted/declined rows are unchanged. cancelled is
    only written by recruiting-chat admin cancel, not group DM.
    """

    dependencies = [
        ("app", "0070_organization_recruiting_chat"),
    ]

    operations = [
        migrations.AlterField(
            model_name="chatroominvitation",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending", "招待中"),
                    ("accepted", "参加済み"),
                    ("declined", "辞退"),
                    ("cancelled", "取消"),
                ],
                db_index=True,
                default="pending",
                max_length=16,
            ),
        ),
    ]
