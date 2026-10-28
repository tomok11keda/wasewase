from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("app", "0078_organization_event_signup_and_chat_event"),
    ]

    operations = [
        migrations.AddField(
            model_name="organizationevent",
            name="image",
            field=models.ImageField(
                blank=True,
                help_text="任意。通常投稿と同じストレージ・検証を使う。",
                null=True,
                upload_to="event_images/",
                verbose_name="イベント画像",
            ),
        ),
    ]
