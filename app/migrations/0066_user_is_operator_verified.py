from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("app", "0065_community_is_official"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="is_operator_verified",
            field=models.BooleanField(
                default=False,
                help_text=(
                    "WASEWASE運営が認証したアカウントとして表示します。"
                    "メール認証、学生認証、大学公認を意味しません。"
                ),
                verbose_name="運営認証バッジ",
            ),
        ),
    ]
