from django.db import migrations


def ensure_account_deletion_schema(apps, schema_editor):
    from app.media_services import (
        ensure_timelinepost_author_nullable,
        ensure_userprofile_terms_accepted_column,
    )

    ensure_userprofile_terms_accepted_column()
    ensure_timelinepost_author_nullable()


class Migration(migrations.Migration):

    dependencies = [
        ("app", "0028_timelinepost_author_nullable"),
    ]

    operations = [
        migrations.RunPython(
            ensure_account_deletion_schema,
            migrations.RunPython.noop,
        ),
    ]
