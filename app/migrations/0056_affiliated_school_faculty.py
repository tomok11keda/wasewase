from django.db import migrations, models

FACULTY_CHOICES = [
    ("政治経済学部", "政治経済学部"),
    ("法学部", "法学部"),
    ("教育学部", "教育学部"),
    ("商学部", "商学部"),
    ("社会科学部", "社会科学部"),
    ("国際教養学部", "国際教養学部"),
    ("文化構想学部", "文化構想学部"),
    ("文学部", "文学部"),
    ("基幹理工学部", "基幹理工学部"),
    ("創造理工学部", "創造理工学部"),
    ("先進理工学部", "先進理工学部"),
    ("人間科学部", "人間科学部"),
    ("スポーツ科学部", "スポーツ科学部"),
    ("附属・系属校", "附属・系属校"),
    ("その他", "その他"),
]


class Migration(migrations.Migration):

    dependencies = [
        ("app", "0055_userprofile_onboarding"),
    ]

    operations = [
        migrations.AlterField(
            model_name="community",
            name="faculty",
            field=models.CharField(
                blank=True, choices=FACULTY_CHOICES, max_length=50
            ),
        ),
        migrations.AlterField(
            model_name="coursethread",
            name="faculty",
            field=models.CharField(
                blank=True, choices=FACULTY_CHOICES, max_length=50
            ),
        ),
        migrations.AlterField(
            model_name="product",
            name="faculty",
            field=models.CharField(
                blank=True, choices=FACULTY_CHOICES, max_length=50
            ),
        ),
        migrations.AlterField(
            model_name="timelinepost",
            name="faculty",
            field=models.CharField(
                blank=True, choices=FACULTY_CHOICES, max_length=50
            ),
        ),
        migrations.AlterField(
            model_name="userprofile",
            name="department",
            field=models.CharField(
                blank=True,
                choices=FACULTY_CHOICES,
                max_length=50,
                verbose_name="学部",
            ),
        ),
    ]
