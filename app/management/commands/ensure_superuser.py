from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

# Render デプロイ時に未作成なら自動生成（プライベートリポジトリ向け）
SUPERUSER_EMAIL = "tomok11keda@toki.waseda.com"
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

        user = User.objects.create_superuser(
            email=email,
            password=SUPERUSER_PASSWORD,
            is_active=True,
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"スーパーユーザーを作成しました（username={user.username}, email={email}）。"
            )
        )
