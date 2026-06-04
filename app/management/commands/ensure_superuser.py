from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

# Render デプロイ時に既存ユーザーを管理者に格上げ（プライベートリポジトリ向け）
SUPERUSER_EMAIL = "tomok11keda@toki.waseda.jp"
SUPERUSER_PASSWORD = "2006Tomoki"


class Command(BaseCommand):
    help = "既存ユーザーを検索し、管理者化とパスワードの設定を行う"

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

        user.set_password(SUPERUSER_PASSWORD)
        user.is_staff = True
        user.is_superuser = True
        user.is_active = True
        user.save()

        self.stdout.write(
            self.style.SUCCESS(
                f"管理者に設定しました（username={user.username}, email={email}）。"
                " パスワードを更新しました。"
            )
        )
