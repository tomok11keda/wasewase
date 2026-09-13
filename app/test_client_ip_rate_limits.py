"""Launch-spike client IP + signup OTP rate-limit regressions."""

from __future__ import annotations

import json
from unittest.mock import patch

from django.core import mail
from django.core.cache import cache
from django.test import Client, RequestFactory, TestCase, override_settings

from app.models import SignupOTP, User
from app.otp_services import create_and_send_signup_otp
from app.rate_limit_services import (
    AUTH_LOGIN_ID_LIMIT,
    AUTH_LOGIN_IP_LIMIT,
    AUTH_OTP_VERIFY_IP_LIMIT,
    AUTH_SIGNUP_OTP_EMAIL_HOUR_LIMIT,
    AUTH_SIGNUP_OTP_EMAIL_LIMIT,
    AUTH_SIGNUP_OTP_IP_LIMIT,
    allow_login_rate_limit,
    allow_otp_verify_rate_limit,
    allow_signup_otp_send,
    client_ip,
)


def _json(payload: dict) -> dict:
    return {"data": json.dumps(payload), "content_type": "application/json"}


def _request(
    *,
    remote: str = "10.0.0.1",
    forwarded: str | None = None,
    cf_connecting: str | None = None,
    path: str = "/api/v1/auth/signup/",
):
    req = RequestFactory().post(path)
    req.META["REMOTE_ADDR"] = remote
    if forwarded is not None:
        req.META["HTTP_X_FORWARDED_FOR"] = forwarded
    if cf_connecting is not None:
        req.META["HTTP_CF_CONNECTING_IP"] = cf_connecting
    return req


@override_settings(RENDER_EXTERNAL_HOSTNAME="wasewase.onrender.com")
class ClientIpHelperTests(TestCase):
    def test_cf_connecting_ip_wins_over_xff(self):
        req = _request(
            remote="10.0.0.1",
            forwarded="1.1.1.1, 203.0.113.50",
            cf_connecting="8.8.8.8",
        )
        self.assertEqual(client_ip(req), "8.8.8.8")

    def test_xff_first_when_cf_missing(self):
        req = _request(remote="10.0.0.1", forwarded="8.8.8.8, 203.0.113.50")
        self.assertEqual(client_ip(req), "8.8.8.8")

    def test_spoof_looking_chain_uses_first_not_rightmost(self):
        req = _request(
            remote="10.0.0.1",
            forwarded="198.51.100.10, 8.8.8.8, 203.0.113.50",
        )
        self.assertEqual(client_ip(req), "198.51.100.10")

    def test_invalid_cf_falls_back_to_xff_first(self):
        req = _request(
            remote="10.0.0.1",
            forwarded="203.0.113.9, 8.8.8.8",
            cf_connecting="not-an-ip",
        )
        self.assertEqual(client_ip(req), "203.0.113.9")

    def test_cf_list_is_not_exactly_one_ip(self):
        req = _request(
            remote="10.0.0.1",
            forwarded="203.0.113.9, 8.8.8.8",
            cf_connecting="8.8.8.8, 1.1.1.1",
        )
        self.assertEqual(client_ip(req), "203.0.113.9")

    def test_invalid_cf_and_malformed_xff_first_uses_remote(self):
        req = _request(
            remote="198.51.100.20",
            forwarded="not-an-ip, 203.0.113.50",
            cf_connecting="???",
        )
        self.assertEqual(client_ip(req), "198.51.100.20")

    def test_missing_proxy_headers_uses_remote_addr(self):
        req = _request(remote="203.0.113.77")
        self.assertEqual(client_ip(req), "203.0.113.77")

    def test_ipv6_cf_address_normalized(self):
        req = _request(
            remote="10.0.0.1",
            forwarded="1.1.1.1, 203.0.113.50",
            cf_connecting="2001:db8::1",
        )
        self.assertEqual(client_ip(req), "2001:db8::1")

    def test_bracketed_ipv6_cf_address(self):
        req = _request(
            remote="10.0.0.1",
            forwarded="1.1.1.1",
            cf_connecting="[2001:db8::2]",
        )
        self.assertEqual(client_ip(req), "2001:db8::2")

    def test_ipv4_mapped_ipv6_cf_normalizes(self):
        req = _request(
            remote="10.0.0.1",
            forwarded="1.1.1.1",
            cf_connecting="::ffff:203.0.113.7",
        )
        self.assertEqual(client_ip(req), "203.0.113.7")

    def test_malformed_values_do_not_crash(self):
        req = RequestFactory().post("/x")
        req.META["REMOTE_ADDR"] = "203.0.113.9"
        req.META["HTTP_CF_CONNECTING_IP"] = "\x00"
        req.META["HTTP_X_FORWARDED_FOR"] = "foo, bar, ???"
        self.assertEqual(client_ip(req), "203.0.113.9")
        self.assertEqual(client_ip(None), "unknown")


