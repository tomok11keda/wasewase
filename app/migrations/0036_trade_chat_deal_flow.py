# Generated manually for trade chat unification

from django.db import migrations, models
import django.db.models.deletion


def forwards_status(apps, schema_editor):
    Product = apps.get_model("app", "Product")
    Product.objects.filter(status="trading").update(status="pending")
    Product.objects.filter(status="sold_out").update(status="sold")


def backwards_status(apps, schema_editor):
    Product = apps.get_model("app", "Product")
    Product.objects.filter(status="pending").update(status="trading")
    Product.objects.filter(status="sold").update(status="sold_out")


class Migration(migrations.Migration):

    dependencies = [
        ("app", "0035_product_handover_campus"),
    ]

    operations = [
        migrations.AddField(
            model_name="chatroom",
            name="deal_status",
            field=models.CharField(
                choices=[
                    ("negotiating", "交渉中"),
                    ("confirmed", "取引確定"),
                    ("closed", "終了"),
                ],
                db_index=True,
                default="negotiating",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="message",
            name="is_system",
            field=models.BooleanField(db_index=True, default=False),
        ),
        migrations.AlterField(
            model_name="message",
            name="sender",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="chat_messages",
                to="app.user",
            ),
        ),
        migrations.AlterField(
            model_name="product",
            name="status",
            field=models.CharField(
                choices=[
                    ("available", "出品中"),
                    ("pending", "取引中"),
                    ("sold", "売り切れ"),
                ],
                default="available",
                max_length=20,
            ),
        ),
        migrations.RunPython(forwards_status, backwards_status),
    ]
