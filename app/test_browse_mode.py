"""閲覧モード（ログイン入口ゲート）のテスト。"""

from django.test import Client, TestCase, override_settings
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

    def test_login_page_shows_browse_mode_cta(self):
        response = self.client.get(reverse("login"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "ログインせずに閲覧モードで始める")
        self.assertContains(response, reverse("enter_browse_mode"))

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
