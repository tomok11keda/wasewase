from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("app", "0039_userprofile_is_private_followrequest"),
    ]

    operations = [
        migrations.AddField(
            model_name="timelinepost",
            name="view_count",
            field=models.PositiveIntegerField(db_default=0, default=0),
        ),
    ]
