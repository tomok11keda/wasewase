from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from app.retention_push_services import (
    RetentionPushError,
    execute_popular_post_retention,
    resolve_retention_test_user,
)


class Command(BaseCommand):
    help = (
        "72時間以上アプリを開いていない学生へ、直近の人気タイムライン投稿を"
        " プッシュする。デフォルトは dry-run（送信しない）。"
        " 実送信は --send。gunicorn からは呼ばない。"
        " in-app Notification は作成しない。"
        " 自分の端末確認は --test-email または --test-user-id と --send。"
        " 72h inactive を無視するのは --ignore-inactivity（test-user 時のみ）。"
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--send",
            action="store_true",
            help="FCM 送信を実行する。未指定なら dry-run。",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="最大送信件数（安全弁）。未指定なら対象全員。test-user 時は最大1。",
        )
        parser.add_argument(
            "--test-email",
            default="",
            help="このメールのユーザー1人だけを対象にする。他ユーザーには送らない。",
        )
        parser.add_argument(
            "--test-user-id",
            type=int,
            default=None,
            help="この user id のユーザー1人だけを対象にする。他ユーザーには送らない。",
        )
        parser.add_argument(
            "--ignore-inactivity",
            action="store_true",
            help="72h last_seen 条件を無視する。--test-email / --test-user-id 必須。",
        )

    def handle(self, *args, **options):
        do_send = bool(options.get("send"))
        limit = options.get("limit")
        if limit is not None and int(limit) < 0:
            raise CommandError("--limit は 0 以上です。")

        test_email = (options.get("test_email") or "").strip()
        test_user_id = options.get("test_user_id")
        ignore_inactivity = bool(options.get("ignore_inactivity"))

        try:
            test_user = resolve_retention_test_user(
                email=test_email, user_id=test_user_id
            )
        except RetentionPushError as exc:
            raise CommandError(str(exc)) from exc

        if ignore_inactivity and test_user is None:
            raise CommandError(
                "--ignore-inactivity は --test-email または --test-user-id と"
                " 一緒にだけ使えます。"
            )

        if test_user is not None and limit is None:
            limit = 1

        try:
            result = execute_popular_post_retention(
                send=do_send,
                limit=limit,
                test_user=test_user,
                ignore_inactivity=ignore_inactivity,
            )
        except RetentionPushError as exc:
            raise CommandError(str(exc)) from exc

        preview = result["preview"]
        counts = result["counts"]
        mode = "send" if do_send else "dry-run"
        audience = result.get("audience") or "production"

        self.stdout.write(f"mode={mode} audience={audience} kind={result['kind']}")
        if test_user is not None:
            self.stdout.write(
                f"test_user_id={test_user.pk} test_email={test_user.email} "
                f"ignore_inactivity={bool(result.get('ignore_inactivity'))}"
            )
        self.stdout.write(f"title={result['title']}")
        self.stdout.write(f"body={result['body']}")
        self.stdout.write(
            "inactive_eligible_users={inactive_eligible_users} "
            "popular_candidates={popular_candidates} "
            "planned_sends={planned_sends} "
            "skipped_frequency_cap={skipped_frequency_cap} "
            "skipped_no_post={skipped_no_post}".format(**preview)
        )
        self.stdout.write(
            "sent={sent} failed={failed} unknown={unknown} "
            "skipped_cap={skipped_cap} skipped_no_post={skipped_no_post} "
            "planned={planned}".format(**counts)
        )
        self.stdout.write(
            f"in_app_notifications_created={result['in_app_notifications_created']} "
            f"deliver_function={result['deliver_function']}"
        )
        if not do_send:
            self.stdout.write(
                self.style.WARNING(
                    "dry-run のため送信していません。実送信は --send。"
                    " テスト送信は --send --test-email=... または "
                    "--send --test-user-id=..."
                )
            )
            return
        self.stdout.write(self.style.SUCCESS("retention popular post push finished"))
