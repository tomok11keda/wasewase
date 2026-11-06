"""通常タイムライン投稿の一度きりの一斉プッシュ。"""

from __future__ import annotations

from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.utils import timezone

from .broadcast_push_services import (
    PUSH_KIND_COMMUNITY_THREAD_BROADCAST,
    PUSH_KIND_TIMELINE_POST_BROADCAST,
    BroadcastPushError,
    execute_community_thread_push,
    execute_timeline_post_push,
    timeline_post_push_link,
)
from .community_services import seed_communities
from .models import (
    Community,
    CommunityThread,
    DevicePushToken,
    Notification,
    Organization,
    OrganizationEvent,
    PushCampaign,
    TimelinePost,
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


class TimelinePostBroadcastPushTests(TestCase):
    def setUp(self):
        reset_firebase_app_for_tests()
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
        self.other = User.objects.create_user(
            email="other-student@waseda.jp",
            password="test-pass-12345",
        )
        _profile(self.other, department="法学部")
        _ios(self.other, "fcm-other-ios-token")
        self.org = Organization.objects.create(
            name="IGNITE",
            slug="ignite",
            status=Organization.Status.ACTIVE,
            is_listed=True,
        )
        starts = timezone.now() + timedelta(days=1)
        self.event = OrganizationEvent.objects.create(
            organization=self.org,
            title="早稲田祭ステージ",
            starts_at=starts,
            ends_at=starts + timedelta(hours=2),
            venue_name="戸山キャンパス",
            status=OrganizationEvent.Status.PUBLISHED,
        )
        self.post = TimelinePost.objects.create(
            author=self.student,
            organization=self.org,
            organization_visibility=TimelinePost.OrganizationVisibility.PUBLIC,
            body="IGNITEのイベントです",
            shared_organization_event=self.event,
        )
        self.sent = PushDeliveryResult(
            PushDeliveryOutcome.SENT, success_count=1, reason="ok"
        )

    def tearDown(self):
        reset_firebase_app_for_tests()

    def test_dry_run_does_not_send_or_create_campaign(self):
        out = StringIO()
        with patch(
            "app.broadcast_push_services.deliver_push_to_user",
            return_value=self.sent,
        ) as deliver:
            call_command(
                "send_timeline_post_push",
                "--post-id",
                str(self.post.pk),
                "--title",
                "IGNITEがイベントを投稿しました！",
                "--body",
                "IGNITEの新しいイベントをチェックしてみよう！",
                "--campaign-key",
                "ignite-wasedasai-2026",
                stdout=out,
            )
        self.assertEqual(deliver.call_count, 0)
        self.assertEqual(PushCampaign.objects.count(), 0)
        self.assertEqual(Notification.objects.count(), 0)
        text = out.getvalue()
        self.assertIn(f"link=/app/posts/{self.post.pk}", text)
        self.assertIn(f"router_path=/posts/{self.post.pk}", text)
        self.assertIn("event_title=早稲田祭ステージ", text)
        self.assertIn("dry-run", text)

    def test_link_opens_timeline_post(self):
        self.assertEqual(
            timeline_post_push_link(self.post.pk),
            f"/app/posts/{self.post.pk}",
        )

    def test_test_send_reaches_only_the_named_user(self):
        with patch(
            "app.broadcast_push_services.deliver_push_to_user",
            return_value=self.sent,
        ) as deliver:
            call_command(
                "send_timeline_post_push",
                "--post-id",
                str(self.post.pk),
                "--title",
                "IGNITEがイベントを投稿しました！",
                "--body",
                "早稲田祭ステージ",
                "--campaign-key",
                "ignite-wasedasai-2026-test",
                "--actor-email",
                self.actor.email,
                "--test-email",
                self.student.email,
                "--send",
            )
        self.assertEqual(deliver.call_count, 1)
        self.assertEqual(deliver.call_args.args[0].pk, self.student.pk)
        self.assertEqual(
            deliver.call_args.kwargs["link"],
            f"/app/posts/{self.post.pk}",
        )
        self.assertEqual(
            deliver.call_args.kwargs["notification_type"],
            PUSH_KIND_TIMELINE_POST_BROADCAST,
        )
        campaign = PushCampaign.objects.get(campaign_key="ignite-wasedasai-2026-test")
        self.assertEqual(campaign.mode, PushCampaign.Mode.TEST)
        self.assertEqual(campaign.timeline_post_id_snapshot, self.post.pk)
        self.assertIsNone(campaign.thread_id_snapshot)
        self.assertEqual(campaign.recipients.count(), 1)
        self.assertEqual(Notification.objects.count(), 0)

    def test_broadcast_requires_explicit_confirmation(self):
        with patch(
            "app.broadcast_push_services.deliver_push_to_user",
            return_value=self.sent,
        ) as deliver:
            with self.assertRaises(CommandError):
                call_command(
                    "send_timeline_post_push",
                    "--post-id",
                    str(self.post.pk),
                    "--title",
                    "title",
                    "--body",
                    "body",
                    "--campaign-key",
                    "ignite-wasedasai-2026",
                    "--actor-email",
                    self.actor.email,
                    "--send",
                )
        self.assertEqual(deliver.call_count, 0)
        self.assertFalse(
            PushCampaign.objects.filter(campaign_key="ignite-wasedasai-2026").exists()
        )

    def test_same_campaign_key_does_not_send_twice(self):
        kwargs = dict(
            post=self.post,
            title="title",
            body="body",
            campaign_key="ignite-wasedasai-2026",
            actor=self.actor,
        )
        with patch(
            "app.broadcast_push_services.deliver_push_to_user",
            return_value=self.sent,
        ) as deliver:
            first = execute_timeline_post_push(**kwargs)
            second = execute_timeline_post_push(**kwargs)
        self.assertEqual(first["send"]["sent"], 2)
        self.assertEqual(deliver.call_count, 2)
        self.assertEqual(second["send"]["sent"], 0)
        self.assertEqual(second["send"]["already_terminal"], 2)
        self.assertEqual(PushCampaign.objects.count(), 1)

    def test_test_campaign_key_cannot_be_reused_for_broadcast(self):
        with patch(
            "app.broadcast_push_services.deliver_push_to_user",
            return_value=self.sent,
        ):
            execute_timeline_post_push(
                post=self.post,
                title="title",
                body="body",
                campaign_key="ignite-wasedasai-2026",
                actor=self.actor,
                test_user=self.student,
            )
            with self.assertRaises(BroadcastPushError):
                execute_timeline_post_push(
                    post=self.post,
                    title="title",
                    body="body",
                    campaign_key="ignite-wasedasai-2026",
                    actor=self.actor,
                )
        campaign = PushCampaign.objects.get()
        self.assertEqual(campaign.mode, PushCampaign.Mode.TEST)
        self.assertEqual(campaign.recipients.count(), 1)

    def test_campaign_key_cannot_target_another_post(self):
        other = TimelinePost.objects.create(
            author=self.student,
            organization=self.org,
            organization_visibility=TimelinePost.OrganizationVisibility.PUBLIC,
            body="別の投稿",
        )
        with patch(
            "app.broadcast_push_services.deliver_push_to_user",
            return_value=self.sent,
        ):
            execute_timeline_post_push(
                post=self.post,
                title="title",
                body="body",
                campaign_key="ignite-wasedasai-2026",
                actor=self.actor,
            )
            with self.assertRaises(BroadcastPushError):
                execute_timeline_post_push(
                    post=other,
                    title="title",
                    body="body",
                    campaign_key="ignite-wasedasai-2026",
                    actor=self.actor,
                )
        campaign = PushCampaign.objects.get()
        self.assertEqual(campaign.timeline_post_id_snapshot, self.post.pk)

    def test_campaign_key_cannot_reuse_a_community_thread_key(self):
        seed_communities()
        community = Community.objects.filter(is_active=True).first()
        thread = CommunityThread.objects.create(
            community=community,
            author=self.student,
            title="thread",
            body="body",
        )
        with patch(
            "app.broadcast_push_services.deliver_push_to_user",
            return_value=self.sent,
        ) as deliver:
            execute_community_thread_push(
                thread=thread,
                title="title",
                body="body",
                campaign_key="shared-key",
                actor=self.actor,
            )
            with self.assertRaises(BroadcastPushError):
                execute_timeline_post_push(
                    post=self.post,
                    title="title",
                    body="body",
                    campaign_key="shared-key",
                    actor=self.actor,
                )
        self.assertTrue(
            all(
                call.kwargs["notification_type"]
                == PUSH_KIND_COMMUNITY_THREAD_BROADCAST
                for call in deliver.call_args_list
            )
        )

    def test_non_staff_cannot_send(self):
        with self.assertRaises(CommandError):
            call_command(
                "send_timeline_post_push",
                "--post-id",
                str(self.post.pk),
                "--title",
                "title",
                "--body",
                "body",
                "--campaign-key",
                "ignite-test-denied",
                "--actor-email",
                self.student.email,
                "--test-email",
                self.student.email,
                "--send",
            )
        self.assertEqual(PushCampaign.objects.count(), 0)

    def test_removed_post_is_not_sent(self):
        self.post.is_removed = True
        self.post.save(update_fields=["is_removed"])
        with patch(
            "app.broadcast_push_services.deliver_push_to_user",
            return_value=self.sent,
        ) as deliver:
            with self.assertRaises(CommandError):
                call_command(
                    "send_timeline_post_push",
                    "--post-id",
                    str(self.post.pk),
                    "--title",
                    "title",
                    "--body",
                    "body",
                    "--campaign-key",
                    "ignite-removed",
                    "--actor-email",
                    self.actor.email,
                    "--send",
                    "--confirm-broadcast",
                )
        self.assertEqual(deliver.call_count, 0)
        self.assertEqual(PushCampaign.objects.count(), 0)

    def test_unlisted_organization_post_is_not_sent(self):
        self.post.organization_visibility = TimelinePost.OrganizationVisibility.DRAFT
        self.post.save(update_fields=["organization_visibility"])
        with self.assertRaises(BroadcastPushError):
            execute_timeline_post_push(
                post=self.post,
                title="title",
                body="body",
                campaign_key="ignite-draft",
                actor=self.actor,
            )
        self.assertEqual(PushCampaign.objects.count(), 0)