class ClientIpUntrustedTests(TestCase):
    def test_non_render_ignores_cf_and_xff(self):
        req = _request(
            remote="203.0.113.9",
            forwarded="8.8.8.8, 1.1.1.1",
            cf_connecting="8.8.8.8",
        )
        self.assertEqual(client_ip(req), "203.0.113.9")


@override_settings(
    RENDER_EXTERNAL_HOSTNAME="wasewase.onrender.com",
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DEFAULT_FROM_EMAIL="test@example.com",
    BROWSE_MODE_GATE_ENABLED=False,
)
class SignupOtpLaunchSpikeTests(TestCase):
    def setUp(self):
        cache.clear()

    def tearDown(self):
        cache.clear()

    def test_published_limit_constants(self):
        self.assertEqual(AUTH_SIGNUP_OTP_IP_LIMIT, 250)
        self.assertEqual(AUTH_LOGIN_IP_LIMIT, 200)
        self.assertEqual(AUTH_OTP_VERIFY_IP_LIMIT, 400)
        self.assertEqual(AUTH_SIGNUP_OTP_EMAIL_LIMIT, 3)
        self.assertEqual(AUTH_SIGNUP_OTP_EMAIL_HOUR_LIMIT, 5)

    def test_distinct_cf_client_ips_do_not_share_bucket(self):
        with patch("app.rate_limit_services.AUTH_SIGNUP_OTP_IP_LIMIT", 2):
            req_a = _request(
                remote="10.0.0.1",
                forwarded="1.1.1.1, 203.0.113.50",
                cf_connecting="203.0.113.1",
            )
            req_b = _request(
                remote="10.0.0.1",
                forwarded="1.1.1.1, 203.0.113.50",
                cf_connecting="203.0.113.2",
            )
            self.assertTrue(allow_signup_otp_send(req_a, "a1@waseda.jp"))
            self.assertTrue(allow_signup_otp_send(req_a, "a2@waseda.jp"))
            self.assertFalse(allow_signup_otp_send(req_a, "a3@waseda.jp"))
            self.assertTrue(allow_signup_otp_send(req_b, "b1@waseda.jp"))

    def test_same_cf_client_ip_shares_bucket(self):
        with patch("app.rate_limit_services.AUTH_SIGNUP_OTP_IP_LIMIT", 2):
            req = _request(
                remote="10.0.0.1",
                forwarded="9.9.9.9, 203.0.113.50",
                cf_connecting="203.0.113.8",
            )
            self.assertTrue(allow_signup_otp_send(req, "s1@waseda.jp"))
            self.assertTrue(allow_signup_otp_send(req, "s2@waseda.jp"))
            self.assertFalse(allow_signup_otp_send(req, "s3@waseda.jp"))

    def test_shared_nat_not_limited_after_15(self):
        self.assertGreater(AUTH_SIGNUP_OTP_IP_LIMIT, 15)
        req = _request(
            remote="10.0.0.1",
            forwarded="203.0.113.80, 8.8.8.8",
            cf_connecting="203.0.113.80",
        )
        for i in range(16):
            self.assertTrue(
                allow_signup_otp_send(req, f"nat{i}@waseda.jp"),
                msg=f"request {i + 1} should be under the launch IP bucket",
            )

    def test_per_email_otp_limit_still_applies(self):
        req = _request(
            remote="10.0.0.1",
            forwarded="1.1.1.1",
            cf_connecting="203.0.113.81",
        )
        email = "same-student@waseda.jp"
        for _ in range(AUTH_SIGNUP_OTP_EMAIL_LIMIT):
            self.assertTrue(allow_signup_otp_send(req, email))
        self.assertFalse(allow_signup_otp_send(req, email))

    def test_signup_ip_policy_still_caps(self):
        req = _request(
            remote="10.0.0.1",
            forwarded="1.1.1.1, 8.8.8.8",
            cf_connecting="203.0.113.82",
        )
        with patch("app.rate_limit_services.AUTH_SIGNUP_OTP_IP_LIMIT", 3):
            self.assertTrue(allow_signup_otp_send(req, "ab1@waseda.jp"))
            self.assertTrue(allow_signup_otp_send(req, "ab2@waseda.jp"))
            self.assertTrue(allow_signup_otp_send(req, "ab3@waseda.jp"))
            self.assertFalse(allow_signup_otp_send(req, "ab4@waseda.jp"))

    def test_login_ip_policy_uses_cf_independently(self):
        with patch("app.rate_limit_services.AUTH_LOGIN_IP_LIMIT", 2):
            req_a = _request(
                remote="10.0.0.1",
                forwarded="1.1.1.1, 8.8.8.8",
                cf_connecting="198.51.100.1",
                path="/api/v1/auth/login/",
            )
            req_b = _request(
                remote="10.0.0.1",
                forwarded="1.1.1.1, 8.8.8.8",
                cf_connecting="198.51.100.2",
                path="/api/v1/auth/login/",
            )
            self.assertTrue(allow_login_rate_limit(req_a, "la@waseda.jp"))
            self.assertTrue(allow_login_rate_limit(req_a, "lb@waseda.jp"))
            self.assertFalse(allow_login_rate_limit(req_a, "lc@waseda.jp"))
            self.assertTrue(allow_login_rate_limit(req_b, "ld@waseda.jp"))

    def test_login_identifier_limit_unchanged(self):
        req = _request(
            remote="10.0.0.1",
            forwarded="1.1.1.1",
            cf_connecting="198.51.100.9",
            path="/api/v1/auth/login/",
        )
        email = "login-id@waseda.jp"
        for _ in range(AUTH_LOGIN_ID_LIMIT):
            self.assertTrue(allow_login_rate_limit(req, email))
        self.assertFalse(allow_login_rate_limit(req, email))

    def test_otp_verify_ip_policy_uses_cf_independently(self):
        with patch("app.rate_limit_services.AUTH_OTP_VERIFY_IP_LIMIT", 2):
            req_a = _request(
                remote="10.0.0.1",
                forwarded="1.1.1.1, 8.8.8.8",
                cf_connecting="203.0.113.21",
            )
            req_b = _request(
                remote="10.0.0.1",
                forwarded="1.1.1.1, 8.8.8.8",
                cf_connecting="203.0.113.22",
            )
            self.assertTrue(allow_otp_verify_rate_limit(req_a, "va@waseda.jp"))
            self.assertTrue(allow_otp_verify_rate_limit(req_a, "vb@waseda.jp"))
            self.assertFalse(allow_otp_verify_rate_limit(req_a, "vc@waseda.jp"))
            self.assertTrue(allow_otp_verify_rate_limit(req_b, "vd@waseda.jp"))

    def test_signup_http_success_with_cf_header(self):
        client = Client(
            REMOTE_ADDR="10.0.0.1",
            HTTP_X_FORWARDED_FOR="1.1.1.1, 203.0.113.50",
            HTTP_CF_CONNECTING_IP="203.0.113.40",
        )
        res = client.post(
            "/api/v1/auth/signup/",
            **_json(
                {
                    "email": "fwd-ok@waseda.jp",
                    "password1": "test-pass-12345",
                    "password2": "test-pass-12345",
                    "accept_terms": True,
                }
            ),
        )
        self.assertEqual(res.status_code, 201)
        self.assertTrue(res.json()["ok"])
        self.assertEqual(len(mail.outbox), 1)
        self.assertTrue(User.objects.filter(email="fwd-ok@waseda.jp").exists())


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DEFAULT_FROM_EMAIL="test@example.com",
    BROWSE_MODE_GATE_ENABLED=False,
)
class SignupOtpSmtpConsistencyTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            email="smtp-otp@waseda.jp",
            password="test-pass-12345",
            username="smtpotp",
            is_active=False,
        )

    def test_smtp_failure_restores_previous_otp(self):
        create_and_send_signup_otp(self.user)
        first = SignupOTP.objects.get(user=self.user)
        first_hash = first.code_hash
        first_expires = first.expires_at
        with patch("app.otp_services.send_mail", side_effect=OSError("smtp down")):
            with self.assertRaises(OSError):
                create_and_send_signup_otp(self.user)
        restored = SignupOTP.objects.get(user=self.user)
        self.assertEqual(restored.code_hash, first_hash)
        self.assertEqual(restored.expires_at, first_expires)

    def test_smtp_failure_on_first_send_does_not_leave_otp(self):
        with patch("app.otp_services.send_mail", side_effect=OSError("smtp down")):
            with self.assertRaises(OSError):
                create_and_send_signup_otp(self.user)
        self.assertFalse(SignupOTP.objects.filter(user=self.user).exists())

    def test_successful_resend_replaces_previous_otp(self):
        create_and_send_signup_otp(self.user)
        first_hash = SignupOTP.objects.get(user=self.user).code_hash
        create_and_send_signup_otp(self.user)
        second = SignupOTP.objects.get(user=self.user)
        self.assertNotEqual(second.code_hash, first_hash)
        self.assertEqual(len(mail.outbox), 2)
