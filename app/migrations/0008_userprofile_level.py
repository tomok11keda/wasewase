from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("app", "0007_timeline_like"),
    ]

    operations = [
        migrations.AddField(
            model_name="userprofile",
            name="level_score",
            field=models.PositiveIntegerField(default=0, verbose_name="レベルスコア"),
        ),
        migrations.AddField(
            model_name="userprofile",
            name="level",
            field=models.PositiveIntegerField(default=1, verbose_name="レベル"),
        ),
    ]
