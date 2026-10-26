"""ProfileLink model, APIs, private-profile gating, and org URL copy."""

from __future__ import annotations

import ast
import importlib.util
import json
from pathlib import Path
from unittest.mock import patch

from django.apps import apps as django_apps
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from .models import Organization, OrganizationMember, ProfileLink, User, UserProfile
from .organization_services import add_organization_member
from .profile_link_services import (
    PROFILE_LINK_MAX,
    ProfileLinkError,
    replace_organization_profile_links,
    replace_user_profile_links,
    serialize_organization_links,
    validate_link_items,
)

_MIGRATION_0075_PATH = (
    Path(__file__).resolve().parent / "migrations" / "0075_profilelink.py"
)


def _load_migration_0075():
    spec = importlib.util.spec_from_file_location(
        "app_migrations_0075_profilelink", _MIGRATION_0075_PATH
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _make_user(email: str, **kwargs) -> User:
    kwargs.setdefault("password", "test-pass-12345")
    user = User.objects.create_user(email=email, **kwargs)
    UserProfile.objects.get_or_create(
        user=user,
        defaults={"name": kwargs.get("username") or email.split("@")[0]},
    )
    return user


def _make_org(**kwargs) -> Organization:
    kwargs.setdefault("name", "リンク団体")
    kwargs.setdefault("slug", "link-org")
    kwargs.setdefault("description", "紹介")
    kwargs.setdefault("category", Organization.Category.CIRCLE)
    kwargs.setdefault("status", Organization.Status.ACTIVE)
    kwargs.setdefault("is_listed", True)
    return Organization.objects.create(**kwargs)


class ProfileLinkModelTests(TestCase):
    def setUp(self):
        self.user = _make_user("link-owner@waseda.jp", username="linkowner")
        self.org = _make_org()

    def test_create_user_link_and_order(self):
        second = ProfileLink.objects.create(
            user=self.user,
            title="YouTube",
            url="https://youtube.com/@example",
            position=1,
        )
        first = ProfileLink.objects.create(
            user=self.user, title="X", url="https://x.com/example", position=0
        )
        urls = list(
            ProfileLink.objects.filter(user=self.user).values_list("url", flat=True)
        )
        self.assertEqual(urls, [first.url, second.url])

    def test_delete_user_removes_links(self):
        ProfileLink.objects.create(
            user=self.user, title="X", url="https://x.com/x", position=0
        )
        self.user.delete()
        self.assertFalse(ProfileLink.objects.exists())

    def test_delete_organization_removes_links(self):
        ProfileLink.objects.create(
            organization=self.org,
            title="公式",
            url="https://example.com",
            position=0,
        )
        self.org.delete()
        self.assertFalse(ProfileLink.objects.exists())

    def test_xor_owner_required(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ProfileLink.objects.create(
                    title="不正", url="https://example.com", position=0
                )

    def test_validate_rejects_dangerous_schemes_and_sixth(self):
        with self.assertRaises(ProfileLinkError):
            validate_link_items(
                [{"title": "xss", "url": "javascript:alert(1)"}]
            )
        with self.assertRaises(ProfileLinkError):
            validate_link_items([{"title": "data", "url": "data:text/html,hi"}])
        items = [
            {"title": f"L{i}", "url": f"https://example.com/{i}"}
            for i in range(PROFILE_LINK_MAX + 1)
        ]
        with self.assertRaises(ProfileLinkError):
            validate_link_items(items)

    def test_replace_enforces_max_and_order(self):
        replace_user_profile_links(
            self.user,
            [
                {"title": "B", "url": "https://b.example.com"},
                {"title": "A", "url": "https://a.example.com"},
            ],
        )
        replace_user_profile_links(
            self.user,
            [
                {"title": "A", "url": "https://a.example.com"},
                {"title": "B", "url": "https://b.example.com"},
            ],
        )
        rows = list(self.user.profile_links.all())
        self.assertEqual([row.title for row in rows], ["A", "B"])
        self.assertEqual([row.position for row in rows], [0, 1])
        too_many = [
            {"title": str(i), "url": f"https://example.com/{i}"}
            for i in range(6)
        ]
        with self.assertRaises(ProfileLinkError):
            replace_user_profile_links(self.user, too_many)
        self.assertEqual(self.user.profile_links.count(), 2)

    def test_duplicate_organization_position_rejected(self):
        ProfileLink.objects.create(
            organization=self.org,
            title="A",
            url="https://a.example",
            position=0,
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ProfileLink.objects.create(
                    organization=self.org,
                    title="B",
                    url="https://b.example",
                    position=0,
                )


class ProfileLinkMigrationCopyTests(TestCase):
    def test_copy_keeps_instagram_and_website_without_duplicate(self):
        org = _make_org(
            slug="copy-org",
            instagram_url="https://instagram.com/wasewase",
            website_url="https://example.com",
        )
        module = _load_migration_0075()
        module.copy_organization_legacy_urls(django_apps, None)
        rows = list(
            ProfileLink.objects.filter(organization=org).order_by("position", "pk")
        )
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0].title, "Instagram")
        self.assertEqual(rows[0].url, "https://instagram.com/wasewase")
        self.assertEqual(rows[0].position, 0)
        self.assertEqual(rows[1].title, "公式Webサイト")
        self.assertEqual(rows[1].url, "https://example.com")
        self.assertEqual(rows[1].position, 1)
        module.copy_organization_legacy_urls(django_apps, None)
        self.assertEqual(ProfileLink.objects.filter(organization=org).count(), 2)

    def test_copy_same_column_urls_once(self):
        org = _make_org(
            slug="dup-url-org",
            instagram_url="https://instagram.com/same",
            website_url="https://instagram.com/same",
        )
        module = _load_migration_0075()
        module.copy_organization_legacy_urls(django_apps, None)
        self.assertEqual(ProfileLink.objects.filter(organization=org).count(), 1)

    def test_migration_is_self_contained_and_warns_about_reverse(self):
        source = _MIGRATION_0075_PATH.read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported.append(node.module or "")
        self.assertFalse(
            any("profile_link_services" in name for name in imported),
            imported,
        )
        self.assertIn("apps.get_model", source)
        self.assertIn("Do not reverse this migration in production", source)
        self.assertIn("drops the ProfileLink table", source)

    def test_empty_database_copy_is_reproducible(self):
        self.assertEqual(ProfileLink.objects.count(), 0)
        org = _make_org(
            slug="empty-db-copy",
            instagram_url="https://instagram.com/empty",
            website_url="https://empty.example",
        )
        module = _load_migration_0075()
        module.copy_organization_legacy_urls(django_apps, None)
        first = list(
            ProfileLink.objects.filter(organization=org)
            .order_by("position", "pk")
            .values_list("title", "url", "position")
        )
        module.copy_organization_legacy_urls(django_apps, None)
        second = list(
            ProfileLink.objects.filter(organization=org)
            .order_by("position", "pk")
            .values_list("title", "url", "position")
        )
        self.assertEqual(
            first,
            [
                ("Instagram", "https://instagram.com/empty", 0),
                ("公式Webサイト", "https://empty.example", 1),
            ],
        )
        self.assertEqual(first, second)


@override_settings(BROWSE_MODE_GATE_ENABLED=False)
class UserProfileLinkApiTests(TestCase):
    def setUp(self):
        self.owner = _make_user("plink-me@waseda.jp", username="plinkme")
        self.other = _make_user("plink-you@waseda.jp", username="plinkyou")
        self.client = Client()

    def _me(self):
        return "/api/v1/me/profile/"

    def _profile(self, user):
        return f"/api/v1/profile/{user.pk}/"

    def _patch_me(self, **payload):
        return self.client.patch(
            self._me(),
            data=json.dumps(payload),
            content_type="application/json",
        )

    def test_owner_get_includes_links(self):
        replace_user_profile_links(
            self.owner,
            [{"title": "Instagram", "url": "https://instagram.com/me"}],
        )
        self.client.force_login(self.owner)
        res = self.client.get(self._me())
        self.assertEqual(res.status_code, 200)
        links = res.json()["profile"]["links"]
        self.assertEqual(len(links), 1)
        self.assertEqual(links[0]["title"], "Instagram")
        self.assertEqual(links[0]["url"], "https://instagram.com/me")
        public = self.client.get(self._profile(self.owner))
        self.assertEqual(public.json()["user"]["links"][0]["url"], links[0]["url"])

    def test_other_can_view_public_links_but_cannot_patch(self):
        replace_user_profile_links(
            self.owner,
            [{"title": "Web", "url": "https://example.com"}],
        )
        self.client.force_login(self.other)
        res = self.client.get(self._profile(self.owner))
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["user"]["links"][0]["url"], "https://example.com")
        patch = self._patch_me(
            links=[{"title": "Hack", "url": "https://evil.example"}]
        )
        self.assertEqual(patch.status_code, 200)
        self.assertEqual(self.other.profile_links.count(), 1)
        self.assertEqual(self.owner.profile_links.count(), 1)
        self.assertEqual(self.owner.profile_links.get().url, "https://example.com")

    def test_owner_can_add_edit_delete_and_reorder(self):
        self.client.force_login(self.owner)
        created = self._patch_me(
            links=[
                {"title": "IG", "url": "https://instagram.com/a"},
                {"title": "Web", "url": "https://example.com"},
            ]
        )
        self.assertEqual(created.status_code, 200)
        self.assertEqual(
            [item["title"] for item in created.json()["profile"]["links"]],
            ["IG", "Web"],
        )
        reordered = self._patch_me(
            links=[
                {"title": "Web", "url": "https://example.com"},
                {"title": "IG", "url": "https://instagram.com/a"},
            ]
        )
        self.assertEqual(
            [item["title"] for item in reordered.json()["profile"]["links"]],
            ["Web", "IG"],
        )
        cleared = self._patch_me(links=[])
        self.assertEqual(cleared.json()["profile"]["links"], [])
        self.assertEqual(self.owner.profile_links.count(), 0)

    def test_rejects_bad_url_and_sixth_link(self):
        self.client.force_login(self.owner)
        bad = self._patch_me(links=[{"title": "xss", "url": "javascript:alert(1)"}])
        self.assertEqual(bad.status_code, 400)
        too_many = self._patch_me(
            links=[
                {"title": str(i), "url": f"https://example.com/{i}"} for i in range(6)
            ]
        )
        self.assertEqual(too_many.status_code, 400)
        self.assertEqual(self.owner.profile_links.count(), 0)

    def test_private_profile_hides_links_from_strangers(self):
        UserProfile.objects.filter(user=self.owner).update(is_private=True)
        replace_user_profile_links(
            self.owner,
            [{"title": "Secret", "url": "https://secret.example"}],
        )
        self.client.force_login(self.other)
        res = self.client.get(self._profile(self.owner))
        self.assertEqual(res.status_code, 200)
        self.assertFalse(res.json()["can_view_content"])
        self.assertEqual(res.json()["user"]["links"], [])
        self.client.force_login(self.owner)
        own = self.client.get(self._profile(self.owner))
        self.assertEqual(own.json()["user"]["links"][0]["title"], "Secret")


