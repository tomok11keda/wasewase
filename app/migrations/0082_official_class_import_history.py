import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("app", "0081_official_course_master"),
    ]

    operations = [
        migrations.CreateModel(
            name="OfficialClassImportBatch",
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
                ("source_path", models.CharField(max_length=500, verbose_name="CSVパス")),
                (
                    "source_sha256",
                    models.CharField(blank=True, max_length=64, verbose_name="CSV SHA256"),
                ),
                ("dry_run", models.BooleanField(default=True, verbose_name="ドライラン")),
                (
                    "publication_status",
                    models.CharField(
                        default="research_only",
                        max_length=32,
                        verbose_name="適用公開状態",
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("dry_run", "ドライラン"),
                            ("committed", "コミット済"),
                            ("failed", "失敗"),
                        ],
                        db_index=True,
                        default="dry_run",
                        max_length=16,
                        verbose_name="状態",
                    ),
                ),
                ("total_rows", models.PositiveIntegerField(default=0)),
                ("created_count", models.PositiveIntegerField(default=0)),
                ("updated_count", models.PositiveIntegerField(default=0)),
                ("skipped_duplicate_count", models.PositiveIntegerField(default=0)),
                ("rejected_count", models.PositiveIntegerField(default=0)),
                ("summary_json", models.TextField(blank=True, verbose_name="サマリJSON")),
                ("error_message", models.TextField(blank=True, verbose_name="エラー")),
                ("started_at", models.DateTimeField(auto_now_add=True)),
                ("finished_at", models.DateTimeField(blank=True, null=True)),
            ],
            options={
                "verbose_name": "公式CSVインポート履歴",
                "verbose_name_plural": "公式CSVインポート履歴",
                "ordering": ["-started_at"],
            },
        ),
        migrations.CreateModel(
            name="OfficialClassImportRow",
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
                ("line_no", models.PositiveIntegerField(verbose_name="行番号")),
                (
                    "action",
                    models.CharField(
                        choices=[
                            ("create", "作成"),
                            ("update", "更新"),
                            ("skip_duplicate_in_file", "ファイル内重複スキップ"),
                            ("reject", "却下"),
                            ("unchanged", "変更なし"),
                        ],
                        max_length=32,
                        verbose_name="アクション",
                    ),
                ),
                (
                    "provisional_identity",
                    models.CharField(
                        blank=True, max_length=64, verbose_name="暫定識別子"
                    ),
                ),
                (
                    "title",
                    models.CharField(blank=True, max_length=200, verbose_name="科目名"),
                ),
                (
                    "reasons",
                    models.CharField(blank=True, max_length=500, verbose_name="理由"),
                ),
            ],
            options={
                "verbose_name": "公式CSVインポート行",
                "verbose_name_plural": "公式CSVインポート行",
                "ordering": ["batch_id", "line_no"],
            },
        ),
        migrations.AddField(
            model_name="officialclassimportbatch",
            name="started_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="official_class_import_batches",
                to=settings.AUTH_USER_MODEL,
                verbose_name="実行者",
            ),
        ),
        migrations.AddField(
            model_name="officialclassimportrow",
            name="batch",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="rows",
                to="app.officialclassimportbatch",
                verbose_name="バッチ",
            ),
        ),
        migrations.AddField(
            model_name="officialclassimportrow",
            name="official_class",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="import_rows",
                to="app.officialclass",
                verbose_name="公式クラス",
            ),
        ),
        migrations.AddIndex(
            model_name="officialclassimportrow",
            index=models.Index(
                fields=["batch", "action"], name="app_officia_batch_i_ef35d7_idx"
            ),
        ),
    ]
