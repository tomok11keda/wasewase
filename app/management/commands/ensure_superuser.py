import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "環境変数に基づき、未作成ならスーパーユーザーを1件だけ作成する"

    def handle(self, *args, **options):
        username = os.environ.get("DJANGO_SUPERUSER_USERNAME", "admin").strip()
        email = (
            os.environ.get("DJANGO_SUPERUSER_EMAIL", "tomoki.2006@icloud.com")
            .strip()
            .lower()
        )
        password = os.environ.get("DJANGO_SUPERUSER_PASSWORD", "").strip()

        if not password:
            self.stdout.write(
                "DJANGO_SUPERUSER_PASSWORD 未設定のため、"
                "スーパーユーザー作成をスキップします。"
            )
            return

        if not email:
            self.stderr.write("DJANGO_SUPERUSER_EMAIL が空です。")
            return

        User = get_user_model()

        if User.objects.filter(email=email).exists():
            self.stdout.write(
                f"スーパーユーザーは既に存在します（email={email}）。"
            )
            return

        if User.objects.filter(username=username).exists():
            self.stdout.write(
                f"ユーザー名「{username}」は既に使用中のため作成をスキップします。"
            )
            return

        User.objects.create_superuser(
            email=email,
            password=password,
            username=username,
            is_active=True,
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"スーパーユーザーを作成しました（username={username}, email={email}）。"
            )
        )
