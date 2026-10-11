"""運営コミュニティスレッド一斉プッシュ。既存 1:1 通知を壊さないこと。"""

from __future__ import annotations

from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from .broadcast_push_services import (
    BroadcastPushError,
    community_thread_push_link,
    execute_community_thread_push,
    load_broadcast_recipient_users,
    preview_broadcast_audience,
    user_allows_broadcast_push,
)
from .community_services import notify_community_reply, seed_communities
from .models import (
    Community,
    CommunityThread,
    CommunityThreadReply,
    DevicePushToken,
    Notification,
    PushCampaign,
    PushCampaignRecipient,
    UserProfile,
)
from .push_services import (
    PushDeliveryOutcome,
    PushDeliveryResult,
    reset_firebase_app_for_tests,
)

User = get_user_model()


def _profile(user, *, department: str) -> UserProfile:
    profile, _created = UserProfile.objects.get_or_create(user=user)
    profile.department = department
    profile.save(update_fields=["department"])
    return profile


def _ios(user, token: str) -> DevicePushToken:
    return DevicePushToken.objects.create(
        user=user, token=token, platform=DevicePushToken.Platform.IOS
    )


class CommunityThreadBroadcastPushTests(TestCase):
    def setUp(self):
        reset_firebase_app_for_tests()
        seed_communities()
        self.community = Community.objects.filter(is_active=True).first()
        self.actor = User.objects.create_user(
            email="ops-actor@waseda.jp",
            password="test-pass-12345",
            is_staff=True,
        )
        self.student = User.objects.create_user(
            email="student@waseda.jp",
            password="test-pass-12345",
        )
        _profile(self.student, department="商学部")
        _ios(self.student, "fcm-student-ios-token")
        self.thread = CommunityThread.objects.create(
            community=self.community,
            author=self.student,
            title="運営お知らせ",
            body="スレッド本文",
        )

    def tearDown(self):
        reset_firebase_app_for_tests()

    def _excluded_users(self):
        alumni = User.objects.create_user(
            email="alumni@waseda.jp", password="test-pass-12345"
        )
        _profile(alumni, department="卒業生")
        _ios(alumni, "fcm-alumni-ios")

        affiliated = User.objects.create_user(
            email="highschool@waseda.jp", password="test-pass-12345"
        )
        _profile(affiliated, department="附属・系属校")
        _ios(affiliated, "fcm-affiliated-ios")

        other = User.objects.create_user(
            email="other@waseda.jp", password="test-pass-12345"
        )
        _profile(other, department="その他")
        _ios(other, "fcm-other-ios")

        blank = User.objects.create_user(
            email="blank@waseda.jp", password="test-pass-12345"
        )
        _profile(blank, department="")
        _ios(blank, "fcm-blank-ios")

        no_profile = User.objects.create_user(
            email="noprof@waseda.jp", password="test-pass-12345"
        )
        _ios(no_profile, "fcm-noprof-ios")

        android_only = User.objects.create_user(
            email="android@waseda.jp", password="test-pass-12345"
        )
        _profile(android_only, department="法学部")
        DevicePushToken.objects.create(
            user=android_only,
            token="fcm-android-only",
            platform=DevicePushToken.Platform.ANDROID,
        )

        no_token = User.objects.create_user(
            email="notoken@waseda.jp", password="test-pass-12345"
        )
        _profile(no_token, department="法学部")

        apns = User.objects.create_user(
            email="apns@waseda.jp", password="test-pass-12345"
        )
        _profile(apns, department="法学部")
        DevicePushToken.objects.create(
            user=apns,
            token="a" * 64,
            platform=DevicePushToken.Platform.IOS,
        )

        test_local = User.objects.create_user(
            email="test1@waseda.jp", password="test-pass-12345"
        )
        _profile(test_local, department="法学部")
        _ios(test_local, "fcm-test-local")

        gmail = User.objects.create_user(
            email="student@gmail.com", password="test-pass-12345"
        )
        _profile(gmail, department="法学部")
        _ios(gmail, "fcm-gmail")

        staff_student = User.objects.create_user(
            email="ops-student@waseda.jp",
            password="test-pass-12345",
            is_staff=True,
        )
        _profile(staff_student, department="商学部")
        _ios(staff_student, "fcm-staff")

        return {
            "alumni": alumni,
            "affiliated": affiliated,
            "other": other,
            "blank": blank,
            "no_profile": no_profile,
            "android_only": android_only,
            "no_token": no_token,
            "apns": apns,
            "test_local": test_local,
            "gmail": gmail,
            "staff_student": staff_student,
        }

    def test_audience_includes_only_strict_university_ios(self):
        excluded = self._excluded_users()
        recipients = load_broadcast_recipient_users()
        ids = {user.pk for user in recipients}
        self.assertIn(self.student.pk, ids)
        for key, user in excluded.items():
            self.assertNotIn(user.pk, ids, key)

    def test_preview_counts_do_not_create_rows(self):
        self._excluded_users()
        preview = preview_broadcast_audience()
        self.assertEqual(preview["eligible_users"], 1)
        self.assertGreaterEqual(preview["ios_tokens"], 1)
        self.assertGreaterEqual(preview["staff_excluded"], 1)
        self.assertEqual(PushCampaign.objects.count(), 0)
        self.assertEqual(Notification.objects.count(), 0)

    def test_dry_run_command_does_not_send_or_persist(self):
        out = StringIO()
        call_command(
            "send_community_thread_push",
            "--thread-id",
            str(self.thread.pk),
            "--title",
            "注目の投稿",
            "--body",
            "詳しく見る",
            "--campaign-key",
            "spotlight-dry",
            stdout=out,
        )
        text = out.getvalue()
        self.assertIn("mode=dry-run", text)
        self.assertIn("eligible_users=1", text)
        self.assertIn(community_thread_push_link(self.thread), text)
        self.assertEqual(PushCampaign.objects.count(), 0)
        self.assertEqual(Notification.objects.count(), 0)

    def test_send_without_confirm_broadcast_is_rejected(self):
        with self.assertRaises(CommandError):
            call_command(
                "send_community_thread_push",
                "--thread-id",
                str(self.thread.pk),
                "--title",
                "注目の投稿",
                "--body",
                "詳しく見る",
                "--campaign-key",
                "spotlight-live",
                "--send",
                "--actor-email",
                self.actor.email,
            )
        self.assertEqual(PushCampaign.objects.count(), 0)

    @override_settings(PUSH_NOTIFICATIONS_ENABLED=True)
    @patch("app.broadcast_push_services.deliver_push_to_user")
    def test_command_test_send_requires_send_flag_and_actor(self, mock_deliver):
        mock_deliver.return_value = PushDeliveryResult(
            PushDeliveryOutcome.SENT, success_count=1, reason="ok"
        )
        _ios(self.actor, "fcm-actor-command-ios")
        out = StringIO()
        call_command(
            "send_community_thread_push",
            "--thread-id",
            str(self.thread.pk),
            "--title",
            "テスト配信",
            "--body",
            "自分の端末確認",
            "--campaign-key",
            "spotlight-cmd-test",
            "--send",
            "--test-email",
            self.actor.email,
            "--actor-email",
            self.actor.email,
            stdout=out,
        )
        text = out.getvalue()
        self.assertIn("mode=send", text)
        self.assertIn("audience=test", text)
        self.assertIn("sent=1", text)
        self.assertEqual(Notification.objects.count(), 0)
        self.assertEqual(mock_deliver.call_count, 1)

    def test_send_requires_staff_actor(self):
        with self.assertRaises(CommandError):
            call_command(
                "send_community_thread_push",
                "--thread-id",
                str(self.thread.pk),
                "--title",
                "注目の投稿",
                "--body",
                "詳しく見る",
                "--campaign-key",
                "spotlight-actor",
                "--send",
                "--test-email",
                self.student.email,
                "--actor-email",
                self.student.email,
            )

    @override_settings(PUSH_NOTIFICATIONS_ENABLED=True)
    @patch("app.broadcast_push_services.deliver_push_to_user")
    def test_test_mode_sends_only_to_named_user(self, mock_deliver):
        extra = User.objects.create_user(
            email="other-student@waseda.jp", password="test-pass-12345"
        )
        _profile(extra, department="法学部")
        _ios(extra, "fcm-extra-ios")
        mock_deliver.return_value = PushDeliveryResult(
            PushDeliveryOutcome.SENT, success_count=1, reason="ok"
        )
        # Staff actor may receive test push even though staff is excluded from broadcast.
        _ios(self.actor, "fcm-actor-ios")
        result = execute_community_thread_push(
            thread=self.thread,
            title="テスト配信",
            body="自分の端末確認",
            campaign_key="spotlight-test-me",
            actor=self.actor,
            test_user=self.actor,
        )
        self.assertEqual(result["eligible_users"], 1)
        self.assertEqual(mock_deliver.call_count, 1)
        self.assertEqual(mock_deliver.call_args.args[0].pk, self.actor.pk)
        self.assertEqual(
            mock_deliver.call_args.kwargs["link"],
            community_thread_push_link(self.thread),
        )
        self.assertEqual(Notification.objects.count(), 0)
        campaign = PushCampaign.objects.get(campaign_key="spotlight-test-me")
        self.assertEqual(campaign.mode, PushCampaign.Mode.TEST)
        self.assertEqual(campaign.recipients.count(), 1)

    @override_settings(PUSH_NOTIFICATIONS_ENABLED=True)
    @patch("app.broadcast_push_services.deliver_push_to_user")
    def test_broadcast_does_not_create_in_app_notifications(self, mock_deliver):
        mock_deliver.return_value = PushDeliveryResult(
            PushDeliveryOutcome.SENT, success_count=1, reason="ok"
        )
        execute_community_thread_push(
            thread=self.thread,
            title="注目の投稿",
            body="詳しく見る",
            campaign_key="spotlight-87",
            actor=self.actor,
        )
        self.assertEqual(Notification.objects.count(), 0)
        self.assertEqual(
            PushCampaignRecipient.objects.get(
                campaign__campaign_key="spotlight-87"
            ).status,
            PushCampaignRecipient.Status.SENT,
        )

    @override_settings(PUSH_NOTIFICATIONS_ENABLED=True)
    @patch("app.broadcast_push_services.deliver_push_to_user")
    def test_same_campaign_key_does_not_resend(self, mock_deliver):
        mock_deliver.return_value = PushDeliveryResult(
            PushDeliveryOutcome.SENT, success_count=1, reason="ok"
        )
        execute_community_thread_push(
            thread=self.thread,
            title="注目の投稿",
            body="詳しく見る",
            campaign_key="spotlight-once",
            actor=self.actor,
        )
        execute_community_thread_push(
            thread=self.thread,
            title="注目の投稿",
            body="詳しく見る",
            campaign_key="spotlight-once",
            actor=self.actor,
        )
        self.assertEqual(mock_deliver.call_count, 1)
        self.assertEqual(PushCampaign.objects.filter(campaign_key="spotlight-once").count(), 1)
        self.assertEqual(
            PushCampaignRecipient.objects.filter(
                campaign__campaign_key="spotlight-once"
            ).count(),
            1,
        )

    @override_settings(PUSH_NOTIFICATIONS_ENABLED=True)
    @patch("app.broadcast_push_services.deliver_push_to_user")
    def test_timeout_is_unknown_and_not_retried(self, mock_deliver):
        mock_deliver.return_value = PushDeliveryResult(
            PushDeliveryOutcome.UNKNOWN, reason="timeout"
        )
        execute_community_thread_push(
            thread=self.thread,
            title="注目の投稿",
            body="詳しく見る",
            campaign_key="spotlight-timeout",
            actor=self.actor,
        )
        recipient = PushCampaignRecipient.objects.get(
            campaign__campaign_key="spotlight-timeout"
        )
        self.assertEqual(recipient.status, PushCampaignRecipient.Status.UNKNOWN)
        execute_community_thread_push(
            thread=self.thread,
            title="注目の投稿",
            body="詳しく見る",
            campaign_key="spotlight-timeout",
            actor=self.actor,
        )
        self.assertEqual(mock_deliver.call_count, 1)
        recipient.refresh_from_db()
        self.assertEqual(recipient.status, PushCampaignRecipient.Status.UNKNOWN)

    @override_settings(PUSH_NOTIFICATIONS_ENABLED=True)
    @patch("app.broadcast_push_services.deliver_push_to_user")
    def test_interrupted_sending_becomes_unknown_not_retried(self, mock_deliver):
        mock_deliver.return_value = PushDeliveryResult(
            PushDeliveryOutcome.SENT, success_count=1, reason="ok"
        )
        campaign = PushCampaign.objects.create(
            campaign_key="spotlight-crash",
            thread=self.thread,
            thread_id_snapshot=self.thread.pk,
            community_slug=self.community.slug,
            title="注目の投稿",
            body="詳しく見る",
            link=community_thread_push_link(self.thread),
            mode=PushCampaign.Mode.BROADCAST,
            created_by=self.actor,
        )
        PushCampaignRecipient.objects.create(
            campaign=campaign,
            user=self.student,
            status=PushCampaignRecipient.Status.SENDING,
        )
        execute_community_thread_push(
            thread=self.thread,
            title="注目の投稿",
            body="詳しく見る",
            campaign_key="spotlight-crash",
            actor=self.actor,
        )
        mock_deliver.assert_not_called()
        recipient = campaign.recipients.get(user=self.student)
        self.assertEqual(recipient.status, PushCampaignRecipient.Status.UNKNOWN)
        self.assertEqual(recipient.reason, "interrupted")

    @override_settings(PUSH_NOTIFICATIONS_ENABLED=True)
    @patch("app.broadcast_push_services.deliver_push_to_user")
    def test_failed_can_be_retried_on_same_campaign_key(self, mock_deliver):
        mock_deliver.side_effect = [
            PushDeliveryResult(PushDeliveryOutcome.FAILED, reason="firebase_unavailable"),
            PushDeliveryResult(PushDeliveryOutcome.SENT, success_count=1, reason="ok"),
        ]
        execute_community_thread_push(
            thread=self.thread,
            title="注目の投稿",
            body="詳しく見る",
            campaign_key="spotlight-retry-failed",
            actor=self.actor,
        )
        recipient = PushCampaignRecipient.objects.get(
            campaign__campaign_key="spotlight-retry-failed"
        )
        self.assertEqual(recipient.status, PushCampaignRecipient.Status.FAILED)
        execute_community_thread_push(
            thread=self.thread,
            title="注目の投稿",
            body="詳しく見る",
            campaign_key="spotlight-retry-failed",
            actor=self.actor,
        )
        recipient.refresh_from_db()
        self.assertEqual(recipient.status, PushCampaignRecipient.Status.SENT)
        self.assertEqual(mock_deliver.call_count, 2)

    def test_claim_is_single_winner(self):
        from .broadcast_push_services import claim_recipient

        campaign = PushCampaign.objects.create(
            campaign_key="spotlight-claim",
            thread=self.thread,
            thread_id_snapshot=self.thread.pk,
            community_slug=self.community.slug,
            title="注目の投稿",
            body="詳しく見る",
            link=community_thread_push_link(self.thread),
            mode=PushCampaign.Mode.BROADCAST,
            created_by=self.actor,
        )
        recipient = PushCampaignRecipient.objects.create(
            campaign=campaign, user=self.student
        )
        self.assertTrue(claim_recipient(recipient))
        self.assertFalse(claim_recipient(recipient))

    def test_community_reply_still_creates_in_app_notification(self):
        reply = CommunityThreadReply.objects.create(
            thread=self.thread,
            author=self.actor,
            body="返信です",
        )
        with patch("app.push_services.notify_user_push", return_value=0):
            notify_community_reply(reply=reply, thread=self.thread)
        self.assertEqual(Notification.objects.filter(recipient=self.student).count(), 1)
        self.assertEqual(PushCampaign.objects.count(), 0)

    def test_wrong_mode_reuse_is_rejected(self):
        PushCampaign.objects.create(
            campaign_key="spotlight-mode",
            thread=self.thread,
            thread_id_snapshot=self.thread.pk,
            community_slug=self.community.slug,
            title="注目の投稿",
            body="詳しく見る",
            link=community_thread_push_link(self.thread),
            mode=PushCampaign.Mode.BROADCAST,
            created_by=self.actor,
        )
        with self.assertRaises(BroadcastPushError):
            execute_community_thread_push(
                thread=self.thread,
                title="注目の投稿",
                body="詳しく見る",
                campaign_key="spotlight-mode",
                actor=self.actor,
                test_user=self.student,
            )

    def test_broadcast_opt_out_hook(self):
        def fake_allows(user):
            if getattr(user, "pk", None) == self.student.pk:
                return False
            return user_allows_broadcast_push(user)

        with patch(
            "app.broadcast_push_services.user_allows_broadcast_push",
            side_effect=fake_allows,
        ):
            self.assertEqual(load_broadcast_recipient_users(), [])
        self.assertEqual(
            [user.pk for user in load_broadcast_recipient_users()],
            [self.student.pk],
        )

    def test_subdomain_waseda_email_is_included(self):
        ruri = User.objects.create_user(
            email="lab@ruri.waseda.jp", password="test-pass-12345"
        )
        _profile(ruri, department="基幹理工学部")
        _ios(ruri, "fcm-ruri-ios")
        ids = {user.pk for user in load_broadcast_recipient_users()}
        self.assertIn(ruri.pk, ids)
        self.assertIn(self.student.pk, ids)
