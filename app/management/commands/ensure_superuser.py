from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

# Render デプロイ時に既存ユーザーを管理者に格上げ（プライベートリポジトリ向け）
SUPERUSER_EMAIL = "tomok11keda@toki.waseda.jp"


class Command(BaseCommand):
    help = "既存ユーザーを検索し、未設定なら is_staff / is_superuser を有効化する"

    def handle(self, *args, **options):
        email = SUPERUSER_EMAIL.strip().lower()
        User = get_user_model()

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            self.stderr.write(
                f"メールアドレス {email} のユーザーが見つかりません。"
                " 先にアプリへ登録してから再デプロイしてください。"
            )
            return

        if user.is_superuser and user.is_staff:
            self.stdout.write(
                f"既に管理者です（email={email}, username={user.username}）。"
            )
            return

        user.is_staff = True
        user.is_superuser = True
        user.is_active = True
        user.save(update_fields=["is_staff", "is_superuser", "is_active"])
        self.stdout.write(
            self.style.SUCCESS(
                f"管理者に格上げしました（username={user.username}, email={email}）。"
            )
        )
