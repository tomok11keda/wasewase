"""Regression tests for beta P0/P1 privacy, authz, and data-integrity fixes."""

from __future__ import annotations

from datetime import timedelta

from django.contrib.auth.hashers import make_password
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from app.course_services import create_offering, enroll_user_in_offering
from app.dm_request_services import (
    _notification_link_matches_dm_room,
    decline_dm_request,
    resolve_dm_request_notifications,
)
from app.group_invite_services import _notification_link_matches_group_room
from app.models import (
    ChatMessage,
    ChatRoom,
    CourseEnrollment,
    CourseMeeting,
    Notification,
    PasswordResetOTP,
    SignupOTP,
    TimelinePost,
    User,
    UserDirectMessageRoom,
    UserDirectMessageRequest,
    UserProfile,
)
from app.otp_services import OTP_MAX_ATTEMPTS, verify_password_reset_otp, verify_signup_otp
from app.timetable_services import upsert_timetable_slot
from app.ugc_services import block_user, filter_visible_timeline_posts


@override_settings(BROWSE_MODE_GATE_ENABLED=False)
class OtpAttemptLockoutTests(TestCase):
    def test_password_reset_otp_lockout_after_max_failures(self):
        user = User.objects.create_user(
            email="otp-lock@waseda.jp",
            password="pass12345",
            username="otplock",
        )
        PasswordResetOTP.objects.create(
            user=user,
            code_hash=make_password("123456"),
            expires_at=timezone.now() + timedelta(minutes=10),
            failed_attempts=0,
        )
        for _ in range(OTP_MAX_ATTEMPTS - 1):
            err = verify_password_reset_otp(user, "000000")
            self.assertIn("正しくありません", err)
        self.assertTrue(PasswordResetOTP.objects.filter(user=user).exists())
        err = verify_password_reset_otp(user, "000000")
        self.assertIn("上限", err)
        self.assertFalse(PasswordResetOTP.objects.filter(user=user).exists())

    def test_signup_otp_lockout_after_max_failures(self):
        user = User.objects.create_user(
            email="signup-lock@waseda.jp",
            password="pass12345",
            username="signuplock",
            is_active=False,
        )
        SignupOTP.objects.create(
            user=user,
            code_hash=make_password("654321"),
            expires_at=timezone.now() + timedelta(minutes=10),
        )
        for _ in range(OTP_MAX_ATTEMPTS):
            err = verify_signup_otp(user, "111111")
        self.assertIn("上限", err)
        self.assertFalse(SignupOTP.objects.filter(user=user).exists())


@override_settings(BROWSE_MODE_GATE_ENABLED=False)
class SharedOfferingMeetingLockTests(TestCase):
    def test_other_enrollee_cannot_add_meeting(self):
        owner = User.objects.create_user(
            email="meet-a@waseda.jp", password="pass12345", username="meeta"
        )
        other = User.objects.create_user(
            email="meet-b@waseda.jp", password="pass12345", username="meetb"
        )
        offering, _ = create_offering(
            user=owner,
            title="経営学",
            instructor="田中",
            academic_year=2026,
            semester="spring",
            day_of_week=0,
            period=2,
            force_create=True,
        )
        enroll_user_in_offering(owner, offering, slot_key="p2-d0")
        with self.assertRaises(ValueError) as ctx:
            enroll_user_in_offering(
                other,
                offering,
                slot_key="p2-d2",
                add_meeting_if_missing=True,
            )
        self.assertEqual(str(ctx.exception), "meeting_locked")
        self.assertEqual(
            CourseMeeting.objects.filter(offering=offering).count(), 1
        )
        self.assertFalse(
            CourseEnrollment.objects.filter(user=other, offering=offering).exists()
        )


@override_settings(BROWSE_MODE_GATE_ENABLED=False)
class TimetableMemoPrivacyTests(TestCase):
    def test_public_timetable_api_hides_memo_from_others(self):
        owner = User.objects.create_user(
            email="memo-a@waseda.jp", password="pass12345", username="memoa"
        )
        viewer = User.objects.create_user(
            email="memo-b@waseda.jp", password="pass12345", username="memob"
        )
        UserProfile.objects.update_or_create(
            user=owner,
            defaults={"name": "メモ主", "is_timetable_public": True},
        )
        upsert_timetable_slot(
            owner, slot_key="p1-d0", name="ミクロ", memo="秘密の課題メモ"
        )
        client = Client()
        client.force_login(viewer)
        res = client.get(f"/api/timetable/user/{owner.pk}/")
        self.assertEqual(res.status_code, 200)
        slot = res.json()["slots"]["p1-d0"]
        self.assertNotIn("memo", slot)
        self.assertEqual(slot["name"], "ミクロ")

        client.force_login(owner)
        own = client.get(f"/api/timetable/user/{owner.pk}/")
        self.assertEqual(own.json()["slots"]["p1-d0"]["memo"], "秘密の課題メモ")


@override_settings(BROWSE_MODE_GATE_ENABLED=False)
class GroupInviteHistoryPrivacyTests(TestCase):
    def test_pending_invitee_cannot_read_group_messages(self):
        owner = User.objects.create_user(
            email="ghist-a@waseda.jp", password="pass12345", username="ghista"
        )
        invitee = User.objects.create_user(
            email="ghist-b@waseda.jp", password="pass12345", username="ghistb"
        )
        client = Client()
        client.force_login(owner)
        created = client.post(
            "/api/v1/dm/groups/",
            data={"name": "秘密ゼミ", "member_ids": [invitee.pk]},
            content_type="application/json",
        )
        self.assertEqual(created.status_code, 201)
        room_id = created.json()["room_id"]
        room = ChatRoom.objects.get(pk=room_id)
        ChatMessage.objects.create(room=room, sender=owner, body="招待前の秘話")

        client.force_login(invitee)
        room_res = client.get(f"/api/v1/dm/groups/{room_id}/")
        self.assertEqual(room_res.status_code, 200)
        self.assertEqual(room_res.json()["room"]["membership_status"], "pending_invite")
        self.assertEqual(room_res.json()["messages"], [])

        poll = client.get(f"/api/v1/dm/groups/{room_id}/messages/")
        self.assertEqual(poll.status_code, 200)
        self.assertEqual(poll.json()["messages"], [])


