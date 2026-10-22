"""Inactive-user popular post retention push. Must not touch 1:1 or broadcast."""

from __future__ import annotations

from datetime import timedelta
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management import CommandError, call_command
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from .broadcast_push_services import user_allows_broadcast_push
from .last_seen_services import maybe_touch_last_seen
from .models import (
    DevicePushToken,
    Notification,
    RetentionPushSend,
    TimelinePost,
    UserProfile,
)
from .push_services import (
    PushDeliveryOutcome,
    PushDeliveryResult,
    reset_firebase_app_for_tests,
)
from .retention_push_services import (
    RETENTION_KIND_POPULAR_POST,
    RETENTION_PUSH_BODY,
    RETENTION_PUSH_TITLE,
    execute_popular_post_retention,
    popular_post_push_link,
)

User = get_user_model()
ROOT = Path(__file__).resolve().parents[1]


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def _profile(user, **fields) -> UserProfile:
    profile, _created = UserProfile.objects.get_or_create(user=user)
    for key, value in fields.items():
        setattr(profile, key, value)
    profile.save()
    return profile


def _ios(user, token: str) -> DevicePushToken:
    return DevicePushToken.objects.create(
        user=user, token=token, platform=DevicePushToken.Platform.IOS
    )


class LastSeenTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            email="seen@waseda.jp", password="test-pass-12345"
        )
        self.profile = _profile(self.user, department="商学部")

    def test_touch_writes_once_then_cache_skips(self):
        self.assertTrue(maybe_touch_last_seen(self.user, path="/app/"))
        self.profile.refresh_from_db()
        first = self.profile.last_seen_at
        self.assertIsNotNone(first)
        self.assertFalse(maybe_touch_last_seen(self.user, path="/app/"))
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.last_seen_at, first)

    def test_static_paths_do_not_write(self):
        self.assertFalse(maybe_touch_last_seen(self.user, path="/static/frontend/assets/main.js"))
        self.profile.refresh_from_db()
        self.assertIsNone(self.profile.last_seen_at)

    @override_settings(WASE_REACT_SPA=True, BROWSE_MODE_GATE_ENABLED=False)
    def test_middleware_updates_on_app_request(self):
        self.client.force_login(self.user)
        res = self.client.get("/app/")
        self.assertEqual(res.status_code, 200)
        self.profile.refresh_from_db()
        self.assertIsNotNone(self.profile.last_seen_at)


