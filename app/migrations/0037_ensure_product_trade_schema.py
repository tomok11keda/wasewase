from django.db import migrations


def ensure_product_trade_schema(apps, schema_editor):
    """0035/0036 適用済みでも列が無い本番 DB を修復する。"""
    from app.product_trade_schema_services import ensure_product_trade_schema as ensure

    ensure()


class Migration(migrations.Migration):

    dependencies = [
        ("app", "0036_trade_chat_deal_flow"),
    ]

    operations = [
        migrations.RunPython(
            ensure_product_trade_schema,
            migrations.RunPython.noop,
        ),
    ]
