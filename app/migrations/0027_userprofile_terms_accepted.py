from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("app", "0026_dm_group_chat"),
    ]

    operations = [
        migrations.AddField(
            model_name="userprofile",
            name="terms_accepted",
            field=models.BooleanField(
                default=False,
                help_text="新規登録時に利用規約・プライバシーポリシーへ同意したか。",
                verbose_name="利用規約への同意",
            ),
        ),
    ]
