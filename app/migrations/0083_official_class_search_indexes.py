from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("app", "0082_official_class_import_history"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="officialclass",
            index=models.Index(
                fields=["publication_status", "academic_year", "school"],
                name="app_officia_pub_ys_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="officialmeeting",
            index=models.Index(
                fields=["day_of_week", "period", "period_kind"],
                name="app_offmeet_slot_idx",
            ),
        ),
    ]
