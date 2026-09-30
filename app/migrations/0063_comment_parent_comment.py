# Timeline comment threading: parent_comment + author tombstone.

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("app", "0062_product_timeline_share_post"),
    ]

    operations = [
        migrations.AddField(
            model_name="comment",
            name="parent_comment",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="replies",
                to="app.comment",
                verbose_name="親コメント",
            ),
        ),
        migrations.AddField(
            model_name="comment",
            name="is_author_deleted",
            field=models.BooleanField(
                db_index=True,
                default=False,
                verbose_name="投稿者削除",
            ),
        ),
        migrations.AddIndex(
            model_name="comment",
            index=models.Index(
                fields=["timeline_post", "parent_comment", "created_at"],
                name="app_comment_thread_idx",
            ),
        ),
    ]
