from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("app", "0017_drop_orphan_timelinepost_god_count"),
    ]

    operations = [
        migrations.AlterField(
            model_name="timelinepost",
            name="like_count",
            field=models.PositiveIntegerField(db_default=0, default=0),
        ),
    ]
