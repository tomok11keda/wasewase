from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("app", "0013_communitythread"),
    ]

    operations = [
        migrations.CreateModel(
            name="CommunityThreadReply",
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
                ("body", models.TextField(max_length=2000)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("is_removed", models.BooleanField(db_index=True, default=False)),
                (
                    "author",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="community_thread_replies",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "thread",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="replies",
                        to="app.communitythread",
                    ),
                ),
            ],
            options={
                "verbose_name": "コミュニティスレッド返信",
                "verbose_name_plural": "コミュニティスレッド返信",
                "ordering": ["created_at"],
            },
        ),
    ]
