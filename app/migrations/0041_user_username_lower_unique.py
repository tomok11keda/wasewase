"""Ensure every user has a unique public handle; add case-insensitive uniqueness."""

from django.db import migrations, models
from django.db.models.functions import Lower


def _ensure_unique_handles(apps, schema_editor):
    """
    Existing users already have User.username handles (often user_{pk}).
    Deduplicate any case-insensitive collisions without changing user PKs or emails.
    """
    User = apps.get_model("app", "User")
    used_lower: set[str] = set()
    for user in User.objects.all().order_by("pk"):
        candidate = (user.username or "").strip() or f"user_{user.pk}"
        if candidate.lower() in used_lower:
            n = 1
            while True:
                trial = f"user_{user.pk}" if n == 1 else f"user_{user.pk}_{n}"
                if trial.lower() not in used_lower:
                    candidate = trial
                    break
                n += 1
        if user.username != candidate:
            user.username = candidate
            user.save(update_fields=["username"])
        used_lower.add(candidate.lower())


def _noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("app", "0040_timelinepost_view_count"),
    ]

    operations = [
        migrations.RunPython(_ensure_unique_handles, _noop_reverse),
        migrations.AddConstraint(
            model_name="user",
            constraint=models.UniqueConstraint(
                Lower("username"),
                name="app_user_username_lower_uniq",
            ),
        ),
    ]
