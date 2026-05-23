from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("app", "0003_userprofile_follow"),
    ]

    operations = [
        migrations.AlterField(
            model_name="timelinepost",
            name="course_name",
            field=models.CharField(
                blank=True, max_length=120, null=True, verbose_name="授業名"
            ),
        ),
        migrations.AlterField(
            model_name="timelinepost",
            name="professor_name",
            field=models.CharField(
                blank=True, max_length=120, null=True, verbose_name="教授名"
            ),
        ),
        migrations.AlterField(
            model_name="coursethread",
            name="course_name",
            field=models.CharField(
                blank=True, max_length=120, null=True, verbose_name="授業名"
            ),
        ),
        migrations.AlterField(
            model_name="coursethread",
            name="professor_name",
            field=models.CharField(
                blank=True, max_length=120, null=True, verbose_name="教授名"
            ),
        ),
    ]
