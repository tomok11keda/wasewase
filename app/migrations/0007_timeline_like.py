from django.conf import settings
from django.db import migrations, models


def dedupe_timeline_likes_and_sync_counts(apps, schema_editor):
    TimelineLike = apps.get_model("app", "TimelineLike")
    TimelinePost = apps.get_model("app", "TimelinePost")

    seen = set()
    for like in TimelineLike.objects.order_by("id"):
        key = (like.timeline_post_id, like.user_id)
        if key in seen:
            like.delete()
        else:
            seen.add(key)

    for post in TimelinePost.objects.all():
        count = TimelineLike.objects.filter(timeline_post_id=post.pk).count()
        post.tip_total = count
        post.save(update_fields=["tip_total"])


class Migration(migrations.Migration):

    dependencies = [
        ("app", "0006_userdirectmessageroom_userdirectmessage"),
    ]

    operations = [
        migrations.RenameModel(
            old_name="TimelineTip",
            new_name="TimelineLike",
        ),
        migrations.RemoveField(
            model_name="timelinelike",
            name="amount",
        ),
        migrations.AlterField(
            model_name="timelinelike",
            name="timeline_post",
            field=models.ForeignKey(
                on_delete=models.deletion.CASCADE,
                related_name="likes",
                to="app.timelinepost",
            ),
        ),
        migrations.AlterField(
            model_name="timelinelike",
            name="user",
            field=models.ForeignKey(
                on_delete=models.deletion.CASCADE,
                related_name="timeline_likes",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.RunPython(
            dedupe_timeline_likes_and_sync_counts,
            migrations.RunPython.noop,
        ),
        migrations.RenameField(
            model_name="timelinepost",
            old_name="tip_total",
            new_name="like_count",
        ),
        migrations.AddConstraint(
            model_name="timelinelike",
            constraint=models.UniqueConstraint(
                fields=("timeline_post", "user"),
                name="unique_timeline_like_per_user",
            ),
        ),
    ]
