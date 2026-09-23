# Generated manually for thread-local anonymous community IDs.

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def backfill_thread_participants(apps, schema_editor):
    CommunityThread = apps.get_model("app", "CommunityThread")
    CommunityThreadReply = apps.get_model("app", "CommunityThreadReply")
    CommunityThreadParticipant = apps.get_model("app", "CommunityThreadParticipant")

    replies_by_thread = {}
    for thread_id, author_id in (
        CommunityThreadReply.objects.order_by("created_at", "pk").values_list(
            "thread_id", "author_id"
        )
    ):
        replies_by_thread.setdefault(thread_id, []).append(author_id)

    rows = []
    for thread in CommunityThread.objects.order_by("pk").only("id", "author_id"):
        seen = {}
        if thread.author_id:
            rows.append(
                CommunityThreadParticipant(
                    thread_id=thread.pk,
                    user_id=thread.author_id,
                    anonymous_number=1,
                )
            )
            seen[thread.author_id] = 1
        next_n = 2
        for author_id in replies_by_thread.get(thread.pk, ()):
            if not author_id or author_id in seen:
                continue
            rows.append(
                CommunityThreadParticipant(
                    thread_id=thread.pk,
                    user_id=author_id,
                    anonymous_number=next_n,
                )
            )
            seen[author_id] = next_n
            next_n += 1
        if len(rows) >= 500:
            CommunityThreadParticipant.objects.bulk_create(
                rows, ignore_conflicts=True
            )
            rows = []
    if rows:
        CommunityThreadParticipant.objects.bulk_create(
            rows, ignore_conflicts=True
        )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("app", "0059_contentreport_community_target_types"),
    ]

    operations = [
        migrations.CreateModel(
            name="CommunityThreadParticipant",
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
                ("anonymous_number", models.PositiveIntegerField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "thread",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="participants",
                        to="app.communitythread",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="community_thread_participations",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "コミュニティスレッド参加者番号",
                "verbose_name_plural": "コミュニティスレッド参加者番号",
            },
        ),
        migrations.AddConstraint(
            model_name="communitythreadparticipant",
            constraint=models.UniqueConstraint(
                fields=("thread", "user"),
                condition=models.Q(user__isnull=False),
                name="uniq_community_thread_participant_user",
            ),
        ),
        migrations.AddConstraint(
            model_name="communitythreadparticipant",
            constraint=models.UniqueConstraint(
                fields=("thread", "anonymous_number"),
                name="uniq_community_thread_participant_number",
            ),
        ),
        migrations.RunPython(backfill_thread_participants, noop_reverse),
    ]
