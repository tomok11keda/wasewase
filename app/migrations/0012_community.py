from django.db import migrations, models
from django.utils import timezone


def seed_communities(apps, schema_editor):
    Community = apps.get_model("app", "Community")
    now = timezone.now()
    seeds = [
        {
            "slug": "commerce",
            "name": "商学部板",
            "description": "商学部の履修・ゼミ・キャリアの話題",
            "category": "faculty",
            "faculty": "商学部",
            "latest_thread_title": "2年生おすすめの経営系科目は？",
            "latest_thread_preview": "来学期の履修登録前に相談したいです。英語科目とのバランスも…",
            "sort_order": 10,
        },
        {
            "slug": "law",
            "name": "法学部板",
            "description": "法学部の授業・司法試験・学習法",
            "category": "faculty",
            "faculty": "法学部",
            "latest_thread_title": "憲法のレポート構成について",
            "latest_thread_preview": "判例の読み方がまだ慣れなくて、構成案を見てほしいです。",
            "sort_order": 20,
        },
        {
            "slug": "polisci",
            "name": "政治経済学部板",
            "description": "政経の授業・ゼミ・インターン情報",
            "category": "faculty",
            "faculty": "政治経済学部",
            "latest_thread_title": "ゼミ配属の雰囲気を教えてください",
            "latest_thread_preview": "志望ゼミを絞り込み中です。面接で聞かれがちなことを知りたいです。",
            "sort_order": 30,
        },
        {
            "slug": "science-tech",
            "name": "理工系板",
            "description": "基幹・創造・先進理工の履修と研究室",
            "category": "faculty",
            "faculty": "基幹理工学部",
            "latest_thread_title": "線形代数の復習方法",
            "latest_thread_preview": "中間の点数が微妙でした。おすすめの問題集ありますか？",
            "sort_order": 40,
        },
        {
            "slug": "thesis",
            "name": "卒論・レポート相談板",
            "description": "卒論・レポートのテーマ選びと進め方",
            "category": "general",
            "faculty": "",
            "latest_thread_title": "卒論テーマが全然決まらない",
            "latest_thread_preview": "指導教員に何を聞けばいいかも分からず困っています…",
            "sort_order": 50,
        },
        {
            "slug": "seminar",
            "name": "ゼミ選び相談板",
            "description": "ゼミ配属・面接・先輩の体験談",
            "category": "course",
            "faculty": "",
            "latest_thread_title": "3年から研究室に入るメリット",
            "latest_thread_preview": "早期配属を考えているのですが、研究と就活の両立が不安です。",
            "sort_order": 60,
        },
        {
            "slug": "career",
            "name": "インターン・就活板",
            "description": "インターン選考・ES・面接の情報交換",
            "category": "general",
            "faculty": "",
            "latest_thread_title": "サマーインターンの選考時期",
            "latest_thread_preview": "各社の選考スケジュールを共有できると助かります。",
            "sort_order": 70,
        },
    ]
    for item in seeds:
        Community.objects.update_or_create(
            slug=item["slug"],
            defaults={
                **item,
                "latest_activity_at": now,
                "is_active": True,
            },
        )


class Migration(migrations.Migration):

    dependencies = [
        ("app", "0011_social_features"),
    ]

    operations = [
        migrations.CreateModel(
            name="Community",
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
                ("slug", models.SlugField(max_length=80, unique=True)),
                ("name", models.CharField(max_length=100)),
                ("description", models.CharField(blank=True, max_length=300)),
                (
                    "category",
                    models.CharField(
                        choices=[
                            ("faculty", "学部"),
                            ("course", "授業・ゼミ"),
                            ("general", "総合"),
                        ],
                        default="general",
                        max_length=20,
                    ),
                ),
                (
                    "faculty",
                    models.CharField(
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
                    ),
                ),
                (
                    "latest_thread_title",
                    models.CharField(blank=True, max_length=120),
                ),
                (
                    "latest_thread_preview",
                    models.CharField(blank=True, max_length=200),
                ),
                ("latest_activity_at", models.DateTimeField(blank=True, null=True)),
                ("is_active", models.BooleanField(db_index=True, default=True)),
                ("sort_order", models.PositiveIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "コミュニティ掲示板",
                "verbose_name_plural": "コミュニティ掲示板",
                "ordering": ["sort_order", "name"],
            },
        ),
        migrations.RunPython(seed_communities, migrations.RunPython.noop),
    ]
