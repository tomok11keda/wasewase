# 通常タイムライン投稿の一度きりの一斉プッシュ。スレッド偽装はしない。

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("app", "0079_organization_event_image"),
    ]

    operations = [
        migrations.AddField(
            model_name="pushcampaign",
            name="timeline_post",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="push_campaigns",
                to="app.timelinepost",
            ),
        ),
        migrations.AddField(
            model_name="pushcampaign",
            name="timeline_post_id_snapshot",
            field=models.PositiveIntegerField(
                blank=True,
                null=True,
                verbose_name="タイムライン投稿ID",
            ),
        ),
        migrations.AlterField(
            model_name="pushcampaign",
            name="thread_id_snapshot",
            field=models.PositiveIntegerField(
                blank=True,
                null=True,
                verbose_name="スレッドID",
            ),
        ),
        migrations.AlterField(
            model_name="pushcampaign",
            name="community_slug",
            field=models.SlugField(
                blank=True,
                default="",
                max_length=80,
                verbose_name="コミュニティslug",
            ),
        ),
    ]
