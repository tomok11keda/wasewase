"""Official community verification: model, admin, API, seed."""

from __future__ import annotations

import json

from django.contrib.admin.sites import site
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.test import Client, RequestFactory, TestCase, override_settings
from django.urls import reverse

from .admin import CommunityAdmin
from .community_api_services import serialize_community
from .community_services import seed_communities
from .models import Community, CommunityThread, User

COMMUNITY_PUBLIC_KEYS = {
    "id",
    "slug",
    "name",
    "description",
    "faculty",
    "category",
    "is_official",
}


def _staff_user(*, email: str, with_change: bool) -> User:
    user = User.objects.create_user(
        email=email,
        password="test-pass-12345",
        is_staff=True,
    )
    if with_change:
        content_type = ContentType.objects.get_for_model(Community)
        user.user_permissions.add(
            Permission.objects.get(
                content_type=content_type, codename="view_community"
            ),
            Permission.objects.get(
                content_type=content_type, codename="change_community"
            ),
        )
    return user


@override_settings(BROWSE_MODE_GATE_ENABLED=False)
class CommunityOfficialModelTests(TestCase):
    def test_new_community_defaults_unofficial(self):
        community = Community.objects.create(
            slug="official-default-test",
            name="公式デフォルト確認",
        )
        community.refresh_from_db()
        self.assertIs(community.is_official, False)

    def test_official_save_and_revoke(self):
        community = Community.objects.create(
            slug="official-toggle-test",
            name="公式トグル",
        )
        community.is_official = True
        community.save(update_fields=["is_official"])
        community.refresh_from_db()
        self.assertTrue(community.is_official)

        community.is_official = False
        community.save(update_fields=["is_official"])
        community.refresh_from_db()
        self.assertFalse(community.is_official)

    def test_seeded_communities_start_unofficial(self):
        seed_communities()
        self.assertTrue(Community.objects.filter(is_active=True).exists())
        self.assertFalse(Community.objects.filter(is_official=True).exists())
        self.assertTrue(
            Community.objects.filter(is_official=False, is_active=True).exists()
        )


@override_settings(BROWSE_MODE_GATE_ENABLED=False)
class CommunityOfficialSeedTests(TestCase):
    def test_reseed_keeps_operator_official_flag(self):
        seed_communities()
        community = Community.objects.get(slug="commerce")
        community.is_official = True
        community.save(update_fields=["is_official"])

        seed_communities()
        community.refresh_from_db()
        self.assertTrue(community.is_official)
        self.assertEqual(community.name, "商学部板")
        self.assertTrue(community.is_active)

    def test_seed_defaults_omit_is_official_assignment(self):
        source = inspect_seed_source()
        self.assertIn("update_or_create", source)
        self.assertNotRegex(source, r'["\']is_official["\']\s*:')


def inspect_seed_source() -> str:
    from pathlib import Path

    text = Path(__file__).with_name("community_services.py").read_text(
        encoding="utf-8"
    )
    start = text.index("def seed_communities")
    end = text.index("\n\n\n", start)
    return text[start:end]


