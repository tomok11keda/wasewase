from django.db import migrations, models


class Migration(migrations.Migration):
    """Per-post org visibility. Existing rows stay unlisted (not public)."""

    dependencies = [
        ("app", "0073_organization_event_lottery"),
    ]

    operations = [
        migrations.AddField(
            model_name="timelinepost",
            name="organization_visibility",
            field=models.CharField(
                choices=[
                    ("public", "公開"),
                    ("draft", "下書き"),
                    ("unlisted", "非公開"),
                ],
                db_default="unlisted",
                default="unlisted",
                help_text=(
                    "個人投稿では無視する。既存団体投稿は unlisted のまま一般公開しない。"
                    "public は一般タイムライン・検索・団体プロフィールに出す。"
                    "draft は管理者のみ。"
                ),
                max_length=16,
                verbose_name="団体投稿の公開状態",
            ),
        ),
        migrations.AddIndex(
            model_name="timelinepost",
            index=models.Index(
                fields=["organization", "organization_visibility"],
                name="app_tlpost_org_vis_idx",
            ),
        ),
    ]