@override_settings(BROWSE_MODE_GATE_ENABLED=False)
class OrganizationProfileLinkApiTests(TestCase):
    def setUp(self):
        cache.clear()
        limiter = patch(
            "app.organization_api_views.allow_organization_profile_update",
            return_value=True,
        )
        limiter.start()
        self.addCleanup(limiter.stop)
        self.addCleanup(cache.clear)
        self.owner = _make_user("olink-owner@waseda.jp", username="olinkowner")
        self.admin = _make_user("olink-admin@waseda.jp", username="olinkadmin")
        self.member = _make_user("olink-member@waseda.jp", username="olinkmember")
        self.outsider = _make_user("olink-out@waseda.jp", username="olinkout")
        self.org = _make_org(
            instagram_url="https://instagram.com/legacy",
            website_url="https://legacy.example",
        )
        add_organization_member(
            self.org, self.owner, role=OrganizationMember.Role.OWNER
        )
        add_organization_member(
            self.org, self.admin, role=OrganizationMember.Role.ADMIN
        )
        add_organization_member(
            self.org, self.member, role=OrganizationMember.Role.MEMBER
        )
        self.client = Client()

    def _url(self):
        return f"/api/v1/organizations/{self.org.slug}/"

    def _patch(self, **payload):
        return self.client.patch(
            self._url(),
            data=json.dumps(payload),
            content_type="application/json",
        )

    def test_get_exposes_unmigrated_column_urls_when_no_rows(self):
        res = self.client.get(self._url())
        self.assertEqual(res.status_code, 200)
        links = res.json()["organization"]["links"]
        urls = [item["url"] for item in links]
        self.assertIn("https://instagram.com/legacy", urls)
        self.assertIn("https://legacy.example", urls)
        titles = [item["title"] for item in links]
        self.assertIn("Instagram", titles)
        self.assertIn("公式Webサイト", titles)

    def test_get_does_not_merge_stale_columns_when_rows_exist(self):
        replace_organization_profile_links(
            self.org,
            [{"title": "YouTube", "url": "https://youtube.com/@kept"}],
        )
        self.org.instagram_url = "https://instagram.com/stale"
        self.org.website_url = "https://stale.example"
        self.org.save(update_fields=["instagram_url", "website_url"])
        res = self.client.get(self._url())
        self.assertEqual(res.status_code, 200)
        urls = [item["url"] for item in res.json()["organization"]["links"]]
        self.assertEqual(urls, ["https://youtube.com/@kept"])
        self.assertNotIn("https://instagram.com/stale", urls)
        self.assertNotIn("https://stale.example", urls)

    def test_owner_replace_links_syncs_legacy_columns_without_duplicate(self):
        self.client.force_login(self.owner)
        res = self._patch(
            links=[
                {"title": "Instagram", "url": "https://instagram.com/new"},
                {"title": "公式Webサイト", "url": "https://new.example"},
                {"title": "X", "url": "https://x.com/new"},
            ]
        )
        self.assertEqual(res.status_code, 200)
        body = res.json()["organization"]
        self.assertEqual(len(body["links"]), 3)
        self.assertEqual(body["instagram_url"], "https://instagram.com/new")
        self.assertEqual(body["website_url"], "https://new.example")
        urls = [item["url"] for item in body["links"]]
        self.assertEqual(len(urls), len(set(urls)))
        self.org.refresh_from_db()
        self.assertEqual(self.org.instagram_url, "https://instagram.com/new")
        self.assertEqual(self.org.profile_links.count(), 3)

    def test_admin_can_edit_member_cannot(self):
        self.client.force_login(self.admin)
        ok = self._patch(links=[{"title": "Web", "url": "https://admin.example"}])
        self.assertEqual(ok.status_code, 200)
        self.client.force_login(self.member)
        denied = self._patch(links=[{"title": "No", "url": "https://member.example"}])
        self.assertEqual(denied.status_code, 403)
        self.client.force_login(self.outsider)
        denied_out = self._patch(
            links=[{"title": "No", "url": "https://outsider.example"}]
        )
        self.assertEqual(denied_out.status_code, 403)
        self.assertEqual(
            ProfileLink.objects.filter(organization=self.org).get().url,
            "https://admin.example",
        )

    def test_legacy_instagram_patch_keeps_column_and_shows_link(self):
        self.client.force_login(self.owner)
        res = self._patch(instagram_url="https://instagram.com/column-only")
        self.assertEqual(res.status_code, 200)
        body = res.json()["organization"]
        self.assertEqual(body["instagram_url"], "https://instagram.com/column-only")
        urls = [item["url"] for item in body["links"]]
        self.assertIn("https://instagram.com/column-only", urls)
        self.assertEqual(
            self.org.profile_links.filter(url="https://instagram.com/column-only").count(),
            1,
        )

    def test_replace_does_not_duplicate_legacy_columns(self):
        self.client.force_login(self.owner)
        replace_organization_profile_links(
            self.org,
            [
                {"title": "Instagram", "url": "https://instagram.com/legacy"},
                {"title": "公式Webサイト", "url": "https://legacy.example"},
            ],
        )
        serialized = serialize_organization_links(self.org)
        urls = [item["url"] for item in serialized]
        self.assertEqual(urls.count("https://instagram.com/legacy"), 1)
        self.assertEqual(urls.count("https://legacy.example"), 1)

    def test_legacy_api_add_change_delete_instagram(self):
        self.client.force_login(self.owner)
        added = self._patch(instagram_url="https://instagram.com/added")
        self.assertEqual(added.status_code, 200)
        self.assertEqual(
            added.json()["organization"]["instagram_url"],
            "https://instagram.com/added",
        )
        changed = self._patch(instagram_url="https://instagram.com/changed")
        self.assertEqual(changed.status_code, 200)
        body = changed.json()["organization"]
        self.assertEqual(body["instagram_url"], "https://instagram.com/changed")
        urls = [item["url"] for item in body["links"]]
        self.assertIn("https://instagram.com/changed", urls)
        self.assertNotIn("https://instagram.com/added", urls)
        deleted = self._patch(instagram_url="")
        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(deleted.json()["organization"]["instagram_url"], "")
        self.assertNotIn(
            "https://instagram.com/changed",
            [item["url"] for item in deleted.json()["organization"]["links"]],
        )
        again = self.client.get(self._url())
        self.assertNotIn(
            "https://instagram.com/changed",
            [item["url"] for item in again.json()["organization"]["links"]],
        )

    def test_legacy_api_add_change_delete_website(self):
        self.client.force_login(self.owner)
        added = self._patch(website_url="https://added.example")
        self.assertEqual(added.status_code, 200)
        changed = self._patch(website_url="https://changed.example")
        self.assertEqual(changed.status_code, 200)
        self.assertEqual(
            changed.json()["organization"]["website_url"],
            "https://changed.example",
        )
        deleted = self._patch(website_url="")
        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(deleted.json()["organization"]["website_url"], "")
        self.assertEqual(
            [item["url"] for item in deleted.json()["organization"]["links"]],
            [],
        )

    def test_legacy_api_updates_both_columns_together(self):
        self.client.force_login(self.owner)
        res = self._patch(
            instagram_url="https://instagram.com/both",
            website_url="https://both.example",
        )
        self.assertEqual(res.status_code, 200)
        body = res.json()["organization"]
        self.assertEqual(body["instagram_url"], "https://instagram.com/both")
        self.assertEqual(body["website_url"], "https://both.example")
        urls = [item["url"] for item in body["links"]]
        self.assertEqual(
            urls,
            ["https://instagram.com/both", "https://both.example"],
        )

    def test_links_payload_wins_over_legacy_fields(self):
        self.client.force_login(self.owner)
        res = self._patch(
            links=[{"title": "YouTube", "url": "https://youtube.com/@canonical"}],
            instagram_url="https://instagram.com/ignored",
            website_url="https://ignored.example",
        )
        self.assertEqual(res.status_code, 200)
        body = res.json()["organization"]
        urls = [item["url"] for item in body["links"]]
        self.assertEqual(urls, ["https://youtube.com/@canonical"])
        self.assertNotIn("https://instagram.com/ignored", urls)
        self.assertEqual(body["instagram_url"], "")
        self.assertEqual(body["website_url"], "https://youtube.com/@canonical")

    def test_legacy_instagram_change_at_five_link_cap_updates_display(self):
        replace_organization_profile_links(
            self.org,
            [
                {"title": "Instagram", "url": "https://instagram.com/old-five"},
                *[
                    {"title": str(index), "url": f"https://kept.example/{index}"}
                    for index in range(PROFILE_LINK_MAX - 1)
                ],
            ],
        )
        self.client.force_login(self.owner)
        res = self._patch(instagram_url="https://instagram.com/new-five")
        self.assertEqual(res.status_code, 200)
        body = res.json()["organization"]
        self.assertEqual(body["instagram_url"], "https://instagram.com/new-five")
        urls = [item["url"] for item in body["links"]]
        self.assertEqual(len(urls), PROFILE_LINK_MAX)
        self.assertEqual(urls[0], "https://instagram.com/new-five")
        self.assertNotIn("https://instagram.com/old-five", urls)
        self.assertEqual(self.org.profile_links.count(), PROFILE_LINK_MAX)

    def test_legacy_add_rejected_at_five_link_cap(self):
        replace_organization_profile_links(
            self.org,
            [
                {"title": str(index), "url": f"https://kept.example/{index}"}
                for index in range(PROFILE_LINK_MAX)
            ],
        )
        kept = list(
            self.org.profile_links.order_by("position").values_list("url", flat=True)
        )
        self.client.force_login(self.owner)
        res = self._patch(instagram_url="https://instagram.com/sixth")
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["error"], "validation")
        self.assertIn("instagram_url", res.json()["errors"])
        self.org.refresh_from_db()
        self.assertEqual(
            list(
                self.org.profile_links.order_by("position").values_list("url", flat=True)
            ),
            list(kept),
        )
        get_res = self.client.get(self._url())
        self.assertNotIn(
            "https://instagram.com/sixth",
            [item["url"] for item in get_res.json()["organization"]["links"]],
        )

    def test_legacy_duplicate_url_does_not_create_second_row(self):
        replace_organization_profile_links(
            self.org,
            [{"title": "YouTube", "url": "https://example.com/same"}],
        )
        self.client.force_login(self.owner)
        res = self._patch(website_url="https://example.com/same")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(self.org.profile_links.count(), 1)
        urls = [item["url"] for item in res.json()["organization"]["links"]]
        self.assertEqual(urls, ["https://example.com/same"])

    def test_same_url_in_both_legacy_columns_creates_one_row(self):
        self.client.force_login(self.owner)
        res = self._patch(
            instagram_url="https://instagram.com/same-both",
            website_url="https://instagram.com/same-both",
        )
        self.assertEqual(res.status_code, 200)
        urls = [item["url"] for item in res.json()["organization"]["links"]]
        self.assertEqual(urls, ["https://instagram.com/same-both"])
        self.assertEqual(self.org.profile_links.count(), 1)

    def test_legacy_instagram_change_keeps_other_links_and_order(self):
        replace_organization_profile_links(
            self.org,
            [
                {"title": "Instagram", "url": "https://instagram.com/old"},
                {"title": "YouTube", "url": "https://youtube.com/@kept"},
                {"title": "X", "url": "https://x.com/kept"},
            ],
        )
        self.client.force_login(self.owner)
        res = self._patch(instagram_url="https://instagram.com/new")
        self.assertEqual(res.status_code, 200)
        titles = [item["title"] for item in res.json()["organization"]["links"]]
        urls = [item["url"] for item in res.json()["organization"]["links"]]
        self.assertEqual(titles, ["Instagram", "YouTube", "X"])
        self.assertEqual(
            urls,
            [
                "https://instagram.com/new",
                "https://youtube.com/@kept",
                "https://x.com/kept",
            ],
        )

    def test_legacy_clear_does_not_delete_unrelated_links(self):
        replace_organization_profile_links(
            self.org,
            [
                {"title": "Instagram", "url": "https://instagram.com/old"},
                {"title": "YouTube", "url": "https://youtube.com/@kept"},
            ],
        )
        self.client.force_login(self.owner)
        res = self._patch(instagram_url="")
        self.assertEqual(res.status_code, 200)
        urls = [item["url"] for item in res.json()["organization"]["links"]]
        self.assertEqual(urls, ["https://youtube.com/@kept"])

    def test_deleted_links_stay_gone_on_reget(self):
        self.client.force_login(self.owner)
        self._patch(
            links=[
                {"title": "Instagram", "url": "https://instagram.com/gone"},
                {"title": "Web", "url": "https://gone.example"},
            ]
        )
        cleared = self._patch(links=[])
        self.assertEqual(cleared.json()["organization"]["links"], [])
        self.org.refresh_from_db()
        self.assertEqual(self.org.instagram_url, "")
        self.assertEqual(self.org.website_url, "")
        again = self.client.get(self._url())
        self.assertEqual(again.json()["organization"]["links"], [])

    def test_partial_name_update_does_not_touch_links(self):
        replace_organization_profile_links(
            self.org,
            [{"title": "YouTube", "url": "https://youtube.com/@kept"}],
        )
        self.client.force_login(self.owner)
        res = self._patch(name="名前だけ変更")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["organization"]["name"], "名前だけ変更")
        urls = [item["url"] for item in res.json()["organization"]["links"]]
        self.assertEqual(urls, ["https://youtube.com/@kept"])


