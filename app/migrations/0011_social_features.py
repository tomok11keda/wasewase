import re

from django.db import migrations, models
import django.db.models.deletion

HANDLE_PATTERN = re.compile(r"^[a-zA-Z0-9_]{3,30}$")


def backfill_user_handles(apps, schema_editor):
    User = apps.get_model("app", "User")
    UserProfile = apps.get_model("app", "UserProfile")

    for user in User.objects.all().iterator():
        profile, _created = UserProfile.objects.get_or_create(user=user)
        old_username = user.username or ""
        if HANDLE_PATTERN.match(old_username):
            continue

        if not (profile.name or "").strip():
            profile.name = old_username
            profile.save(update_fields=["name"])

        candidate = f"user_{user.pk}"
        suffix = 0
        while (
            User.objects.filter(username=candidate).exclude(pk=user.pk).exists()
        ):
            suffix += 1
            candidate = f"user_{user.pk}_{suffix}"

        user.username = candidate
        user.save(update_fields=["username"])


class Migration(migrations.Migration):

    dependencies = [
        ("app", "0010_ugc_safety"),
    ]

    operations = [
        migrations.AddField(
            model_name="timelinepost",
            name="quoted_post",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="quotes",
                to="app.timelinepost",
                verbose_name="引用元投稿",
            ),
        ),
        migrations.RunPython(backfill_user_handles, migrations.RunPython.noop),
    ]
