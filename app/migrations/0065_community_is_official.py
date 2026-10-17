from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("app", "0064_push_campaign"),
    ]

    operations = [
        migrations.AddField(
            model_name="community",
            name="is_official",
            field=models.BooleanField(
                default=False,
                help_text="WASEWASE運営が認証したコミュニティとして表示します。大学公認を意味しません。",
                verbose_name="公式コミュニティ",
            ),
        ),
    ]
