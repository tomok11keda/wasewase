from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("app", "0068_retention_popular_post_push"),
    ]

    operations = [
        migrations.AlterField(
            model_name="timelinepost",
            name="author",
            field=models.ForeignKey(
                blank=True,
                help_text="操作した個人User。団体投稿でも公開表示には使わない。",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="timeline_posts",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="timelinepost",
            name="organization",
            field=models.ForeignKey(
                blank=True,
                help_text="設定時は団体名義投稿。null は個人投稿。団体削除では投稿を残すため PROTECT。",
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="timeline_posts",
                to="app.organization",
                verbose_name="投稿主体の団体",
            ),
        ),
    ]
