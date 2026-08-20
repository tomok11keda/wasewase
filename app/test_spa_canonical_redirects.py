"""Classic GET pages redirect to React /app/* when WASE_REACT_SPA is on."""

from __future__ import annotations

from django.test import Client, TestCase, override_settings

from .models import User, UserProfile
from .notification_api_services import notification_spa_path
from .spa_canonical import (
    app_absolute,
    dm_room_url,
    product_detail_url,
    trade_chat_url,
    user_profile_url,
)


@override_settings(WASE_REACT_SPA=True, BROWSE_MODE_GATE_ENABLED=False)
class SpaCanonicalRedirectTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="spa-redir@waseda.jp",
            password="test-pass-12345",
            username="sparedir",
        )
        UserProfile.objects.update_or_create(
            user=self.user, defaults={"name": "Spa"}
        )
        self.client = Client()
        self.client.force_login(self.user)

    def _assert_redirects_to(self, path: str, expected: str):
        res = self.client.get(path)
        self.assertIn(res.status_code, (301, 302), msg=path)
        self.assertEqual(res.url, expected, msg=path)

    def test_core_page_redirects(self):
        cases = [
            ("/", "/app/"),
            ("/more/", "/app/more"),
            ("/flea/", "/app/flea"),
            ("/exhibit/", "/app/flea/exhibit"),
            ("/product/456/", "/app/flea/products/456"),
            ("/chat/123/", "/app/flea/chats/123"),
            ("/dm/", "/app/dm"),
            ("/dm/9/", "/app/dm/9"),
            ("/dm/groups/create/", "/app/dm/groups/new"),
            ("/dm/groups/4/", "/app/dm/groups/4"),
            ("/notifications/", "/app/notifications"),
            ("/search/", "/app/search"),
            ("/timetable/", "/app/timetable"),
            ("/timetable/user/7/", "/app/timetable/user/7"),
            ("/courses/12/", "/app/courses/12"),
            ("/courses/12/talk/", "/app/courses/12/talk"),
            ("/user/5/", "/app/users/5"),
            ("/communities/", "/app/communities"),
            ("/product/10/trade/", "/app/flea/products/10"),
            ("/login/", "/app/login"),
            ("/signup/", "/app/signup"),
        ]
        for src, dest in cases:
            self._assert_redirects_to(src, dest)

    def test_query_string_preserved(self):
        res = self.client.get("/chat/123/?from=push")
        self.assertEqual(res.status_code, 302)
        self.assertEqual(res.url, "/app/flea/chats/123?from=push")

        res = self.client.get("/search/?q=hello")
        self.assertEqual(res.status_code, 302)
        self.assertEqual(res.url, "/app/search?q=hello")

    def test_settings_and_report_not_forced_to_spa(self):
        """React-less pages must keep serving Classic (no SPA redirect)."""
        res = self.client.get("/mypage/settings/")
        self.assertEqual(res.status_code, 200)
        self.assertNotIn("/app/mypage", res.get("Location", ""))

        res = self.client.get("/mypage/edit/")
        self.assertEqual(res.status_code, 200)


@override_settings(WASE_REACT_SPA=False, BROWSE_MODE_GATE_ENABLED=False)
class SpaCanonicalDisabledTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="classic@waseda.jp",
            password="test-pass-12345",
            username="classic",
        )
        UserProfile.objects.update_or_create(
            user=self.user, defaults={"name": "Classic"}
        )
        self.client = Client()
        self.client.force_login(self.user)

    def test_classic_home_still_renders(self):
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        self.assertNotEqual(res.get("Location"), "/app/")

    def test_link_helpers_use_classic_paths(self):
        self.assertEqual(trade_chat_url(3), "/chat/3/")
        self.assertEqual(product_detail_url(4), "/product/4/")
        self.assertEqual(dm_room_url(5), "/dm/5/")
        self.assertEqual(user_profile_url(6), "/user/6/")