@override_settings(BROWSE_MODE_GATE_ENABLED=False)
class CommunityOfficialAdminTests(TestCase):
    def setUp(self):
        seed_communities()
        self.community = Community.objects.get(slug="commerce")
        self.factory = RequestFactory()
        self.model_admin = CommunityAdmin(Community, site)
        self.change_url = reverse(
            "admin:app_community_change", args=[self.community.pk]
        )

    def _form_data(self, *, official: bool) -> dict[str, str]:
        data = {
            "name": self.community.name,
            "slug": self.community.slug,
            "description": self.community.description,
            "category": self.community.category,
            "faculty": self.community.faculty,
            "latest_thread_title": self.community.latest_thread_title,
            "latest_thread_preview": self.community.latest_thread_preview,
            "sort_order": str(self.community.sort_order),
            "_save": "保存",
        }
        if self.community.is_active:
            data["is_active"] = "on"
        if official:
            data["is_official"] = "on"
        return data

    def test_admin_exposes_official_without_dropping_fields(self):
        listed = set(self.model_admin.list_display)
        self.assertIn("is_official", listed)
        self.assertIn("name", listed)
        self.assertIn("is_active", listed)
        self.assertIn("is_official", self.model_admin.list_filter)
        self.assertEqual(
            self.model_admin.search_fields, ("name", "slug", "description")
        )
        self.assertEqual(self.model_admin.prepopulated_fields, {"slug": ("name",)})
        self.assertFalse(getattr(self.model_admin, "list_editable", ()))
        flat_fields = [
            field
            for _name, opts in self.model_admin.fieldsets
            for field in opts["fields"]
        ]
        for required in (
            "name",
            "slug",
            "description",
            "category",
            "faculty",
            "is_official",
            "is_active",
            "sort_order",
            "latest_thread_title",
            "latest_thread_preview",
            "latest_activity_at",
        ):
            self.assertIn(required, flat_fields)

    def test_change_community_staff_can_toggle_official(self):
        staff = _staff_user(email="official-admin@waseda.jp", with_change=True)
        client = Client()
        client.force_login(staff)

        get_response = client.get(self.change_url)
        self.assertEqual(get_response.status_code, 200)
        self.assertContains(get_response, "公式認証")
        self.assertContains(get_response, "id_is_official")

        post_on = client.post(self.change_url, self._form_data(official=True))
        self.assertEqual(post_on.status_code, 302)
        self.community.refresh_from_db()
        self.assertTrue(self.community.is_official)

        post_off = client.post(self.change_url, self._form_data(official=False))
        self.assertEqual(post_off.status_code, 302)
        self.community.refresh_from_db()
        self.assertFalse(self.community.is_official)

    def test_admin_form_saves_official_flag(self):
        staff = _staff_user(email="official-form@waseda.jp", with_change=True)
        request = self.factory.post(self.change_url, self._form_data(official=True))
        request.user = staff
        Form = self.model_admin.get_form(request, obj=self.community)
        form = Form(self._form_data(official=True), instance=self.community)
        self.assertTrue(form.is_valid(), form.errors)
        saved = form.save()
        self.assertTrue(saved.is_official)

    def test_non_staff_cannot_change_official_via_admin(self):
        user = User.objects.create_user(
            email="official-user@waseda.jp",
            password="test-pass-12345",
        )
        client = Client()
        client.force_login(user)
        get_response = client.get(self.change_url)
        self.assertIn(get_response.status_code, (302, 403))
        post_response = client.post(self.change_url, self._form_data(official=True))
        self.assertIn(post_response.status_code, (302, 403))
        self.community.refresh_from_db()
        self.assertFalse(self.community.is_official)

    def test_staff_without_change_permission_cannot_toggle(self):
        staff = _staff_user(email="official-no-perm@waseda.jp", with_change=False)
        client = Client()
        client.force_login(staff)
        get_response = client.get(self.change_url)
        self.assertEqual(get_response.status_code, 403)
        post_response = client.post(self.change_url, self._form_data(official=True))
        self.assertEqual(post_response.status_code, 403)
        self.community.refresh_from_db()
        self.assertFalse(self.community.is_official)


