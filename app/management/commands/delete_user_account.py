from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from app.account_deletion_services import delete_user_account
from app.chat_schema_services import ensure_chatroom_group_chat_schema


class Command(BaseCommand):
    help = "指定ユーザーを退会処理で物理削除する（本番スキーマ修復込み）"

    def add_arguments(self, parser):
        parser.add_argument(
            "--email",
            help="削除対象ユーザーのメールアドレス",
        )
        parser.add_argument(
            "--user-id",
            type=int,
            help="削除対象ユーザーの ID",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="削除せず、対象ユーザーとスキーマ修復のみ確認する",
        )

    def handle(self, *args, **options):
        email = (options.get("email") or "").strip().lower()
        user_id = options.get("user_id")
        dry_run = options.get("dry_run")

        if not email and not user_id:
            raise CommandError("--email または --user-id を指定してください。")

        User = get_user_model()
        if user_id:
            user = User.objects.filter(pk=user_id).first()
            if user is None:
                raise CommandError(f"user_id={user_id} のユーザーが見つかりません。")
        else:
            user = User.objects.filter(email__iexact=email).first()
            if user is None:
                raise CommandError(f"email={email} のユーザーが見つかりません。")

        self.stdout.write(
            f"対象ユーザー: id={user.pk} email={user.email} username={user.username}"
        )

        self.stdout.write("ChatRoom 系スキーマ修復を実行します...")
        ensure_chatroom_group_chat_schema()
        self.stdout.write(self.style.SUCCESS("スキーマ修復完了"))

        if dry_run:
            self.stdout.write(self.style.WARNING("dry-run のため削除は実行しません。"))
            return

        delete_user_account(user)

        if User.objects.filter(pk=user.pk).exists():
            raise CommandError(f"削除後も user_id={user.pk} が残っています。")

        self.stdout.write(self.style.SUCCESS(f"user_id={user.pk} を削除しました。"))