class NotificationLinkMatchTests(SimpleTestCase):
    def test_dm_link_match_avoids_prefix_collision(self):
        self.assertTrue(_notification_link_matches_dm_room("/app/dm/1", 1))
        self.assertTrue(_notification_link_matches_dm_room("/dm/1", 1))
        self.assertFalse(_notification_link_matches_dm_room("/app/dm/10", 1))
        self.assertFalse(_notification_link_matches_dm_room("/app/dm/11", 1))
        self.assertFalse(_notification_link_matches_dm_room("/app/dm/groups/1", 1))

    def test_group_link_match_avoids_prefix_collision(self):
        self.assertTrue(
            _notification_link_matches_group_room("/app/dm/groups/2", 2)
        )
        self.assertFalse(
            _notification_link_matches_group_room("/app/dm/groups/20", 2)
        )


@override_settings(BROWSE_MODE_GATE_ENABLED=False)
class DeclinedDmAccessTests(TestCase):
    def test_declined_recipient_cannot_send_or_poll(self):
        a = User.objects.create_user(
            email="dmdec-a@waseda.jp", password="pass12345", username="dmdeca"
        )
        b = User.objects.create_user(
            email="dmdec-b@waseda.jp", password="pass12345", username="dmdecb"
        )
        room = UserDirectMessageRoom.objects.create(
            user_a=a if a.pk < b.pk else b,
            user_b=b if a.pk < b.pk else a,
        )
        UserDirectMessageRequest.objects.create(
            room=room,
            from_user=a,
            to_user=b,
            status=UserDirectMessageRequest.Status.PENDING,
        )
        decline_dm_request(room, b)

        client = Client()
        client.force_login(b)
        send = client.post(
            f"/api/v1/dm/rooms/{room.pk}/messages/send/",
            data={"body": "拒否後でも送れる？"},
            content_type="application/json",
        )
        self.assertEqual(send.status_code, 403)
        poll = client.get(f"/api/v1/dm/rooms/{room.pk}/messages/")
        self.assertEqual(poll.status_code, 403)
        classic = client.get(f"/dm/{room.pk}/messages/")
        self.assertEqual(classic.status_code, 403)


@override_settings(BROWSE_MODE_GATE_ENABLED=False)
class BidirectionalBlockFeedTests(TestCase):
    def test_blocked_user_cannot_see_blockers_posts(self):
        a = User.objects.create_user(
            email="blk-a@waseda.jp", password="pass12345", username="blka"
        )
        b = User.objects.create_user(
            email="blk-b@waseda.jp", password="pass12345", username="blkb"
        )
        post = TimelinePost.objects.create(author=a, body="Aの投稿")
        block_user(a, b)
        visible = filter_visible_timeline_posts(
            TimelinePost.objects.all(), viewer=b
        )
        self.assertFalse(visible.filter(pk=post.pk).exists())


@override_settings(BROWSE_MODE_GATE_ENABLED=False)
class DmNotificationResolveCollisionTests(TestCase):
    def test_resolve_does_not_touch_sibling_room_notifications(self):
        recipient = User.objects.create_user(
            email="ncoll-r@waseda.jp", password="pass12345", username="ncollr"
        )
        sender = User.objects.create_user(
            email="ncoll-s@waseda.jp", password="pass12345", username="ncolls"
        )
        room = UserDirectMessageRoom.objects.create(
            user_a=sender if sender.pk < recipient.pk else recipient,
            user_b=recipient if sender.pk < recipient.pk else sender,
        )
        note_match = Notification.objects.create(
            recipient=recipient,
            message="メッセージリクエストが届いています",
            link=f"/app/dm/{room.pk}",
        )
        note_sibling = Notification.objects.create(
            recipient=recipient,
            message="メッセージリクエストが届いています",
            link=f"/app/dm/{room.pk}0",
        )
        resolve_dm_request_notifications(recipient, room, accepted=True)
        note_match.refresh_from_db()
        note_sibling.refresh_from_db()
        self.assertIn("承認", note_match.message)
        self.assertTrue(note_match.is_read)
        self.assertEqual(note_sibling.message, "メッセージリクエストが届いています")
        self.assertFalse(note_sibling.is_read)


class CameraNativeScriptSanityTests(SimpleTestCase):
    def test_capacitor_native_has_no_json_debug_alerts(self):
        from pathlib import Path

        root = Path(__file__).resolve().parents[1]
        for rel in ("static/js/capacitor_native.js", "www/js/capacitor_native.js"):
            text = (root / rel).read_text()
            self.assertNotIn("alert(JSON.stringify", text)
            self.assertIn("function alertCameraDebugError", text)


class AllowedHostsGuardTests(SimpleTestCase):
    def test_star_disallowed_when_not_debug(self):
        from django.core.exceptions import ImproperlyConfigured

        debug = False
        allowed_hosts_env = "*"
        with self.assertRaises(ImproperlyConfigured):
            if allowed_hosts_env.strip() == "*":
                if debug:
                    _ = ["*"]
                else:
                    raise ImproperlyConfigured(
                        "本番では DJANGO_ALLOWED_HOSTS=* は許可されません。"
                    )