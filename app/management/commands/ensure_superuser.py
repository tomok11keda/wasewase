from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

# Render デプロイ時に未作成なら自動生成（プライベートリポジトリ向け）
SUPERUSER_USERNAME = "admin"
SUPERUSER_EMAIL = "tomoki.2006@icloud.com"
SUPERUSER_PASSWORD = "2006Tomoki"


class Command(BaseCommand):
    help = "未作成ならスーパーユーザーを1件だけ作成する"

    def handle(self, *args, **options):
        email = SUPERUSER_EMAIL.strip().lower()
        User = get_user_model()

        if User.objects.filter(email=email).exists():
            self.stdout.write(
                f"スーパーユーザーは既に存在します（email={email}）。"
            )
            return

        if User.objects.filter(username=SUPERUSER_USERNAME).exists():
            self.stdout.write(
                f"ユーザー名「{SUPERUSER_USERNAME}」は既に使用中のため作成をスキップします。"
            )
            return

        User.objects.create_superuser(
            email=email,
            password=SUPERUSER_PASSWORD,
            username=SUPERUSER_USERNAME,
            is_active=True,
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"スーパーユーザーを作成しました（username={SUPERUSER_USERNAME}, email={email}）。"
            )
        )
