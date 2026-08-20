"""React SPA Phase 1–2: feature flag isolation and /api/v1/me/."""

from __future__ import annotations

from django.test import Client, TestCase, override_settings
from django.urls import reverse

from .models import User


class SpaFeatureFlagTests(TestCase):
    def test_spa_404_when_flag_off(self):
        with override_settings(WASE_REACT_SPA=False, BROWSE_MODE_GATE_ENABLED=False):
            response = self.client.get("/app/")
        self.assertEqual(response.status_code, 404)

    def test_spa_serves_shell_when_flag_on(self):
        with override_settings(WASE_REACT_SPA=True, BROWSE_MODE_GATE_ENABLED=False):
            response = self.client.get("/app/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="root"')
        self.assertContains(response, "frontend/assets/main.js")
        # SPA must not load classic badge poll scripts (React owns badges)
        self.assertNotContains(response, "notification_badge.js")
        self.assertNotContains(response, "dm_badge.js")

    def test_spa_client_route_also_serves_shell(self):
        with override_settings(WASE_REACT_SPA=True, BROWSE_MODE_GATE_ENABLED=False):
            response = self.client.get("/app/flea")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="root"')

    def test_course_talk_spa_shell_and_classic_redirect(self):
        with override_settings(WASE_REACT_SPA=True, BROWSE_MODE_GATE_ENABLED=False):
            shell = self.client.get("/app/courses/42/talk")
            self.assertEqual(shell.status_code, 200)
            self.assertContains(shell, 'id="root"')

            classic = self.client.get("/courses/42/talk/")
            self.assertEqual(classic.status_code, 302)
            self.assertEqual(classic.url, "/app/courses/42/talk")

            detail = self.client.get("/courses/42/")
            self.assertEqual(detail.status_code, 302)
            self.assertEqual(detail.url, "/app/courses/42")

    def test_classic_home_redirects_to_spa_when_spa_on(self):
        with override_settings(WASE_REACT_SPA=True, BROWSE_MODE_GATE_ENABLED=False):
            response = self.client.get("/")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/app/")


class ApiV1MeTests(TestCase):
    def test_me_anonymous(self):
        with override_settings(BROWSE_MODE_GATE_ENABLED=False):
            response = self.client.get("/api/v1/me/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertFalse(data["authenticated"])
        self.assertIsNone(data["user"])

    def test_me_authenticated(self):
        user = User.objects.create_user(
            email="spa-phase@waseda.jp",
            password="test-pass-12345",
        )
        client = Client()
        client.force_login(user)
        response = client.get(reverse("api_v1_me"))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["authenticated"])
        self.assertEqual(data["user"]["id"], user.pk)
        self.assertEqual(data["user"]["email"], "spa-phase@waseda.jp")

    def test_auth_required_api_returns_json_401(self):
        with override_settings(BROWSE_MODE_GATE_ENABLED=False):
            response = self.client.get("/api/v1/notifications/")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response["Content-Type"].split(";")[0], "application/json")
        self.assertEqual(response.json()["error"], "unauthorized")

    def test_classic_home_still_redirects_html_when_gate_on(self):
        with override_settings(WASE_REACT_SPA=False, BROWSE_MODE_GATE_ENABLED=True):
            response = self.client.get("/")
        self.assertIn(response.status_code, (302, 301))
        self.assertIn("/login", response.url)
