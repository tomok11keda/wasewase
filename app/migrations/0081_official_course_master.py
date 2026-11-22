import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("app", "0080_pushcampaign_timeline_post"),
    ]

    operations = [
        migrations.CreateModel(
            name="OfferingOfficialLink",
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
                (
                    "match_method",
                    models.CharField(
                        choices=[
                            ("manual", "人手"),
                            ("suggested", "候補"),
                            ("created_from_official", "公式から作成"),
                            ("exact_provisional", "暫定キー一致"),
                        ],
                        default="manual",
                        max_length=32,
                        verbose_name="対応方法",
                    ),
                ),
                ("confidence", models.FloatField(default=1.0, verbose_name="信頼度")),
                (
                    "reviewed_at",
                    models.DateTimeField(
                        blank=True, null=True, verbose_name="確認日時"
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "開講公式リンク",
                "verbose_name_plural": "開講公式リンク",
            },
        ),
        migrations.CreateModel(
            name="OfficialClass",
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
                (
                    "academic_year",
                    models.PositiveIntegerField(db_index=True, verbose_name="年度"),
                ),
                (
                    "school",
                    models.CharField(db_index=True, max_length=50, verbose_name="学部"),
                ),
                (
                    "section",
                    models.CharField(blank=True, max_length=120, verbose_name="区分"),
                ),
                ("title", models.CharField(max_length=200, verbose_name="科目名")),
                (
                    "title_normalized",
                    models.CharField(
                        blank=True,
                        db_index=True,
                        max_length=200,
                        verbose_name="正規化科目名",
                    ),
                ),
                (
                    "haibun_class_no",
                    models.CharField(
                        blank=True,
                        help_text="公開配当表のクラス列。シラバスクラスコードの代替ではない。",
                        max_length=16,
                        verbose_name="配当表クラス番号",
                    ),
                ),
                (
                    "instructor",
                    models.CharField(blank=True, max_length=200, verbose_name="担当教員"),
                ),
                (
                    "instructor_normalized",
                    models.CharField(
                        blank=True,
                        db_index=True,
                        max_length=200,
                        verbose_name="正規化教員名",
                    ),
                ),
                (
                    "semester_code",
                    models.CharField(blank=True, max_length=32, verbose_name="学期コード"),
                ),
                (
                    "semester_label",
                    models.CharField(blank=True, max_length=32, verbose_name="学期表示"),
                ),
                (
                    "credits",
                    models.CharField(blank=True, max_length=20, verbose_name="単位"),
                ),
                (
                    "modality_raw",
                    models.CharField(
                        blank=True, max_length=40, verbose_name="授業実施方法"
                    ),
                ),
                (
                    "is_cancelled",
                    models.BooleanField(default=False, verbose_name="本年度休講"),
                ),
                (
                    "subject_key",
                    models.CharField(
                        blank=True,
                        help_text="公式シラバスの科目キー。未取得なら空。推測生成禁止。",
                        max_length=32,
                        verbose_name="科目キー",
                    ),
                ),
                (
                    "syllabus_class_code",
                    models.CharField(
                        blank=True,
                        help_text="公式シラバスのクラスコード。未取得なら空。",
                        max_length=16,
                        verbose_name="シラバスクラスコード",
                    ),
                ),
                (
                    "course_code",
                    models.CharField(
                        blank=True, max_length=32, verbose_name="コースコード"
                    ),
                ),
                (
                    "provisional_identity",
                    models.CharField(
                        help_text="配当表フィールドから決定的に導出。公式キーの代替ではない。",
                        max_length=64,
                        unique=True,
                        verbose_name="暫定識別子",
                    ),
                ),
                (
                    "source_url",
                    models.URLField(blank=True, verbose_name="出典URL"),
                ),
                (
                    "source_listing_page",
                    models.URLField(blank=True, verbose_name="掲載ページ"),
                ),
                (
                    "source_extract_line",
                    models.PositiveIntegerField(default=0, verbose_name="抽出行"),
                ),
                ("source_raw_line", models.TextField(blank=True, verbose_name="元行")),
                (
                    "parse_flags",
                    models.CharField(
                        blank=True, max_length=200, verbose_name="抽出フラグ"
                    ),
                ),
                ("needs_human_review", models.BooleanField(default=False)),
                (
                    "publication_status",
                    models.CharField(
                        choices=[
                            ("research_only", "研究検証のみ"),
                            ("internal", "内部"),
                            ("public", "公開可"),
                        ],
                        db_index=True,
                        default="research_only",
                        max_length=32,
                        verbose_name="公開状態",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "公式開講クラス",
                "verbose_name_plural": "公式開講クラス",
                "ordering": [
                    "academic_year",
                    "school",
                    "title",
                    "haibun_class_no",
                    "pk",
                ],
            },
        ),
        migrations.CreateModel(
            name="OfficialMeeting",
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
                (
                    "day_of_week",
                    models.PositiveSmallIntegerField(
                        blank=True,
                        help_text="0=月 … 6=日。ODはnull可。",
                        null=True,
                        verbose_name="曜日",
                    ),
                ),
                (
                    "period",
                    models.PositiveSmallIntegerField(
                        blank=True, null=True, verbose_name="時限"
                    ),
                ),
                (
                    "period_kind",
                    models.CharField(
                        choices=[("period", "通常限"), ("od", "オンデマンド")],
                        default="period",
                        max_length=16,
                        verbose_name="時限種別",
                    ),
                ),
                (
                    "raw",
                    models.CharField(blank=True, max_length=32, verbose_name="元表記"),
                ),
                (
                    "fingerprint",
                    models.CharField(blank=True, max_length=64, verbose_name="指紋"),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "verbose_name": "公式ミーティング",
                "verbose_name_plural": "公式ミーティング",
                "ordering": ["id"],
            },
        ),
        migrations.AlterField(
            model_name="courseoffering",
            name="source",
            field=models.CharField(
                choices=[
                    ("user", "ユーザー"),
                    ("admin", "管理者"),
                    ("official", "公式マスター"),
                ],
                default="user",
                max_length=16,
                verbose_name="出典",
            ),
        ),
        migrations.AddField(
            model_name="offeringofficiallink",
            name="offering",
            field=models.OneToOneField(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="official_link",
                to="app.courseoffering",
                verbose_name="開講授業",
            ),
        ),
        migrations.AddField(
            model_name="officialclass",
            name="canonical_offering",
            field=models.ForeignKey(
                blank=True,
                help_text="新規履修・共通トークの受け皿。他Offeringの自動統合はしない。",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="official_canonical_for",
                to="app.courseoffering",
                verbose_name="正規CourseOffering",
            ),
        ),
        migrations.AddField(
            model_name="offeringofficiallink",
            name="official_class",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="offering_links",
                to="app.officialclass",
                verbose_name="公式開講クラス",
            ),
        ),
        migrations.AddField(
            model_name="officialmeeting",
            name="official_class",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="meetings",
                to="app.officialclass",
                verbose_name="公式開講クラス",
            ),
        ),
        migrations.AddIndex(
            model_name="officialclass",
            index=models.Index(
                fields=["academic_year", "school", "title_normalized"],
                name="app_officia_academi_b4e17b_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="officialclass",
            index=models.Index(
                fields=["subject_key", "syllabus_class_code"],
                name="app_officia_subject_a025df_idx",
            ),
        ),
        migrations.AddConstraint(
            model_name="officialclass",
            constraint=models.UniqueConstraint(
                condition=models.Q(
                    ("subject_key__gt", ""), ("syllabus_class_code__gt", "")
                ),
                fields=("academic_year", "subject_key", "syllabus_class_code"),
                name="uniq_official_class_syllabus_identity",
            ),
        ),
        migrations.AddIndex(
            model_name="offeringofficiallink",
            index=models.Index(
                fields=["official_class", "match_method"],
                name="app_offerin_officia_22c6d5_idx",
            ),
        ),
    ]