class RetentionPopularPostPushTests(TestCase):
    def setUp(self):
        reset_firebase_app_for_tests()
        cache.clear()
        self.now = timezone.now()
        self.author = User.objects.create_user(
            email="author@waseda.jp", password="test-pass-12345"
        )
        _profile(self.author, department="商学部")
        self.inactive = User.objects.create_user(
            email="inactive@waseda.jp", password="test-pass-12345"
        )
        _profile(
            self.inactive,
            department="商学部",
            last_seen_at=self.now - timedelta(hours=80),
        )
        _ios(self.inactive, "fcm-inactive-ios")
        self.post = TimelinePost.objects.create(
            author=self.author,
            body="campus popular body",
            like_count=12,
            created_at=self.now - timedelta(hours=30),
        )
        TimelinePost.objects.filter(pk=self.post.pk).update(
            created_at=self.now - timedelta(hours=30)
        )
        self.post.refresh_from_db()

    def tearDown(self):
        reset_firebase_app_for_tests()

    def _recent_user(self, **kwargs):
        user = User.objects.create_user(
            email=kwargs.get("email", "recent@waseda.jp"),
            password="test-pass-12345",
        )
        _profile(
            user,
            department=kwargs.get("department", "商学部"),
            last_seen_at=kwargs.get("last_seen_at", self.now - timedelta(hours=10)),
        )
        if kwargs.get("token", True):
            _ios(user, kwargs.get("token_value", "fcm-recent-ios"))
        return user

    def test_inactive_under_72h_is_not_selected(self):
        recent = self._recent_user()
        sent = PushDeliveryResult(PushDeliveryOutcome.SENT, success_count=1, reason="ok")
        with patch(
            "app.retention_push_services.deliver_push_to_user", return_value=sent
        ) as mock_deliver:
            result = execute_popular_post_retention(send=True, now=self.now)
        user_ids = [row["user_id"] for row in result["deliveries"]]
        self.assertNotIn(recent.pk, user_ids)
        mock_deliver.assert_called()
        self.assertTrue(
            any(row["user_id"] == self.inactive.pk for row in result["deliveries"])
        )

    def test_inactive_over_72h_can_be_selected(self):
        result = execute_popular_post_retention(send=False, now=self.now)
        self.assertGreaterEqual(result["preview"]["planned_sends"], 1)
        self.assertTrue(
            any(row["user_id"] == self.inactive.pk for row in result["deliveries"])
        )

    def test_no_token_is_not_selected(self):
        DevicePushToken.objects.filter(user=self.inactive).delete()
        with patch("app.retention_push_services.deliver_push_to_user") as mock_deliver:
            result = execute_popular_post_retention(send=True, now=self.now)
        mock_deliver.assert_not_called()
        self.assertFalse(
            any(row["user_id"] == self.inactive.pk for row in result["deliveries"])
        )

    def test_opt_out_is_not_selected(self):
        def _allow(user):
            if user.pk == self.inactive.pk:
                return False
            return user_allows_broadcast_push(user)

        with patch(
            "app.retention_push_services.user_allows_broadcast_push",
            side_effect=_allow,
        ):
            with patch(
                "app.retention_push_services.deliver_push_to_user"
            ) as mock_deliver:
                result = execute_popular_post_retention(send=True, now=self.now)
        mock_deliver.assert_not_called()
        self.assertFalse(
            any(row["user_id"] == self.inactive.pk for row in result["deliveries"])
        )

    def test_own_post_is_excluded(self):
        TimelinePost.objects.filter(pk=self.post.pk).update(author=self.inactive)
        with patch("app.retention_push_services.deliver_push_to_user") as mock_deliver:
            result = execute_popular_post_retention(send=True, now=self.now)
        mock_deliver.assert_not_called()
        self.assertEqual(result["counts"]["skipped_no_post"], 1)

    def test_same_post_is_not_resent(self):
        prior = RetentionPushSend.objects.create(
            user=self.inactive,
            kind=RETENTION_KIND_POPULAR_POST,
            object_id=str(self.post.pk),
            status=RetentionPushSend.Status.SENT,
            local_date=(self.now - timedelta(days=10)).date(),
            sent_at=self.now - timedelta(days=10),
        )
        RetentionPushSend.objects.filter(pk=prior.pk).update(
            created_at=self.now - timedelta(days=10),
            sent_at=self.now - timedelta(days=10),
        )
        other = TimelinePost.objects.create(
            author=self.author,
            body="another popular",
            like_count=3,
        )
        TimelinePost.objects.filter(pk=other.pk).update(
            created_at=self.now - timedelta(hours=36)
        )
        sent = PushDeliveryResult(PushDeliveryOutcome.SENT, success_count=1, reason="ok")
        with patch(
            "app.retention_push_services.deliver_push_to_user", return_value=sent
        ) as mock_deliver:
            result = execute_popular_post_retention(send=True, now=self.now)
        mock_deliver.assert_called_once()
        self.assertEqual(result["deliveries"][0]["post_id"], other.pk)

    def test_frequency_cap_within_72h(self):
        older = TimelinePost.objects.create(
            author=self.author,
            body="older popular",
            like_count=4,
        )
        TimelinePost.objects.filter(pk=older.pk).update(
            created_at=self.now - timedelta(hours=40)
        )
        prior = RetentionPushSend.objects.create(
            user=self.inactive,
            kind=RETENTION_KIND_POPULAR_POST,
            object_id=str(older.pk),
            status=RetentionPushSend.Status.SENT,
            local_date=self.now.date(),
            sent_at=self.now - timedelta(hours=5),
        )
        RetentionPushSend.objects.filter(pk=prior.pk).update(
            created_at=self.now - timedelta(hours=5),
            sent_at=self.now - timedelta(hours=5),
        )
        with patch("app.retention_push_services.deliver_push_to_user") as mock_deliver:
            result = execute_popular_post_retention(send=True, now=self.now)
        mock_deliver.assert_not_called()
        self.assertGreaterEqual(result["counts"]["skipped_cap"], 1)

    def test_dry_run_does_not_send_or_write(self):
        with patch("app.retention_push_services.deliver_push_to_user") as mock_deliver:
            result = execute_popular_post_retention(send=False, now=self.now)
        mock_deliver.assert_not_called()
        self.assertEqual(result["deliveries"][0]["status"], "dry_run")
        self.assertEqual(RetentionPushSend.objects.count(), 0)
        self.assertEqual(Notification.objects.count(), 0)
        out = StringIO()
        call_command("send_retention_popular_post_push", stdout=out)
        self.assertIn("dry-run", out.getvalue())
        self.assertEqual(RetentionPushSend.objects.count(), 0)

    @override_settings(PUSH_NOTIFICATIONS_ENABLED=True)
    def test_send_uses_only_deliver_push_to_user(self):
        sent = PushDeliveryResult(PushDeliveryOutcome.SENT, success_count=1, reason="ok")
        with (
            patch(
                "app.retention_push_services.deliver_push_to_user", return_value=sent
            ) as mock_deliver,
            patch("app.notification_services.create_notification") as mock_create,
            patch("app.push_services.notify_user_push") as mock_notify,
        ):
            result = execute_popular_post_retention(send=True, now=self.now)
        mock_deliver.assert_called_once()
        kwargs = mock_deliver.call_args.kwargs
        self.assertEqual(kwargs["title"], RETENTION_PUSH_TITLE)
        self.assertEqual(kwargs["body"], RETENTION_PUSH_BODY)
        self.assertNotIn("campus popular body", kwargs["body"])
        self.assertNotIn("author", kwargs["body"])
        self.assertEqual(kwargs["link"], popular_post_push_link(self.post.pk))
        self.assertIn("rp=popular_post", kwargs["link"])
        self.assertIn(f"/app/posts/{self.post.pk}", kwargs["link"])
        self.assertEqual(kwargs["notification_type"], RETENTION_KIND_POPULAR_POST)
        mock_create.assert_not_called()
        mock_notify.assert_not_called()
        self.assertEqual(result["counts"]["sent"], 1)
        self.assertEqual(result["in_app_notifications_created"], 0)
        self.assertEqual(Notification.objects.count(), 0)
        row = RetentionPushSend.objects.get()
        self.assertEqual(row.status, RetentionPushSend.Status.SENT)
        self.assertEqual(row.object_id, str(self.post.pk))
        self.assertEqual(row.kind, RETENTION_KIND_POPULAR_POST)

    def test_last_login_is_ignored_for_inactivity(self):
        recent = self._recent_user()
        User.objects.filter(pk=recent.pk).update(
            last_login=self.now - timedelta(hours=96)
        )
        User.objects.filter(pk=self.inactive.pk).update(last_login=self.now)
        result = execute_popular_post_retention(send=False, now=self.now)
        ids = [row["user_id"] for row in result["deliveries"]]
        self.assertNotIn(recent.pk, ids)
        self.assertIn(self.inactive.pk, ids)

    def test_null_last_seen_is_not_selected(self):
        unseen = User.objects.create_user(
            email="unseen@waseda.jp", password="test-pass-12345"
        )
        _profile(unseen, department="商学部", last_seen_at=None)
        _ios(unseen, "fcm-unseen-ios")
        result = execute_popular_post_retention(send=False, now=self.now)
        ids = [row["user_id"] for row in result["deliveries"]]
        self.assertNotIn(unseen.pk, ids)

    def test_posts_outside_24_to_48h_window_are_excluded(self):
        TimelinePost.objects.filter(pk=self.post.pk).update(
            created_at=self.now - timedelta(hours=10)
        )
        with patch("app.retention_push_services.deliver_push_to_user") as mock_deliver:
            too_new = execute_popular_post_retention(send=True, now=self.now)
        mock_deliver.assert_not_called()
        self.assertEqual(too_new["preview"]["popular_candidates"], 0)

        TimelinePost.objects.filter(pk=self.post.pk).update(
            created_at=self.now - timedelta(hours=50)
        )
        with patch("app.retention_push_services.deliver_push_to_user") as mock_deliver:
            too_old = execute_popular_post_retention(send=True, now=self.now)
        mock_deliver.assert_not_called()
        self.assertEqual(too_old["preview"]["popular_candidates"], 0)

    def test_zero_engagement_is_not_sent(self):
        TimelinePost.objects.filter(pk=self.post.pk).update(like_count=0)
        with patch("app.retention_push_services.deliver_push_to_user") as mock_deliver:
            result = execute_popular_post_retention(send=True, now=self.now)
        mock_deliver.assert_not_called()
        self.assertEqual(result["preview"]["popular_candidates"], 0)

    def test_removed_post_is_excluded(self):
        TimelinePost.objects.filter(pk=self.post.pk).update(is_removed=True)
        with patch("app.retention_push_services.deliver_push_to_user") as mock_deliver:
            execute_popular_post_retention(send=True, now=self.now)
        mock_deliver.assert_not_called()

    def test_staff_and_test_accounts_are_excluded(self):
        staff = User.objects.create_user(
            email="staff@waseda.jp",
            password="test-pass-12345",
            is_staff=True,
        )
        _profile(staff, department="商学部", last_seen_at=self.now - timedelta(hours=80))
        _ios(staff, "fcm-staff-ios")
        tester = User.objects.create_user(
            email="test1@waseda.jp", password="test-pass-12345"
        )
        _profile(
            tester, department="商学部", last_seen_at=self.now - timedelta(hours=80)
        )
        _ios(tester, "fcm-test-ios")
        result = execute_popular_post_retention(send=False, now=self.now)
        ids = [row["user_id"] for row in result["deliveries"]]
        self.assertNotIn(staff.pk, ids)
        self.assertNotIn(tester.pk, ids)

    def test_command_send_flag_required_for_delivery(self):
        sent = PushDeliveryResult(PushDeliveryOutcome.SENT, success_count=1, reason="ok")
        with patch(
            "app.retention_push_services.deliver_push_to_user", return_value=sent
        ) as mock_deliver:
            call_command("send_retention_popular_post_push", stdout=StringIO())
            mock_deliver.assert_not_called()
            call_command(
                "send_retention_popular_post_push", "--send", stdout=StringIO()
            )
            mock_deliver.assert_called_once()