@override_settings(BROWSE_MODE_GATE_ENABLED=False)
class CommunityOfficialApiTests(TestCase):
    def setUp(self):
        seed_communities()
        self.user = User.objects.create_user(
            email="official-api@waseda.jp",
            password="test-pass-12345",
        )
        self.community = Community.objects.get(slug="commerce")
        self.client = Client()
        self.thread = CommunityThread.objects.create(
            community=self.community,
            author=self.user,
            title="公式API確認スレッド",
            body="公式フラグの読み取り確認",
        )

    def _community_from_list(self) -> dict:
        response = self.client.get("/api/v1/communities/threads/")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        match = next(
            t for t in payload["threads"] if t["id"] == self.thread.pk
        )
        return match["community"]

    def _community_from_detail(self) -> dict:
        response = self.client.get(
            f"/api/v1/communities/{self.community.slug}/threads/{self.thread.pk}/"
        )
        self.assertEqual(response.status_code, 200)
        return response.json()["thread"]["community"]

    def test_serialize_community_keeps_existing_keys(self):
        payload = serialize_community(self.community)
        self.assertEqual(set(payload), COMMUNITY_PUBLIC_KEYS)
        self.assertIs(payload["is_official"], False)

        self.community.is_official = True
        self.community.save(update_fields=["is_official"])
        payload = serialize_community(self.community)
        self.assertIs(payload["is_official"], True)

    def test_list_and_detail_return_official_state(self):
        unofficial = self._community_from_list()
        self.assertEqual(set(unofficial), COMMUNITY_PUBLIC_KEYS)
        self.assertFalse(unofficial["is_official"])
        self.assertFalse(self._community_from_detail()["is_official"])

        self.community.is_official = True
        self.community.save(update_fields=["is_official"])
        self.assertTrue(self._community_from_list()["is_official"])
        self.assertTrue(self._community_from_detail()["is_official"])

    def _discover_community_thread(self, thread_id: int) -> dict:
        discover = self.client.get("/api/v1/search/")
        self.assertEqual(discover.status_code, 200)
        payload = discover.json().get("discover")
        self.assertIsInstance(payload, dict)
        communities = payload.get("communities") or []
        for row in communities:
            if row.get("kind") != "thread":
                continue
            thread = row.get("thread") or {}
            if thread.get("id") == thread_id:
                self.assertIn("community", thread)
                return thread
        self.fail(
            f"thread {thread_id} missing from discover.communities "
            f"({len(communities)} rows)"
        )

    def test_search_includes_is_official(self):
        self.community.is_official = True
        self.community.save(update_fields=["is_official"])
        search = self.client.get(
            "/api/v1/search/", {"q": "公式API確認スレッド"}
        )
        self.assertEqual(search.status_code, 200)
        threads = search.json()["threads"]
        match = next(t for t in threads if t["id"] == self.thread.pk)
        self.assertTrue(match["community"]["is_official"])

    def test_discover_returns_official_true_and_false(self):
        other = (
            Community.objects.exclude(pk=self.community.pk)
            .filter(is_active=True)
            .first()
        )
        self.assertIsNotNone(other)
        unofficial_thread = CommunityThread.objects.create(
            community=other,
            author=self.user,
            title="非公式Discoverスレッド",
            body="discover unofficial flag",
        )
        self.community.is_official = True
        self.community.save(update_fields=["is_official"])
        other.is_official = False
        other.save(update_fields=["is_official"])

        official = self._discover_community_thread(self.thread.pk)
        unofficial = self._discover_community_thread(unofficial_thread.pk)
        self.assertTrue(official["community"]["is_official"])
        self.assertFalse(unofficial["community"]["is_official"])

    def test_discover_unofficial_default(self):
        thread = self._discover_community_thread(self.thread.pk)
        self.assertFalse(thread["community"]["is_official"])

    def test_create_post_cannot_set_official(self):
        self.client.force_login(self.user)
        created = self.client.post(
            "/api/v1/communities/threads/",
            data=json.dumps(
                {
                    "title": "公式化できない",
                    "body": "is_official を混ぜても無視される",
                    "tag": self.community.faculty or "",
                    "is_official": True,
                    "community": {"is_official": True},
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(created.status_code, 201)
        thread = created.json()["thread"]
        self.assertIn("is_official", thread["community"])
        self.assertFalse(thread["community"]["is_official"])
        self.community.refresh_from_db()
        self.assertFalse(self.community.is_official)

    def test_create_post_cannot_revoke_official(self):
        self.community.is_official = True
        self.community.save(update_fields=["is_official"])
        self.client.force_login(self.user)
        created = self.client.post(
            "/api/v1/communities/threads/",
            data=json.dumps(
                {
                    "title": "公式解除できない",
                    "body": "false を送っても解除されない",
                    "tag": self.community.faculty or "",
                    "is_official": False,
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(created.status_code, 201)
        self.assertTrue(created.json()["thread"]["community"]["is_official"])
        self.community.refresh_from_db()
        self.assertTrue(self.community.is_official)

    def test_missing_community_write_endpoints(self):
        self.client.force_login(self.user)
        payload = json.dumps({"is_official": True})
        patch = self.client.patch(
            f"/api/v1/communities/{self.community.slug}/",
            data=payload,
            content_type="application/json",
        )
        put = self.client.put(
            f"/api/v1/communities/{self.community.slug}/",
            data=payload,
            content_type="application/json",
        )
        post = self.client.post(
            "/api/v1/communities/",
            data=payload,
            content_type="application/json",
        )
        self.assertNotEqual(patch.status_code, 200)
        self.assertNotEqual(put.status_code, 200)
        self.assertNotEqual(post.status_code, 200)
        self.community.refresh_from_db()
        self.assertFalse(self.community.is_official)

    def test_thread_reply_and_anonymity_unchanged(self):
        self.client.force_login(self.user)
        detail = self.client.get(
            f"/api/v1/communities/{self.community.slug}/threads/{self.thread.pk}/"
        )
        self.assertEqual(detail.status_code, 200)
        thread = detail.json()["thread"]
        self.assertEqual(thread["anonymous_label"], "ユーザー1")
        reply = self.client.post(
            f"/api/v1/communities/{self.community.slug}/threads/{self.thread.pk}/replies/",
            data=json.dumps({"body": "匿名返信"}),
            content_type="application/json",
        )
        self.assertEqual(reply.status_code, 201)
        self.assertEqual(reply.json()["reply"]["anonymous_label"], "ユーザー1")
        self.assertFalse("is_official" in reply.json()["reply"])
