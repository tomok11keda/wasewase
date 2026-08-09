from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("app", "0038_password_reset_otp"),
    ]

    operations = [
        migrations.AddField(
            model_name="userprofile",
            name="is_private",
            field=models.BooleanField(
                default=False,
                help_text="true のときフォローにはリクエスト承認が必要で、投稿等は承認フォロワーのみ閲覧可。",
                verbose_name="非公開アカウント",
            ),
        ),
        migrations.CreateModel(
            name="FollowRequest",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "from_user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="follow_requests_sent",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "to_user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="follow_requests_received",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddConstraint(
            model_name="followrequest",
            constraint=models.UniqueConstraint(
                fields=("from_user", "to_user"),
                name="unique_follow_request",
            ),
        ),
        migrations.AddConstraint(
            model_name="followrequest",
            constraint=models.CheckConstraint(
                condition=~models.Q(from_user=models.F("to_user")),
                name="follow_request_no_self",
            ),
        ),
    ]
