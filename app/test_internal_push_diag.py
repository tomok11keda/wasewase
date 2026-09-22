"""Staff-only internal push diagnostics API. Never returns tokens."""

from __future__ import annotations

from django.test import Client, TestCase, override_settings
from django.urls import reverse

from app.models import DevicePushToken, User


PUSH_DIAG_URL = "/api/v1/internal/push-diag/"
FORBIDDEN_KEYS = (
    "token",
    "fcmPrefix",
    "fcm_prefix",
    "private_key",
    "email",
    "password",
    "cookie",
    "csrf",
)


def _assert_safe_payload(payload: dict) -> None:
    for key in FORBIDDEN_KEYS:
        assert key not in payload, key
    for value in payload.values():
        if isinstance(value, str) and len(value) >= 32:
            raise AssertionError("unexpected long string in push diag payload")


class InternalPushDiagApiTests(TestCase):
    def test_anonymous_is_404_not_payload(self):
        with override_settings(BROWSE_MODE_GATE_ENABLED=False):
            response = self.client.get(PUSH_DIAG_URL)
        self.assertEqual(response.status_code, 404)
        data = response.json()
        self.assertEqual(data, {"detail": "not_found"})
        self.assertNotIn("user_id", data)
        self.assertNotIn("device_push_token_count", data)

    def test_anonymous_with_browse_gate_is_404_not_401(self):
        with override_settings(BROWSE_MODE_GATE_ENABLED=True, WASE_REACT_SPA=True):
            response = self.client.get(PUSH_DIAG_URL)
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"detail": "not_found"})

    def test_regular_user_is_404(self):
        user = User.objects.create_user(
            email="push-diag-user@waseda.jp",
            password="test-pass-12345",
        )
        client = Client()
        client.force_login(user)
        response = client.get(PUSH_DIAG_URL)
        self.assertEqual(response.status_code, 404)
        data = response.json()
        self.assertEqual(data, {"detail": "not_found"})
        self.assertNotIn("user_id", data)

    def test_staff_ok_without_token_fields(self):
        user = User.objects.create_user(
            email="push-diag-staff@waseda.jp",
            password="test-pass-12345",
            is_staff=True,
        )
        DevicePushToken.objects.create(
            user=user,
            token="fcm-diag-placeholder-not-a-real-token",
            platform=DevicePushToken.Platform.IOS,
        )
        client = Client()
        client.force_login(user)
        response = client.get(reverse("api_v1_internal_push_diag"))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(
            set(data.keys()),
            {
                "ok",
                "authenticated",
                "user_id",
                "is_staff",
                "is_superuser",
                "device_push_token_count",
            },
        )
        self.assertTrue(data["ok"])
        self.assertTrue(data["authenticated"])
        self.assertEqual(data["user_id"], user.pk)
        self.assertTrue(data["is_staff"])
        self.assertFalse(data["is_superuser"])
        self.assertEqual(data["device_push_token_count"], 1)
        self.assertNotIn("email", data)
        _assert_safe_payload(data)

    def test_superuser_without_staff_ok(self):
        user = User.objects.create_user(
            email="push-diag-su@waseda.jp",
            password="test-pass-12345",
            is_staff=False,
            is_superuser=True,
        )
        client = Client()
        client.force_login(user)
        response = client.get(PUSH_DIAG_URL)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["user_id"], user.pk)
        self.assertTrue(data["is_superuser"])
        self.assertFalse(data["is_staff"])
        self.assertEqual(data["device_push_token_count"], 0)
        _assert_safe_payload(data)

    def test_me_includes_staff_flags_only(self):
        staff = User.objects.create_user(
            email="push-diag-me@waseda.jp",
            password="test-pass-12345",
            is_staff=True,
            is_superuser=True,
        )
        client = Client()
        client.force_login(staff)
        response = client.get("/api/v1/me/")
        data = response.json()
        self.assertTrue(data["is_staff"])
        self.assertTrue(data["is_superuser"])

        anon = self.client.get("/api/v1/me/")
        anon_data = anon.json()
        self.assertFalse(anon_data["is_staff"])
        self.assertFalse(anon_data["is_superuser"])
