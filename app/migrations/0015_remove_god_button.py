from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("app", "0014_communitythreadreply"),
    ]

    operations = [
        migrations.DeleteModel(
            name="GodButtonUse",
        ),
        migrations.RemoveField(
            model_name="timelinepost",
            name="god_count",
        ),
        migrations.RemoveField(
            model_name="coursethread",
            name="god_boost_count",
        ),
        migrations.RemoveField(
            model_name="threadpost",
            name="is_god_pick",
        ),
        migrations.AlterModelOptions(
            name="coursethread",
            options={"ordering": ["-last_activity"]},
        ),
        migrations.AlterModelOptions(
            name="threadpost",
            options={"ordering": ["-created_at"]},
        ),
    ]
