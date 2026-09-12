"""Auth login / OTP / password-reset HTTP rate limits."""

from __future__ import annotations

import json
from unittest.mock import patch

from django.core import mail
from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from app.models import PasswordResetOTP, SignupOTP, User
from app.otp_services import (
    OTP_MAX_ATTEMPTS,
    PASSWORD_RESET_USER_SESSION_KEY,
    PASSWORD_RESET_VERIFIED_SESSION_KEY,
    SIGNUP_PENDING_SESSION_KEY,
    create_and_send_signup_otp,
    verify_signup_otp,
)
from app.rate_limit_services import (
    AUTH_LOGIN_ID_LIMIT,
    AUTH_OTP_VERIFY_ID_LIMIT,
    AUTH_RESET_OTP_EMAIL_LIMIT,
    AUTH_SIGNUP_OTP_EMAIL_LIMIT,
    RATE_LIMIT_USER_MESSAGE,
    allow_login_rate_limit,
    auth_identifier_digest,
)


def _json(payload: dict) -> dict:
    return {"data": json.dumps(payload), "content_type": "application/json"}


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DEFAULT_FROM_EMAIL="test@example.com",
    BROWSE_MODE_GATE_ENABLED=False,
)
class AuthRateLimitTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = Client(REMOTE_ADDR="203.0.113.10")
        self.user = User.objects.create_user(
            email="login-rl@waseda.jp",
            password="correct-pass-123",
            username="loginrl",
            is_active=True,
        )

    def tearDown(self):
        cache.clear()

    def _login_api(self, email="login-rl@waseda.jp", password="wrong"):
        return self.client.post(
            "/api/v1/auth/login/",
            **_json({"email": email, "password": password}),
        )

    def _classic_login(self, email="login-rl@waseda.jp", password="wrong"):
        return self.client.post(
            reverse("login"),
            {"username": email, "password": password},
        )

    def test_login_identifier_limit_api(self):
        for _ in range(AUTH_LOGIN_ID_LIMIT):
            res = self._login_api()
            self.assertEqual(res.status_code, 400)
        blocked = self._login_api()
        self.assertEqual(blocked.status_code, 429)
        body = blocked.json()
        self.assertFalse(body["ok"])
        self.assertEqual(body["error"], "rate_limited")
        self.assertEqual(body["message"], RATE_LIMIT_USER_MESSAGE)
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_active)

    def test_login_classic_and_api_share_budget(self):
        for _ in range(5):
            self.assertEqual(self._login_api().status_code, 400)
        for _ in range(5):
            self.assertEqual(self._classic_login().status_code, 200)
        blocked_api = self._login_api()
        self.assertEqual(blocked_api.status_code, 429)
        blocked_classic = self._classic_login()
        self.assertEqual(blocked_classic.status_code, 429)
        self.assertContains(
            blocked_classic, RATE_LIMIT_USER_MESSAGE, status_code=429
        )
        self.assertFalse(self.client.session.get("_auth_user_id"))

    def test_login_ip_limit(self):
        with patch("app.rate_limit_services.AUTH_LOGIN_IP_LIMIT", 3):
            other = Client(REMOTE_ADDR="203.0.113.10")
            for i in range(3):
                User.objects.create_user(
                    email=f"ip{i}@waseda.jp",
                    password="x",
                    username=f"ip{i}user",
                )
                res = other.post(
                    "/api/v1/auth/login/",
                    **_json({"email": f"ip{i}@waseda.jp", "password": "wrong"}),
                )
                self.assertEqual(res.status_code, 400)
            blocked = other.post(
                "/api/v1/auth/login/",
                **_json({"email": "fresh-ip@waseda.jp", "password": "wrong"}),
            )
            self.assertEqual(blocked.status_code, 429)

    def test_login_does_not_lock_account(self):
        for _ in range(AUTH_LOGIN_ID_LIMIT + 1):
            self._login_api()
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_active)
        cache.clear()
        ok = self._login_api(password="correct-pass-123")
        self.assertEqual(ok.status_code, 200)
        self.assertTrue(ok.json()["ok"])

    def test_rate_limited_login_does_not_authenticate(self):
        for _ in range(AUTH_LOGIN_ID_LIMIT):
            self._login_api()
        blocked = self._login_api(password="correct-pass-123")
        self.assertEqual(blocked.status_code, 429)
        self.assertFalse(self.client.session.get("_auth_user_id"))
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_active)

    def test_cache_keys_do_not_contain_raw_email(self):
        email = "login-rl@waseda.jp"
        self._login_api()
        digest = auth_identifier_digest(email)
        self.assertIsNotNone(cache.get(f"rl:auth_login_id:{digest}"))
        self.assertIsNone(cache.get(f"rl:auth_login_id:{email}"))
        self.assertIsNone(cache.get(f"rl:auth_login_id:{email.lower()}"))
        self.assertNotEqual(digest, email)

    def test_cache_failure_fail_open(self):
        with patch(
            "app.course_services.cache.get", side_effect=RuntimeError("cache down")
        ):
            self.assertTrue(allow_login_rate_limit(None, "login-rl@waseda.jp"))
        res = self._login_api()
        self.assertEqual(res.status_code, 400)


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DEFAULT_FROM_EMAIL="test@example.com",
    BROWSE_MODE_GATE_ENABLED=False,
)
class SignupOtpRateLimitTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = Client(REMOTE_ADDR="198.51.100.20")

    def tearDown(self):
        cache.clear()

    def _signup(self, email="otp-send@waseda.jp", username="otpsend", client=None):
        client = client or self.client
        return client.post(
            "/api/v1/auth/signup/",
            **_json(
                {
                    "email": email,
                    "password1": "test-pass-12345",
                    "password2": "test-pass-12345",
                    "accept_terms": True,
                }
            ),
        )

    def test_signup_email_limit_and_resend_shares_budget(self):
        first = self._signup()
        self.assertEqual(first.status_code, 201)
        for _ in range(AUTH_SIGNUP_OTP_EMAIL_LIMIT - 1):
            res = self.client.post("/api/v1/auth/verify/resend/", **_json({}))
            self.assertEqual(res.status_code, 200)
        self.assertEqual(len(mail.outbox), AUTH_SIGNUP_OTP_EMAIL_LIMIT)
        user = User.objects.get(email="otp-send@waseda.jp")
        otp = SignupOTP.objects.get(user=user)
        otp.failed_attempts = 2
        otp.save(update_fields=["failed_attempts"])
        hash_before = otp.code_hash

        blocked = self._signup(username="otpsend2")
        self.assertEqual(blocked.status_code, 429)
        self.assertEqual(blocked.json()["error"], "rate_limited")
        self.assertEqual(len(mail.outbox), AUTH_SIGNUP_OTP_EMAIL_LIMIT)

        resend = self.client.post("/api/v1/auth/verify/resend/", **_json({}))
        self.assertEqual(resend.status_code, 429)
        self.assertEqual(len(mail.outbox), AUTH_SIGNUP_OTP_EMAIL_LIMIT)
        otp.refresh_from_db()
        self.assertEqual(otp.failed_attempts, 2)
        self.assertEqual(otp.code_hash, hash_before)

        classic_resend = self.client.post(reverse("verify_otp_resend"))
        self.assertEqual(classic_resend.status_code, 302)
        otp.refresh_from_db()
        self.assertEqual(otp.failed_attempts, 2)
        self.assertEqual(otp.code_hash, hash_before)
        self.assertEqual(len(mail.outbox), AUTH_SIGNUP_OTP_EMAIL_LIMIT)

    def test_signup_classic_shares_api_budget(self):
        payload = {
            "email": "share@waseda.jp",
            "password1": "test-pass-12345",
            "password2": "test-pass-12345",
            "accept_terms": "on",
        }
        self.assertEqual(
            self._signup(email="share@waseda.jp", username="otpshare").status_code,
            201,
        )
        resend = self.client.post("/api/v1/auth/verify/resend/", **_json({}))
        self.assertEqual(resend.status_code, 200)
        classic = self.client.post(reverse("signup"), payload)
        self.assertEqual(classic.status_code, 302)
        blocked_api = self.client.post("/api/v1/auth/verify/resend/", **_json({}))
        self.assertEqual(blocked_api.status_code, 429)
        blocked_classic = self.client.post(
            reverse("signup"),
            payload,
        )
        self.assertEqual(blocked_classic.status_code, 429)
        self.assertContains(
            blocked_classic, RATE_LIMIT_USER_MESSAGE, status_code=429
        )
        self.assertEqual(len(mail.outbox), AUTH_SIGNUP_OTP_EMAIL_LIMIT)

    def test_signup_ip_limit(self):
        with patch("app.rate_limit_services.AUTH_SIGNUP_OTP_IP_LIMIT", 2):
            a = self._signup(email="ip-a@waseda.jp", username="otpipa")
            b = self._signup(email="ip-b@waseda.jp", username="otpipb")
            self.assertEqual(a.status_code, 201)
            self.assertEqual(b.status_code, 201)
            c = self._signup(email="ip-c@waseda.jp", username="otpipc")
            self.assertEqual(c.status_code, 429)
            self.assertEqual(len(mail.outbox), 2)
            self.assertFalse(User.objects.filter(email="ip-c@waseda.jp").exists())

    def test_signup_hourly_email_limit(self):
        with (
            patch("app.rate_limit_services.AUTH_SIGNUP_OTP_EMAIL_LIMIT", 10),
            patch("app.rate_limit_services.AUTH_SIGNUP_OTP_EMAIL_HOUR_LIMIT", 2),
        ):
            self.assertEqual(self._signup().status_code, 201)
            self.assertEqual(
                self.client.post("/api/v1/auth/verify/resend/", **_json({})).status_code,
                200,
            )
            blocked = self.client.post("/api/v1/auth/verify/resend/", **_json({}))
            self.assertEqual(blocked.status_code, 429)
            self.assertEqual(len(mail.outbox), 2)

    def test_signup_verify_http_limit_preserves_db_attempts(self):
        signup = self._signup(email="verify-rl@waseda.jp", username="otpverrl")
        self.assertEqual(signup.status_code, 201)
        user = User.objects.get(email="verify-rl@waseda.jp")
        last_err = ""
        for _ in range(OTP_MAX_ATTEMPTS):
            last_err = verify_signup_otp(user, "000000")
        self.assertIn("上限", last_err)
        self.assertFalse(SignupOTP.objects.filter(user=user).exists())

        cache.clear()
        create_and_send_signup_otp(user)
        session = self.client.session
        session[SIGNUP_PENDING_SESSION_KEY] = user.pk
        session.save()

        for _ in range(AUTH_OTP_VERIFY_ID_LIMIT):
            res = self.client.post(
                "/api/v1/auth/verify/",
                **_json({"code": "000000"}),
            )
            self.assertEqual(res.status_code, 400)
        blocked = self.client.post(
            "/api/v1/auth/verify/",
            **_json({"code": "000000"}),
        )
        self.assertEqual(blocked.status_code, 429)

    def test_signup_verify_classic_shares_api_budget(self):
        signup = self._signup(email="vshare@waseda.jp", username="vshareu")
        self.assertEqual(signup.status_code, 201)
        session = self.client.session
        session[SIGNUP_PENDING_SESSION_KEY] = User.objects.get(
            email="vshare@waseda.jp"
        ).pk
        session.save()
        for _ in range(10):
            self.client.post("/api/v1/auth/verify/", **_json({"code": "111111"}))
        for _ in range(10):
            self.client.post(reverse("verify_otp"), {"code": "111111"})
        blocked = self.client.post(
            "/api/v1/auth/verify/",
            **_json({"code": "111111"}),
        )
        self.assertEqual(blocked.status_code, 429)
        classic_blocked = self.client.post(reverse("verify_otp"), {"code": "111111"})
        self.assertEqual(classic_blocked.status_code, 429)


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DEFAULT_FROM_EMAIL="test@example.com",
    BROWSE_MODE_GATE_ENABLED=False,
)
class PasswordResetRateLimitTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = Client(REMOTE_ADDR="192.0.2.40")
        self.user = User.objects.create_user(
            email="reset-rl@waseda.jp",
            password="old-pass-12345",
            username="resetrl",
            is_active=True,
        )

    def tearDown(self):
        cache.clear()

    def _reset(self, email="reset-rl@waseda.jp"):
        return self.client.post(
            "/api/v1/auth/password-reset/",
            **_json({"email": email}),
        )

    def test_reset_issue_and_resend_share_budget(self):
        for _ in range(AUTH_RESET_OTP_EMAIL_LIMIT):
            res = self._reset()
            self.assertEqual(res.status_code, 200)
        self.assertEqual(len(mail.outbox), AUTH_RESET_OTP_EMAIL_LIMIT)
        otp = PasswordResetOTP.objects.get(user=self.user)
        otp.failed_attempts = 3
        otp.save(update_fields=["failed_attempts"])
        hash_before = otp.code_hash

        blocked = self._reset()
        self.assertEqual(blocked.status_code, 429)
        self.assertEqual(blocked.json()["error"], "rate_limited")
        self.assertEqual(len(mail.outbox), AUTH_RESET_OTP_EMAIL_LIMIT)

        resend = self.client.post(
            "/api/v1/auth/password-reset/resend/",
            **_json({}),
        )
        self.assertEqual(resend.status_code, 429)
        otp.refresh_from_db()
        self.assertEqual(otp.failed_attempts, 3)
        self.assertEqual(otp.code_hash, hash_before)
        self.assertIsNone(
            self.client.session.get(PASSWORD_RESET_VERIFIED_SESSION_KEY)
        )

    def test_reset_nonexistent_email_still_rate_limited_without_new_leak(self):
        missing = "nobody-rl@waseda.jp"
        for _ in range(AUTH_RESET_OTP_EMAIL_LIMIT):
            res = self._reset(email=missing)
            self.assertEqual(res.status_code, 400)
            self.assertEqual(res.json()["error"], "not_found")
        blocked = self._reset(email=missing)
        self.assertEqual(blocked.status_code, 429)
        self.assertEqual(blocked.json()["error"], "rate_limited")
        self.assertEqual(blocked.json()["message"], RATE_LIMIT_USER_MESSAGE)
        self.assertNotIn("登録されていません", blocked.json()["message"])
        self.assertEqual(len(mail.outbox), 0)

    def test_reset_classic_shares_api_budget(self):
        for _ in range(2):
            self.assertEqual(self._reset().status_code, 200)
        classic = self.client.post(
            reverse("password_reset_request"),
            {"email": "reset-rl@waseda.jp"},
        )
        self.assertEqual(classic.status_code, 302)
        blocked = self._reset()
        self.assertEqual(blocked.status_code, 429)
        classic_blocked = self.client.post(
            reverse("password_reset_request"),
            {"email": "reset-rl@waseda.jp"},
        )
        self.assertEqual(classic_blocked.status_code, 429)

    def test_reset_ip_limit(self):
        with patch("app.rate_limit_services.AUTH_RESET_OTP_IP_LIMIT", 2):
            User.objects.create_user(
                email="reset-ip-b@waseda.jp",
                password="old-pass-12345",
                username="resetipb",
            )
            a = self._reset(email="reset-rl@waseda.jp")
            b = self._reset(email="reset-ip-b@waseda.jp")
            self.assertEqual(a.status_code, 200)
            self.assertEqual(b.status_code, 200)
            c = self._reset(email="reset-rl@waseda.jp")
            self.assertEqual(c.status_code, 429)

    def test_reset_verify_http_limit(self):
        from app.otp_services import verify_password_reset_otp

        self.assertEqual(self._reset().status_code, 200)
        last_err = ""
        for _ in range(OTP_MAX_ATTEMPTS):
            last_err = verify_password_reset_otp(self.user, "000000")
        self.assertIn("上限", last_err)
        self.assertFalse(PasswordResetOTP.objects.filter(user=self.user).exists())

        cache.clear()
        self.assertEqual(self._reset().status_code, 200)
        session = self.client.session
        session[PASSWORD_RESET_USER_SESSION_KEY] = self.user.pk
        session.save()
        for _ in range(AUTH_OTP_VERIFY_ID_LIMIT):
            self.client.post(
                "/api/v1/auth/password-reset/verify/",
                **_json({"code": "000000"}),
            )
        blocked = self.client.post(
            "/api/v1/auth/password-reset/verify/",
            **_json({"code": "000000"}),
        )
        self.assertEqual(blocked.status_code, 429)
        classic_blocked = self.client.post(
            reverse("password_reset_verify"),
            {"code": "000000"},
        )
        self.assertEqual(classic_blocked.status_code, 429)
