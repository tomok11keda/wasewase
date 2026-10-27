from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from app.account_deletion_services import delete_user_account, user_is_superuser
from app.chat_schema_services import ensure_chatroom_group_chat_schema
from app.organization_services import (
    LastOrganizationOwnerError,
    organizations_left_without_owner_if_users_deleted,
)


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
        parser.add_argument(
            "--allow-unpublished-organizations",
            action="store_true",
            help="最後の代表管理者でも、団体を非公開にして削除する",
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

        if user_is_superuser(user):
            raise CommandError(
                "Refusing to delete a superuser. Demote the account first."
            )

        self.stdout.write("ChatRoom 系スキーマ修復を実行します...")
        ensure_chatroom_group_chat_schema()
        self.stdout.write(self.style.SUCCESS("スキーマ修復完了"))

        orphaned = organizations_left_without_owner_if_users_deleted([user.pk])
        allow_unpublish = bool(options.get("allow_unpublished_organizations"))
        if orphaned:
            names = "、".join(
                (organization.name or organization.slug) for organization in orphaned
            )
            self.stdout.write(
                self.style.WARNING(
                    f"最後の代表管理者です。削除すると次の団体は非公開になります: {names}"
                )
            )
            if not allow_unpublish:
                raise CommandError(
                    "団体を非公開にして削除する場合は "
                    "--allow-unpublished-organizations を指定してください。"
                )

        if dry_run:
            self.stdout.write(self.style.WARNING("dry-run のため削除は実行しません。"))
            return

        try:
            delete_user_account(
                user,
                allow_orphaning_organizations=allow_unpublish,
            )
        except LastOrganizationOwnerError as exc:
            raise CommandError(str(exc)) from exc

        if User.objects.filter(pk=user.pk).exists():
            raise CommandError(f"削除後も user_id={user.pk} が残っています。")

        self.stdout.write(self.style.SUCCESS(f"user_id={user.pk} を削除しました。"))
