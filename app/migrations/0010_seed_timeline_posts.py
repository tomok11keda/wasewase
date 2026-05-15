from django.conf import settings
from django.db import migrations


def seed_timeline_posts(apps, schema_editor):
    TimelinePost = apps.get_model("app", "TimelinePost")
    User = apps.get_model(*settings.AUTH_USER_MODEL.split("."))

    if TimelinePost.objects.exists():
        return

    user = User.objects.order_by("pk").first()
    if not user:
        return

    samples = [
        (
            "線形代数Ⅰ",
            "山田太郎",
            "政治経済学部",
            "期末試験は第5章まで。過去問は図書館にあります。",
            2,
            3,
        ),
        (
            "憲法",
            "佐藤花子",
            "法学部",
            "レポートの引用は脚注形式で。判例は必ずページ番号まで。",
            1,
            1,
        ),
        (
            "マーケティング論",
            "鈴木一郎",
            "商学部",
            "グループワークの役割分担、今日までに決めておきましょう。",
            0,
            0,
        ),
        (
            "教育心理学",
            "田中次郎",
            "教育学部",
            "実習の持ち物：筆記用具と名札。服装は指定なし。",
            0,
            2,
        ),
    ]
    for course, prof, faculty, body, god_count, tip_total in samples:
        TimelinePost.objects.create(
            author=user,
            course_name=course,
            professor_name=prof,
            faculty=faculty,
            body=body,
            god_count=god_count,
            tip_total=tip_total,
        )


class Migration(migrations.Migration):

    dependencies = [
        ("app", "0009_alter_godbuttonuse_thread_timelinepost_and_more"),
    ]

    operations = [
        migrations.RunPython(seed_timeline_posts, migrations.RunPython.noop),
    ]