def _grant_model_perms(user: User, *models) -> None:
    for model in models:
        content_type = ContentType.objects.get_for_model(model)
        for action in ("add", "change", "delete", "view"):
            user.user_permissions.add(
                Permission.objects.get(
                    content_type=content_type,
                    codename=f"{action}_{model._meta.model_name}",
                )
            )


@override_settings(BROWSE_MODE_GATE_ENABLED=False)
class OrganizationProfileLinkAdminTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(
            email="plink-admin@waseda.jp",
            password="test-pass-12345",
            is_staff=True,
        )
        _grant_model_perms(
            self.staff, Organization, OrganizationMember, ProfileLink
        )
        self.client = Client()
        self.client.force_login(self.staff)
        self.org = _make_org(slug="admin-link-org")

    def _change_url(self):
        return reverse("admin:app_organization_change", args=[self.org.pk])

    def _payload(self, **overrides):
        data = {
            "name": self.org.name,
            "slug": self.org.slug,
            "description": self.org.description,
            "category": self.org.category,
            "instagram_url": "https://instagram.com/should-not-stick",
            "website_url": "https://should-not-stick.example",
            "status": self.org.status,
            "memberships-TOTAL_FORMS": "0",
            "memberships-INITIAL_FORMS": "0",
            "memberships-MIN_NUM_FORMS": "0",
            "memberships-MAX_NUM_FORMS": "1000",
            "profile_links-TOTAL_FORMS": "0",
            "profile_links-INITIAL_FORMS": "0",
            "profile_links-MIN_NUM_FORMS": "0",
            "profile_links-MAX_NUM_FORMS": "5",
            "_save": "保存",
        }
        if self.org.is_listed:
            data["is_listed"] = "on"
        data.update(overrides)
        return data

    def test_change_page_shows_readonly_legacy_columns(self):
        response = self.client.get(self._change_url())
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn("公開リンク（互換）", html)
        self.assertIn("プロフィールリンク", html)
        self.assertNotIn('name="instagram_url"', html)
        self.assertNotIn('name="website_url"', html)

    def test_posting_legacy_columns_does_not_diverge_from_profile_links(self):
        existing = ProfileLink.objects.create(
            organization=self.org,
            title="YouTube",
            url="https://youtube.com/@admin",
            position=0,
        )
        response = self.client.post(
            self._change_url(),
            self._payload(
                **{
                    "profile_links-TOTAL_FORMS": "1",
                    "profile_links-INITIAL_FORMS": "1",
                    "profile_links-0-id": str(existing.pk),
                    "profile_links-0-organization": str(self.org.pk),
                    "profile_links-0-title": "YouTube",
                    "profile_links-0-url": "https://youtube.com/@admin",
                    "profile_links-0-position": "0",
                }
            ),
        )
        self.assertEqual(response.status_code, 302)
        self.org.refresh_from_db()
        self.assertEqual(self.org.instagram_url, "")
        self.assertEqual(self.org.website_url, "https://youtube.com/@admin")
        self.assertEqual(self.org.profile_links.count(), 1)
        self.assertEqual(self.org.profile_links.get().url, "https://youtube.com/@admin")

    def test_saving_profile_link_inline_syncs_legacy_columns(self):
        response = self.client.post(
            self._change_url(),
            self._payload(
                **{
                    "profile_links-TOTAL_FORMS": "1",
                    "profile_links-INITIAL_FORMS": "0",
                    "profile_links-0-organization": str(self.org.pk),
                    "profile_links-0-title": "Instagram",
                    "profile_links-0-url": "https://instagram.com/admin-inline",
                    "profile_links-0-position": "0",
                }
            ),
        )
        self.assertEqual(response.status_code, 302)
        self.org.refresh_from_db()
        self.assertEqual(self.org.profile_links.count(), 1)
        self.assertEqual(
            self.org.profile_links.get().url, "https://instagram.com/admin-inline"
        )
        self.assertEqual(self.org.instagram_url, "https://instagram.com/admin-inline")
        self.assertEqual(self.org.website_url, "")

    def test_staff_without_permission_cannot_change_organization(self):
        staff = User.objects.create_user(
            email="no-org-perm@waseda.jp",
            password="test-pass-12345",
            is_staff=True,
        )
        client = Client()
        client.force_login(staff)
        response = client.get(self._change_url())
        self.assertIn(response.status_code, (302, 403))
        posted = client.post(
            self._change_url(),
            self._payload(
                **{
                    "profile_links-TOTAL_FORMS": "1",
                    "profile_links-INITIAL_FORMS": "0",
                    "profile_links-0-title": "Hack",
                    "profile_links-0-url": "https://evil.example",
                    "profile_links-0-position": "0",
                }
            ),
        )
        self.assertIn(posted.status_code, (302, 403))
        self.assertEqual(self.org.profile_links.count(), 0)

    def test_anonymous_is_redirected_from_organization_admin(self):
        response = Client().get(self._change_url())
        self.assertEqual(response.status_code, 302)
