from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("app", "0015_remove_god_button"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="userprofile",
            name="level",
        ),
        migrations.RemoveField(
            model_name="userprofile",
            name="level_score",
        ),
    ]
