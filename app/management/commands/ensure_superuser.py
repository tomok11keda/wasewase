import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

# 既存ユーザーを管理者に格上げ（パスワードは環境変数があるときだけ更新）
SUPERUSER_EMAIL = (
    os.environ.get("WASE_SUPERUSER_EMAIL", "tomok11keda@toki.waseda.jp")
    .strip()
    .lower()
)
SUPERUSER_PASSWORD = os.environ.get("WASE_SUPERUSER_PASSWORD", "").strip()


class Command(BaseCommand):
    help = "既存ユーザーを検索し、管理者化する（パスワードは env 指定時のみ更新）"

    def handle(self, *args, **options):
        email = SUPERUSER_EMAIL
        User = get_user_model()

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            self.stderr.write(
                f"メールアドレス {email} のユーザーが見つかりません。"
                " 先にアプリへ登録してから再デプロイしてください。"
            )
            return

        user.is_staff = True
        user.is_superuser = True
        user.is_active = True
        update_fields = ["is_staff", "is_superuser", "is_active"]

        if SUPERUSER_PASSWORD:
            user.set_password(SUPERUSER_PASSWORD)
            update_fields.append("password")
            user.save(update_fields=update_fields)
            self.stdout.write(
                self.style.SUCCESS(
                    f"管理者に設定しました（username={user.username}, email={email}）。"
                    " パスワードを更新しました。"
                )
            )
            return

        user.save(update_fields=update_fields)
        self.stdout.write(
            self.style.SUCCESS(
                f"管理者に設定しました（username={user.username}, email={email}）。"
                " パスワードは変更していません"
                "（WASE_SUPERUSER_PASSWORD 未設定）。"
            )
        )
