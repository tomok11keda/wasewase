from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("app", "0061_alumni_faculty"),
    ]

    operations = [
        migrations.AddField(
            model_name="product",
            name="timeline_share_post",
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=models.SET_NULL,
                related_name="shared_product",
                to="app.timelinepost",
                verbose_name="タイムラインシェア投稿",
            ),
        ),
    ]
