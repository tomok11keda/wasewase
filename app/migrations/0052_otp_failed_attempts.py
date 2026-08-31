from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("app", "0051_course_meeting"),
    ]

    operations = [
        migrations.AddField(
            model_name="signupotp",
            name="failed_attempts",
            field=models.PositiveSmallIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="passwordresetotp",
            name="failed_attempts",
            field=models.PositiveSmallIntegerField(default=0),
        ),
    ]