class RetentionTestUserPushTests(TestCase):
    def setUp(self):
        reset_firebase_app_for_tests()
        cache.clear()
        self.now = timezone.now()
        self.author = User.objects.create_user(
            email="author-test@waseda.jp", password="test-pass-12345"
        )
        _profile(self.author, department="商学部")
        self.inactive = User.objects.create_user(
            email="inactive-other@waseda.jp", password="test-pass-12345"
        )
        _profile(
            self.inactive,
            department="商学部",
            last_seen_at=self.now - timedelta(hours=80),
        )
        _ios(self.inactive, "fcm-other-inactive-ios")
        self.target = User.objects.create_user(
            email="me@waseda.jp", password="test-pass-12345"
        )
        _profile(
            self.target,
            department="商学部",
            last_seen_at=self.now - timedelta(hours=10),
        )
        _ios(self.target, "fcm-me-ios")
        self.post = TimelinePost.objects.create(
            author=self.author,
            body="campus popular body",
            like_count=12,
        )
        TimelinePost.objects.filter(pk=self.post.pk).update(
            created_at=self.now - timedelta(hours=30)
        )
        self.post.refresh_from_db()
        self.sent = PushDeliveryResult(
            PushDeliveryOutcome.SENT, success_count=1, reason="ok"
        )

    def tearDown(self):
        reset_firebase_app_for_tests()

    def test_test_user_email_never_sends_to_others(self):
        with patch(
            "app.retention_push_services.deliver_push_to_user", return_value=self.sent
        ) as mock_deliver:
            result = execute_popular_post_retention(
                send=True,
                now=self.now,
                test_user=self.target,
                ignore_inactivity=True,
            )
        mock_deliver.assert_called_once()
        self.assertEqual(mock_deliver.call_args.args[0].pk, self.target.pk)
        ids = [row["user_id"] for row in result["deliveries"]]
        self.assertEqual(ids, [self.target.pk])
        self.assertNotIn(self.inactive.pk, ids)
        self.assertEqual(result["audience"], "test")
        kwargs = mock_deliver.call_args.kwargs
        self.assertEqual(kwargs["title"], RETENTION_PUSH_TITLE)
        self.assertEqual(kwargs["body"], RETENTION_PUSH_BODY)
        self.assertEqual(kwargs["link"], popular_post_push_link(self.post.pk))
        self.assertIn("rp=popular_post", kwargs["link"])

    def test_test_user_id_command_pins_one_user(self):
        with patch(
            "app.retention_push_services.deliver_push_to_user", return_value=self.sent
        ) as mock_deliver:
            call_command(
                "send_retention_popular_post_push",
                "--send",
                f"--test-user-id={self.target.pk}",
                "--ignore-inactivity",
                stdout=StringIO(),
            )
        mock_deliver.assert_called_once()
        self.assertEqual(mock_deliver.call_args.args[0].pk, self.target.pk)

    def test_test_user_without_send_is_dry_run(self):
        with patch("app.retention_push_services.deliver_push_to_user") as mock_deliver:
            out = StringIO()
            call_command(
                "send_retention_popular_post_push",
                f"--test-email={self.target.email}",
                "--ignore-inactivity",
                stdout=out,
            )
        mock_deliver.assert_not_called()
        self.assertEqual(RetentionPushSend.objects.count(), 0)
        self.assertIn("dry-run", out.getvalue())
        self.assertIn("audience=test", out.getvalue())

    def test_recent_test_user_requires_ignore_inactivity(self):
        with patch("app.retention_push_services.deliver_push_to_user") as mock_deliver:
            blocked = execute_popular_post_retention(
                send=True, now=self.now, test_user=self.target
            )
        mock_deliver.assert_not_called()
        self.assertEqual(blocked["deliveries"], [])
        self.assertEqual(blocked["preview"]["inactive_eligible_users"], 0)

        with patch(
            "app.retention_push_services.deliver_push_to_user", return_value=self.sent
        ) as mock_deliver:
            allowed = execute_popular_post_retention(
                send=True,
                now=self.now,
                test_user=self.target,
                ignore_inactivity=True,
            )
        mock_deliver.assert_called_once()
        self.assertEqual(allowed["deliveries"][0]["user_id"], self.target.pk)

    def test_ignore_inactivity_without_test_user_is_rejected(self):
        with self.assertRaises(CommandError):
            call_command(
                "send_retention_popular_post_push",
                "--send",
                "--ignore-inactivity",
                stdout=StringIO(),
            )
        with patch("app.retention_push_services.deliver_push_to_user") as mock_deliver:
            with self.assertRaises(CommandError):
                call_command(
                    "send_retention_popular_post_push",
                    "--ignore-inactivity",
                    stdout=StringIO(),
                )
        mock_deliver.assert_not_called()

    def test_unknown_test_user_is_rejected(self):
        with self.assertRaises(CommandError):
            call_command(
                "send_retention_popular_post_push",
                "--test-email=missing@waseda.jp",
                stdout=StringIO(),
            )
        with self.assertRaises(CommandError):
            call_command(
                "send_retention_popular_post_push",
                "--test-user-id=999999",
                stdout=StringIO(),
            )

    def test_email_and_user_id_mismatch_is_rejected(self):
        with self.assertRaises(CommandError):
            call_command(
                "send_retention_popular_post_push",
                f"--test-email={self.target.email}",
                f"--test-user-id={self.inactive.pk}",
                stdout=StringIO(),
            )

    def test_test_user_without_token_does_not_fall_back(self):
        DevicePushToken.objects.filter(user=self.target).delete()
        with patch("app.retention_push_services.deliver_push_to_user") as mock_deliver:
            result = execute_popular_post_retention(
                send=True,
                now=self.now,
                test_user=self.target,
                ignore_inactivity=True,
            )
        mock_deliver.assert_not_called()
        self.assertEqual(result["deliveries"], [])
        self.assertNotIn(self.inactive.pk, [row["user_id"] for row in result["deliveries"]])

    def test_production_send_without_test_user_still_targets_inactive(self):
        with patch(
            "app.retention_push_services.deliver_push_to_user", return_value=self.sent
        ) as mock_deliver:
            result = execute_popular_post_retention(send=True, now=self.now)
        ids = [row["user_id"] for row in result["deliveries"]]
        self.assertIn(self.inactive.pk, ids)
        self.assertNotIn(self.target.pk, ids)
        self.assertEqual(result["audience"], "production")
        mock_deliver.assert_called()
        self.assertTrue(
            all(call.args[0].pk != self.target.pk for call in mock_deliver.call_args_list)
        )


