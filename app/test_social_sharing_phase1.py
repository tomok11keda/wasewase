"""Phase 1 external sharing: canonical post route, next, privacy."""

from __future__ import annotations

import json

from django.test import Client, TestCase, override_settings

from .models import Product, TimelinePost, User, UserProfile
from .notification_api_services import notification_spa_path
from .spa_canonical import canonicalize_next_url, product_detail_url


@override_settings(WASE_REACT_SPA=True, BROWSE_MODE_GATE_ENABLED=False)
class CanonicalPostSpaShellTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="share-shell@waseda.jp",
            password="test-pass-12345",
            username="shareshell",
        )
        UserProfile.objects.update_or_create(
            user=self.user, defaults={"name": "Share"}
        )
        self.post = TimelinePost.objects.create(
            author=self.user,
            body="secret share body",
        )
        self.client = Client()
        self.client.force_login(self.user)

    def test_authenticated_posts_path_serves_spa_shell(self):
        res = self.client.get(f"/app/posts/{self.post.pk}")
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, 'id="root"')
        self.assertContains(res, "frontend/assets/main.js")
        self.assertNotContains(res, "secret share body")
        self.assertNotContains(res, "share-shell@waseda.jp")

    def test_authenticated_posts_path_refresh_still_serves_shell(self):
        first = self.client.get(f"/app/posts/{self.post.pk}")
        second = self.client.get(f"/app/posts/{self.post.pk}")
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertContains(second, 'id="root"')

    def test_flea_canonical_url_unchanged(self):
        product = Product.objects.create(
            seller=self.user,
            name="シェア商品",
            price=1000,
            category="other",
        )
        self.assertEqual(
            product_detail_url(product.pk),
            f"/app/flea/products/{product.pk}",
        )
        res = self.client.get(f"/app/flea/products/{product.pk}")
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, 'id="root"')


@override_settings(WASE_REACT_SPA=True, BROWSE_MODE_GATE_ENABLED=True)
class CanonicalPostAuthReturnTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="share-login@waseda.jp",
            password="test-pass-12345",
            username="sharelogin",
            is_active=True,
        )
        UserProfile.objects.update_or_create(
            user=self.user, defaults={"name": "Login"}
        )
        self.post = TimelinePost.objects.create(
            author=self.user,
            body="return-to-post body",
        )
        self.client = Client()

    def test_anonymous_posts_path_goes_to_login_with_next(self):
        res = self.client.get(f"/app/posts/{self.post.pk}")
        self.assertEqual(res.status_code, 302)
        location = res["Location"]
        self.assertIn("/app/login", location)
        self.assertIn(f"/app/posts/{self.post.pk}", location)
        self.assertIn("next=", location)

    def test_login_redirect_preserves_canonical_post_path(self):
        ok = self.client.post(
            "/api/v1/auth/login/",
            data=json.dumps(
                {
                    "email": "share-login@waseda.jp",
                    "password": "test-pass-12345",
                    "next": f"/app/posts/{self.post.pk}",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(ok.status_code, 200)
        self.assertTrue(ok.json()["ok"])
        self.assertEqual(ok.json()["redirect"], f"/app/posts/{self.post.pk}")

    def test_login_rejects_external_next_url(self):
        ok = self.client.post(
            "/api/v1/auth/login/",
            data=json.dumps(
                {
                    "email": "share-login@waseda.jp",
                    "password": "test-pass-12345",
                    "next": "https://evil.example/phish",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(ok.json()["redirect"], "/app/")

    def test_login_rejects_protocol_relative_next(self):
        ok = self.client.post(
            "/api/v1/auth/login/",
            data=json.dumps(
                {
                    "email": "share-login@waseda.jp",
                    "password": "test-pass-12345",
                    "next": "//evil.example/phish",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(ok.json()["redirect"], "/app/")


@override_settings(WASE_REACT_SPA=True, BROWSE_MODE_GATE_ENABLED=True)
class SharePrivacyTests(TestCase):
    def setUp(self):
        self.author = User.objects.create_user(
            email="share-priv@waseda.jp",
            password="test-pass-12345",
            username="sharepriv",
        )
        self.post = TimelinePost.objects.create(
            author=self.author,
            body="campus-only body",
        )
        self.client = Client()

    def test_anonymous_single_post_api_denied(self):
        res = self.client.get(f"/api/v1/timeline/{self.post.pk}/")
        self.assertEqual(res.status_code, 401)
        blob = json.dumps(res.json())
        self.assertNotIn("campus-only body", blob)
        self.assertNotIn("share-priv@waseda.jp", blob)

    def test_browse_mode_single_post_api_denied(self):
        browse = self.client.post(
            "/api/v1/auth/browse/",
            data=json.dumps({"next": f"/app/posts/{self.post.pk}"}),
            content_type="application/json",
        )
        self.assertEqual(browse.status_code, 200)
        self.assertTrue(browse.json()["me"]["is_browse_mode"])
        res = self.client.get(f"/api/v1/timeline/{self.post.pk}/")
        self.assertEqual(res.status_code, 401)
        blob = json.dumps(res.json())
        self.assertNotIn("campus-only body", blob)

    def test_removed_post_remains_unavailable(self):
        viewer = User.objects.create_user(
            email="share-viewer@waseda.jp",
            password="test-pass-12345",
            username="shareviewer",
        )
        self.client.force_login(viewer)
        self.post.is_removed = True
        self.post.save(update_fields=["is_removed"])
        res = self.client.get(f"/api/v1/timeline/{self.post.pk}/")
        self.assertEqual(res.status_code, 404)
        blob = json.dumps(res.json())
        self.assertNotIn("campus-only body", blob)


@override_settings(WASE_REACT_SPA=True)
class CanonicalShareUrlMappingTests(TestCase):
    def test_posts_path_maps_for_next(self):
        self.assertEqual(notification_spa_path("/posts/123"), "/posts/123")
        self.assertEqual(
            notification_spa_path("/app/posts/123"),
            "/posts/123",
        )
        self.assertEqual(
            canonicalize_next_url("/app/posts/123"),
            "/app/posts/123",
        )
        self.assertEqual(
            canonicalize_next_url("/posts/123"),
            "/app/posts/123",
        )

    def test_old_hash_post_behavior_still_supported(self):
        self.assertEqual(notification_spa_path("/#post-123"), "/#post-123")
        self.assertEqual(
            notification_spa_path("/app/#post-123"),
            "/#post-123",
        )
        self.assertEqual(
            canonicalize_next_url("/app/#post-123"),
            "/app/#post-123",
        )

    def test_external_next_rejected_by_canonicalize(self):
        self.assertEqual(canonicalize_next_url("https://evil.example"), "/app/")
        self.assertEqual(canonicalize_next_url("//evil.example"), "/app/")
        self.assertEqual(
            canonicalize_next_url("https://evil.example/app/posts/1"),
            "/app/",
        )

    def test_flea_canonical_mapping_unchanged(self):
        self.assertEqual(
            notification_spa_path("/flea/products/9"),
            "/flea/products/9",
        )
        self.assertEqual(
            canonicalize_next_url("/app/flea/products/9"),
            "/app/flea/products/9",
        )
        self.assertEqual(product_detail_url(9), "/app/flea/products/9")
