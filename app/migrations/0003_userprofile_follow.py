# Generated manually for profile and follow features

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("app", "0002_stripe_connect_fields"),
    ]

    operations = [
        migrations.RenameField(
            model_name="userprofile",
            old_name="faculty",
            new_name="department",
        ),
        migrations.AddField(
            model_name="userprofile",
            name="name",
            field=models.CharField(blank=True, max_length=80, verbose_name="名前"),
        ),
        migrations.AddField(
            model_name="userprofile",
            name="bio",
            field=models.TextField(blank=True, verbose_name="概要"),
        ),
        migrations.AddField(
            model_name="userprofile",
            name="grade",
            field=models.CharField(
                blank=True,
                choices=[
                    ("", "未設定"),
                    ("1年", "1年"),
                    ("2年", "2年"),
                    ("3年", "3年"),
                    ("4年", "4年"),
                    ("院1年", "院1年"),
                    ("院2年", "院2年"),
                    ("その他", "その他"),
                ],
                max_length=20,
                verbose_name="学年",
            ),
        ),
        migrations.AlterField(
            model_name="userprofile",
            name="department",
            field=models.CharField(
                blank=True,
                choices=[
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
                    ("その他", "その他"),
                ],
                max_length=50,
                verbose_name="学部",
            ),
        ),
        migrations.CreateModel(
            name="Follow",
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
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "follower",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="following",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "following",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="followers",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddConstraint(
            model_name="follow",
            constraint=models.UniqueConstraint(
                fields=("follower", "following"),
                name="unique_follow_relationship",
            ),
        ),
    ]
