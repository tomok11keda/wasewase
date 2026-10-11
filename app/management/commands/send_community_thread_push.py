from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from app.broadcast_push_services import (
    BroadcastPushError,
    community_thread_push_link,
    execute_community_thread_push,
    load_visible_thread,
    preview_broadcast_audience,
    require_staff_actor,
    validate_campaign_key,
    validate_copy,
)

User = get_user_model()


class Command(BaseCommand):
    help = (
        "運営が選んだコミュニティスレッドを、対象の早稲田大学生の iOS 端末へ"
        " プッシュする。デフォルトは dry-run（送信しない）。"
        " 本番一斉送信には --send と --confirm-broadcast が両方必要。"
        " 自分の端末確認は --send --test-email=...。"
        " in-app Notification は作成しない。"
    )

    def add_arguments(self, parser):
        parser.add_argument("--thread-id", type=int, required=True)
        parser.add_argument("--title", required=True)
        parser.add_argument("--body", required=True)
        parser.add_argument("--campaign-key", required=True)
        parser.add_argument(
            "--actor-email",
            default="",
            help="送信者（staff/superuser）。--send 時は必須。",
        )
        parser.add_argument(
            "--test-email",
            default="",
            help="このユーザーの iOS トークンだけを対象にするテストモード。",
        )
        parser.add_argument(
            "--send",
            action="store_true",
            help="FCM 送信を実行する。未指定なら dry-run。",
        )
        parser.add_argument(
            "--confirm-broadcast",
            action="store_true",
            help="大学生向け一斉送信であることを明示する。--test-email と同時指定不可。",
        )

    def handle(self, *args, **options):
        try:
            thread = load_visible_thread(int(options["thread_id"]))
            title, body = validate_copy(
                title=options.get("title") or "",
                body=options.get("body") or "",
            )
            campaign_key = validate_campaign_key(options.get("campaign_key") or "")
        except BroadcastPushError as exc:
            raise CommandError(str(exc)) from exc

        test_email = (options.get("test_email") or "").strip().lower()
        actor_email = (options.get("actor_email") or "").strip().lower()
        do_send = bool(options.get("send"))
        confirm_broadcast = bool(options.get("confirm_broadcast"))

        if test_email and confirm_broadcast:
            raise CommandError(
                "--test-email と --confirm-broadcast は同時に指定できません。"
            )

        test_user = None
        if test_email:
            test_user = User.objects.filter(email__iexact=test_email).first()
            if test_user is None:
                raise CommandError(f"テストユーザー {test_email} が見つかりません。")

        link = community_thread_push_link(thread)
        preview = preview_broadcast_audience(test_user=test_user)
        mode = "test" if test_user is not None else "broadcast"
        run_mode = "send" if do_send else "dry-run"

        self.stdout.write(f"mode={run_mode} audience={mode}")
        self.stdout.write(
            f"thread_id={thread.pk} community={thread.community.slug} "
            f"campaign_key={campaign_key}"
        )
        self.stdout.write(f"link={link}")
        self.stdout.write(f"title={title}")
        self.stdout.write(
            "eligible_users={eligible_users} ios_tokens={ios_tokens} "
            "staff_excluded={staff_excluded} "
            "not_university_faculty_excluded={not_university_faculty_excluded} "
            "test_or_non_waseda_email_excluded={test_or_non_waseda_email_excluded} "
            "no_ios_token_excluded={no_ios_token_excluded} "
            "broadcast_opt_out_excluded={broadcast_opt_out_excluded}".format(
                **preview
            )
        )

        if not do_send:
            self.stdout.write(
                self.style.WARNING(
                    "dry-run のため送信していません。"
                    " テスト送信は --send --test-email=... --actor-email=..."
                    " 本番は --send --confirm-broadcast --actor-email=..."
                )
            )
            return

        if test_user is None and not confirm_broadcast:
            raise CommandError(
                "本番一斉送信には --send に加えて --confirm-broadcast が必要です。"
                " 先に dry-run と --test-email で確認してください。"
            )

        actor = User.objects.filter(email__iexact=actor_email).first() if actor_email else None
        try:
            require_staff_actor(actor)
            result = execute_community_thread_push(
                thread=thread,
                title=title,
                body=body,
                campaign_key=campaign_key,
                actor=actor,
                test_user=test_user,
            )
        except BroadcastPushError as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(
            "sent={sent} failed={failed} unknown={unknown} "
            "claimed={claimed} skipped_locked={skipped_locked} "
            "already_terminal={already_terminal} "
            "stale_sending_to_unknown={stale_sending_to_unknown}".format(
                **result["send"]
            )
        )
        self.stdout.write(
            f"campaign_status={result['status']} "
            f"in_app_notifications_created={result['in_app_notifications_created']}"
        )
        self.stdout.write(self.style.SUCCESS("push campaign run finished"))
