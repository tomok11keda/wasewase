# 同意の有無（terms_accepted）に加え、同意日時と規約版を記録する。
# 既存行は backfill しない。terms_accepted=True でも日時・版は空のままにする。

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("app", "0053_communitythreadreply_reply_to"),
    ]

    operations = [
        migrations.AddField(
            model_name="userprofile",
            name="terms_accepted_at",
            field=models.DateTimeField(
                blank=True,
                help_text="同意した日時。既存ユーザーで正確な日時が不明な場合は空。",
                null=True,
                verbose_name="利用規約への同意日時",
            ),
        ),
        migrations.AddField(
            model_name="userprofile",
            name="terms_version",
            field=models.CharField(
                blank=True,
                default="",
                help_text="同意した規約の版。既存ユーザーで正確な版が不明な場合は空。",
                max_length=64,
                verbose_name="同意した利用規約の版",
            ),
        ),
    ]