@override_settings(WASE_REACT_SPA=True)
class SpaLinkHelperTests(TestCase):
    def test_helpers_emit_app_urls(self):
        self.assertEqual(trade_chat_url(3), "/app/flea/chats/3")
        self.assertEqual(product_detail_url(4), "/app/flea/products/4")
        self.assertEqual(dm_room_url(5), "/app/dm/5")
        self.assertEqual(user_profile_url(6), "/app/users/6/posts")
        self.assertEqual(app_absolute("/flea"), "/app/flea")

    def test_notification_spa_path_covers_app_and_classic(self):
        self.assertEqual(notification_spa_path("/chat/7/"), "/flea/chats/7")
        self.assertEqual(
            notification_spa_path("/app/flea/chats/7"), "/flea/chats/7"
        )
        self.assertEqual(notification_spa_path("/exhibit/"), "/flea/exhibit")
        self.assertEqual(notification_spa_path("/more/"), "/more")
        self.assertEqual(notification_spa_path("/mypage/settings/"), "")
        self.assertEqual(notification_spa_path("/report/user/1/"), "")


@override_settings(WASE_REACT_SPA=True, BROWSE_MODE_GATE_ENABLED=False)
class CanonicalizeNextUrlTests(TestCase):
    def test_classic_next_maps_to_app(self):
        from .spa_canonical import canonicalize_next_url

        cases = [
            ("/chat/123/", "/app/flea/chats/123"),
            ("/product/123/", "/app/flea/products/123"),
            ("/dm/123/", "/app/dm/123"),
            ("/more/", "/app/more"),
            ("/flea/", "/app/flea"),
            ("/notifications/", "/app/notifications"),
            ("/search/", "/app/search"),
            ("/timetable/", "/app/timetable"),
            ("/user/5/", "/app/users/5/posts"),
            ("/communities/", "/app/communities"),
            ("/dm/groups/4/", "/app/dm/groups/4"),
            ("/courses/9/", "/app/courses/9"),
            ("/courses/9/talk/", "/app/courses/9/talk"),
            ("/courses/9/talk/?from=inbox", "/app/courses/9/talk?from=inbox"),
        ]
        for src, dest in cases:
            self.assertEqual(canonicalize_next_url(src), dest, msg=src)

    def test_app_next_preserved(self):
        from .spa_canonical import canonicalize_next_url

        self.assertEqual(
            canonicalize_next_url("/app/flea/chats/123"),
            "/app/flea/chats/123",
        )

    def test_query_string_preserved(self):
        from .spa_canonical import canonicalize_next_url

        self.assertEqual(
            canonicalize_next_url("/chat/123/?from=push"),
            "/app/flea/chats/123?from=push",
        )

    def test_external_urls_rejected(self):
        from .spa_canonical import canonicalize_next_url

        self.assertEqual(
            canonicalize_next_url("https://example.com"), "/app/"
        )
        self.assertEqual(canonicalize_next_url("//example.com"), "/app/")
        self.assertEqual(canonicalize_next_url("example.com"), "/app/")

    def test_unmapped_classic_kept(self):
        from .spa_canonical import canonicalize_next_url

        self.assertEqual(
            canonicalize_next_url("/mypage/settings/"),
            "/mypage/settings/",
        )

    def test_safe_next_url_via_login_api(self):
        from django.test import RequestFactory

        from .auth_api_services import safe_next_url

        req = RequestFactory().get("/api/v1/auth/login/")
        self.assertEqual(
            safe_next_url(req, "/chat/123/"), "/app/flea/chats/123"
        )
        self.assertEqual(
            safe_next_url(req, "/app/flea/chats/123"),
            "/app/flea/chats/123",
        )
        self.assertEqual(
            safe_next_url(req, "/chat/123/?from=push"),
            "/app/flea/chats/123?from=push",
        )
        self.assertEqual(safe_next_url(req, "https://example.com"), "/app/")
        self.assertEqual(safe_next_url(req, "//example.com"), "/app/")
