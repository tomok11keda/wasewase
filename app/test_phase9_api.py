"""Phase 9: notifications + auth JSON API tests."""

from __future__ import annotations

import json

from django.core import mail
from django.test import Client, TestCase, override_settings

from .models import Notification, User, UserProfile
from .notification_api_services import notification_spa_path
from .otp_services import (
    PASSWORD_RESET_USER_SESSION_KEY,
    PASSWORD_RESET_VERIFIED_SESSION_KEY,
    SIGNUP_PENDING_SESSION_KEY,
    create_and_send_password_reset_otp,
    create_and_send_signup_otp,
    generate_otp_code,
)


@override_settings(
    BROWSE_MODE_GATE_ENABLED=False,
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    EMAIL_USE_CONSOLE_FALLBACK=True,
)
class NotificationApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="n9@waseda.jp", password="test-pass-12345", username="n9"
        )
        UserProfile.objects.update_or_create(user=self.user, defaults={"name": "N"})
        self.client = Client()
        Notification.objects.create(
            recipient=self.user,
            message="テスト通知",
            link="/user/2/",
            is_read=False,
        )
        Notification.objects.create(
            recipient=self.user,
            message="DM通知",
            link="/dm/9/",
            is_read=False,
        )

    def test_spa_path_mapping(self):
        self.assertEqual(notification_spa_path("/user/5/"), "/users/5/posts")
        self.assertEqual(notification_spa_path("/dm/3/"), "/dm/3")
        self.assertEqual(notification_spa_path("/chat/7/"), "/flea/chats/7")
        self.assertEqual(notification_spa_path("/app/flea/chats/7"), "/flea/chats/7")
        self.assertEqual(notification_spa_path("/product/4/"), "/flea/products/4")
        self.assertEqual(notification_spa_path("/#post-12"), "/#post-12")
        self.assertEqual(
            notification_spa_path("/communities/foo/threads/9/"),
            "/communities/foo/threads/9",
        )
        self.assertEqual(notification_spa_path("/communities/"), "/communities")
        self.assertEqual(notification_spa_path("/flea/"), "/flea")
        self.assertEqual(notification_spa_path("/exhibit/"), "/flea/exhibit")
        self.assertEqual(notification_spa_path("/more/"), "/more")
        self.assertEqual(notification_spa_path("/timetable/"), "/timetable")
        self.assertEqual(notification_spa_path("/notifications/"), "/notifications")
        self.assertEqual(notification_spa_path("/dm/"), "/dm")
        self.assertEqual(notification_spa_path("/mypage/settings/"), "")

    def test_list_marks_read(self):
        self.client.force_login(self.user)
        res = self.client.get("/api/v1/notifications/")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data["ok"])
        self.assertEqual(len(data["notifications"]), 2)
        self.assertEqual(data["unread_count"], 0)
        self.assertGreaterEqual(data["marked_count"], 1)
        paths = {n["spa_path"] for n in data["notifications"]}
        self.assertIn("/users/2/posts", paths)
        self.assertIn("/dm/9", paths)

    def test_mark_read_endpoint(self):
        self.client.force_login(self.user)
        res = self.client.post("/api/v1/notifications/mark-read/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["unread_count"], 0)

    def test_unauthenticated_list(self):
        res = self.client.get("/api/v1/notifications/")
        self.assertIn(res.status_code, (302, 401, 403))


@override_settings(
    BROWSE_MODE_GATE_ENABLED=False,
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    EMAIL_USE_CONSOLE_FALLBACK=True,
    WASE_REACT_SPA=True,
)
class AuthApiTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            email="auth9@waseda.jp",
            password="test-pass-12345",
            username="auth9",
            is_active=True,
        )
        UserProfile.objects.update_or_create(
            user=self.user, defaults={"name": "Auth"}
        )

    def test_login_logout(self):
        bad = self.client.post(
            "/api/v1/auth/login/",
            data=json.dumps({"email": "auth9@waseda.jp", "password": "wrong"}),
            content_type="application/json",
        )
        self.assertEqual(bad.status_code, 400)

        ok = self.client.post(
            "/api/v1/auth/login/",
            data=json.dumps(
                {
                    "email": "auth9@waseda.jp",
                    "password": "test-pass-12345",
                    "next": "/app/dm",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(ok.status_code, 200)
        self.assertTrue(ok.json()["ok"])
        self.assertTrue(ok.json()["me"]["authenticated"])
        self.assertEqual(ok.json()["redirect"], "/app/dm")

        me = self.client.get("/api/v1/auth/me/")
        self.assertTrue(me.json()["me"]["authenticated"])

        out = self.client.post("/api/v1/auth/logout/")
        self.assertEqual(out.status_code, 200)
        me2 = self.client.get("/api/v1/auth/me/")
        self.assertFalse(me2.json()["me"]["authenticated"])

    def test_signup_verify_flow(self):
        meta = self.client.get("/api/v1/auth/signup-meta/")
        self.assertEqual(meta.status_code, 200)
        self.assertTrue(meta.json()["faculties"])

        signup = self.client.post(
            "/api/v1/auth/signup/",
            data=json.dumps(
                {
                    "email": "new9@waseda.jp",
                    "nickname": "新規",
                    "username": "new9user",
                    "faculty": "政治経済学部",
                    "password1": "test-pass-12345",
                    "password2": "test-pass-12345",
                    "accept_terms": True,
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(signup.status_code, 201)
        self.assertEqual(signup.json()["redirect"], "/app/verify")
        user = User.objects.get(email="new9@waseda.jp")
        self.assertFalse(user.is_active)

        # Pull OTP from SignupOTP via creating known code
        from django.contrib.auth.hashers import make_password
        from django.utils import timezone
        from datetime import timedelta
        from .models import SignupOTP

        code = "123456"
        SignupOTP.objects.update_or_create(
            user=user,
            defaults={
                "code_hash": make_password(code),
                "expires_at": timezone.now() + timedelta(minutes=10),
            },
        )
        session = self.client.session
        session[SIGNUP_PENDING_SESSION_KEY] = user.pk
        session.save()

        verify = self.client.post(
            "/api/v1/auth/verify/",
            data=json.dumps({"code": code}),
            content_type="application/json",
        )
        self.assertEqual(verify.status_code, 200)
        user.refresh_from_db()
        self.assertTrue(user.is_active)
        self.assertTrue(verify.json()["me"]["authenticated"])

    def test_password_reset_flow(self):
        from django.contrib.auth.hashers import make_password
        from django.utils import timezone
        from datetime import timedelta
        from .models import PasswordResetOTP

        req = self.client.post(
            "/api/v1/auth/password-reset/",
            data=json.dumps({"email": "auth9@waseda.jp"}),
            content_type="application/json",
        )
        self.assertEqual(req.status_code, 200)
        self.assertEqual(req.json()["redirect"], "/app/password-reset/verify")

        code = "654321"
        PasswordResetOTP.objects.update_or_create(
            user=self.user,
            defaults={
                "code_hash": make_password(code),
                "expires_at": timezone.now() + timedelta(minutes=10),
            },
        )
        session = self.client.session
        session[PASSWORD_RESET_USER_SESSION_KEY] = self.user.pk
        session.save()

        ver = self.client.post(
            "/api/v1/auth/password-reset/verify/",
            data=json.dumps({"code": code}),
            content_type="application/json",
        )
        self.assertEqual(ver.status_code, 200)

        setp = self.client.post(
            "/api/v1/auth/password-reset/set/",
            data=json.dumps(
                {"password1": "new-pass-12345", "password2": "new-pass-12345"}
            ),
            content_type="application/json",
        )
        self.assertEqual(setp.status_code, 200)
        self.assertEqual(setp.json()["redirect"], "/app/login")

        login = self.client.post(
            "/api/v1/auth/login/",
            data=json.dumps(
                {"email": "auth9@waseda.jp", "password": "new-pass-12345"}
            ),
            content_type="application/json",
        )
        self.assertEqual(login.status_code, 200)
        self.assertTrue(login.json()["ok"])

    def test_browse_mode(self):
        res = self.client.post(
            "/api/v1/auth/browse/",
            data=json.dumps({"next": "/app/"}),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()["me"]["is_browse_mode"])


@override_settings(WASE_REACT_SPA=False, BROWSE_MODE_GATE_ENABLED=False)
class ClassicAuthUnaffectedTests(TestCase):
    def test_classic_login_html(self):
        res = self.client.get("/login/")
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "ログイン")

    def test_classic_notifications_html(self):
        user = User.objects.create_user(
            email="classic-n@waseda.jp",
            password="test-pass-12345",
            username="classicn",
        )
        self.client.force_login(user)
        res = self.client.get("/notifications/")
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "通知")