class RetentionPushSourceTests(SimpleTestCase):
    def test_course_talk_push_stays_off(self):
        src = _read("app/course_chat_services.py")
        self.assertIn("Push / in-app Notification: intentionally OFF", src)

    def test_native_open_captures_retention_without_changing_notification_opened(self):
        router = _read("frontend/src/components/NativePushOpenRouter.tsx")
        events = _read("frontend/src/lib/analytics/events.ts")
        self.assertIn("retentionPushOpened", router)
        self.assertIn("parseRetentionPushOpen", router)
        self.assertIn("retention_push_opened", events)
        self.assertIn('captureEvent("notification_opened")', events)
        self.assertNotIn("retention_push_opened", events.split("notificationOpened")[1].split("retentionPushOpened")[0])

    def test_link_helper_keeps_generic_copy(self):
        self.assertIn("rp=popular_post", popular_post_push_link(7))
        self.assertIn("/app/posts/7", popular_post_push_link(7))

    def test_inactivity_does_not_use_last_login(self):
        src = _read("app/retention_push_services.py")
        self.assertNotIn("last_login", src)
        self.assertIn("last_seen_at", src)
        self.assertIn("CANDIDATE_MIN_AGE_HOURS = 24", src)
        self.assertIn("CANDIDATE_MAX_AGE_HOURS = 48", src)
        self.assertIn("deliver_push_to_user", src)
        self.assertNotIn("create_notification(", src)
        self.assertNotIn("notify_user_push(", src)
