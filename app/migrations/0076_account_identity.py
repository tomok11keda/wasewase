from django.db import migrations, models
import django.db.models.deletion


def blank_emails_to_null(apps, schema_editor):
    User = apps.get_model("app", "User")
    User.objects.filter(email="").update(email=None)


class Migration(migrations.Migration):
    dependencies = [
        ("app", "0075_profilelink"),
    ]

    operations = [
        migrations.CreateModel(
            name="AccountIdentity",
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
            ],
            options={
                "verbose_name": "アカウント同一性",
                "verbose_name_plural": "アカウント同一性",
            },
        ),
        # PostgreSQL UNIQUE allows multiple NULLs, so sub-profiles can share
        # email=NULL while existing non-null emails stay unique.
        migrations.AlterField(
            model_name="user",
            name="email",
            field=models.EmailField(
                blank=True,
                max_length=254,
                null=True,
                unique=True,
                verbose_name="メールアドレス",
            ),
        ),
        migrations.RunPython(blank_emails_to_null, migrations.RunPython.noop),
        migrations.AddField(
            model_name="user",
            name="identity",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="users",
                to="app.accountidentity",
                verbose_name="アカウント同一性",
            ),
        ),
    ]
