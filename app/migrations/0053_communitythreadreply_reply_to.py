# Generated manually for community reply_to nesting.

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("app", "0052_otp_failed_attempts"),
    ]

    operations = [
        migrations.AddField(
            model_name="communitythreadreply",
            name="reply_to",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="child_replies",
                to="app.communitythreadreply",
                verbose_name="返信先",
            ),
        ),
    ]
