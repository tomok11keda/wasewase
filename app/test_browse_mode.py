"""閲覧モード（ログイン入口ゲート）のテスト。"""

from pathlib import Path

from django.conf import settings
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from .browse_mode_services import BROWSE_MODE_SESSION_KEY


@override_settings(BROWSE_MODE_GATE_ENABLED=True)
class BrowseModeGateTests(TestCase):
    def setUp(self):
        self.client = Client()

    def test_anonymous_home_redirects_to_login(self):
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response["Location"])
        self.assertIn("next=", response["Location"])

    def test_login_page_does_not_expose_browse_mode_cta(self):
        response = self.client.get(reverse("login"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "ログイン")
        self.assertNotContains(response, "ログインせずに閲覧モードで始める")
        self.assertNotContains(response, reverse("enter_browse_mode"))

    def test_enter_browse_mode_enables_home(self):
        response = self.client.get(reverse("enter_browse_mode"))
        self.assertRedirects(response, reverse("home"))
        self.assertTrue(self.client.session.get(BROWSE_MODE_SESSION_KEY))

        home = self.client.get(reverse("home"))
        self.assertEqual(home.status_code, 200)
        self.assertContains(home, "閲覧モード")
        self.assertContains(home, "login-required-dialog")
        self.assertContains(home, "data-requires-login")

    def test_enter_browse_mode_respects_safe_next(self):
        response = self.client.get(
            reverse("enter_browse_mode"),
            {"next": reverse("flea_index")},
        )
        self.assertRedirects(response, reverse("flea_index"))
        flea = self.client.get(reverse("flea_index"))
        self.assertEqual(flea.status_code, 200)
        self.assertContains(flea, "閲覧モード")

    def test_browse_mode_flea_shows_exhibit_gate(self):
        self.client.get(reverse("enter_browse_mode"))
        response = self.client.get(reverse("flea_index"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "data-requires-login")
        self.assertContains(response, "出品")


@override_settings(BROWSE_MODE_GATE_ENABLED=True, WASE_REACT_SPA=True)
class BrowseModePublicEntryHiddenSpaTests(TestCase):
    def test_spa_login_does_not_expose_browse_cta(self):
        response = self.client.get("/app/login")
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "ログインせずに閲覧モードで始める")
        self.assertNotContains(response, reverse("enter_browse_mode"))

    def test_anonymous_app_home_redirects_to_spa_login(self):
        response = self.client.get("/app/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/app/login", response["Location"])


class BrowseModeFrontendBundleTests(SimpleTestCase):
    def test_spa_bundle_does_not_contain_browse_cta(self):
        bundle = Path(settings.BASE_DIR) / "static/frontend/assets/main.js"
        self.assertTrue(bundle.is_file(), bundle)
        text = bundle.read_text(encoding="utf-8")
        self.assertNotIn("ログインせずに閲覧モードで始める", text)
