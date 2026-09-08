from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = (
        "既存ユーザーを明示操作で管理者へ昇格する復旧用コマンド。"
        "起動時には実行しない。"
        " --email 必須。"
        " --promote で is_staff / is_superuser を付与。"
        " --activate で is_active=True。"
        " ユーザー作成とパスワード変更はしない"
        "（createsuperuser / changepassword を使う）。"
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--email",
            help="対象ユーザーのメールアドレス（必須）",
        )
        parser.add_argument(
            "--promote",
            action="store_true",
            help="is_staff と is_superuser を True にする",
        )
        parser.add_argument(
            "--activate",
            action="store_true",
            help="is_active を True にする。--promote だけでは再有効化しない",
        )

    def handle(self, *args, **options):
        email = (options.get("email") or "").strip().lower()
        promote = bool(options.get("promote"))
        activate = bool(options.get("activate"))

        if not email:
            raise CommandError("--email を指定してください。")

        User = get_user_model()
        user = User.objects.filter(email__iexact=email).first()
        if user is None:
            raise CommandError(
                f"メールアドレス {email} のユーザーが見つかりません。"
                " このコマンドはユーザーを作成しません。"
                " 新規管理者は createsuperuser を使ってください。"
            )

        update_fields = []
        if promote:
            if not user.is_staff:
                user.is_staff = True
                update_fields.append("is_staff")
            if not user.is_superuser:
                user.is_superuser = True
                update_fields.append("is_superuser")
        if activate:
            if not user.is_active:
                user.is_active = True
                update_fields.append("is_active")

        if update_fields:
            user.save(update_fields=update_fields)

        self.stdout.write(
            f"email={user.email} is_staff={user.is_staff} "
            f"is_superuser={user.is_superuser} is_active={user.is_active}"
        )
        if not promote and not activate:
            self.stdout.write(
                "権限は変更していません。"
                " 昇格するには --promote、再有効化には --activate を指定してください。"
            )
            return

        if update_fields:
            self.stdout.write(
                self.style.SUCCESS(f"更新しました: {', '.join(update_fields)}")
            )
        else:
            self.stdout.write("変更はありません（既に指定の権限です）。")
