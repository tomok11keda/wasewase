"""Phase 1-B: organization profile GET/PATCH API."""

from __future__ import annotations

import json

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.test.client import BOUNDARY, MULTIPART_CONTENT, encode_multipart

from .models import Organization, OrganizationMember, User, UserProfile
from .organization_api_services import DESCRIPTION_MAX_LENGTH
from .organization_services import add_organization_member, can_manage_organization

_MINIMAL_GIF = (
    b"GIF89a\x01\x00\x01\x00\x80\x00\x00\xff\xff\xff\x00\x00\x00!\xf9\x04"
    b"\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"
)


def _make_user(email: str, **kwargs) -> User:
    kwargs.setdefault("password", "test-pass-12345")
    user = User.objects.create_user(email=email, **kwargs)
    UserProfile.objects.get_or_create(
        user=user,
        defaults={"name": email.split("@")[0]},
    )
    return user


def _make_org(**kwargs) -> Organization:
    kwargs.setdefault("name", "チームわせわせ")
    kwargs.setdefault("slug", "team-wasewase")
    kwargs.setdefault("description", "WaseWaseの学生団体")
    kwargs.setdefault("category", Organization.Category.PROJECT)
    kwargs.setdefault("status", Organization.Status.ACTIVE)
    kwargs.setdefault("is_listed", True)
    kwargs.setdefault("is_verified", False)
    return Organization.objects.create(**kwargs)


@override_settings(BROWSE_MODE_GATE_ENABLED=False)
class OrganizationProfileApiTests(TestCase):
    def setUp(self):
        self.owner = _make_user("org-owner@waseda.jp", username="orgowner")
        self.admin = _make_user("org-admin@waseda.jp", username="orgadmin")
        self.member = _make_user("org-member@waseda.jp", username="orgmember")
        self.outsider = _make_user("org-out@waseda.jp", username="orgout")
        self.other_owner = _make_user("other-owner@waseda.jp", username="otherowner")
        self.org = _make_org()
        add_organization_member(
            self.org, self.owner, role=OrganizationMember.Role.OWNER
        )
        add_organization_member(
            self.org, self.admin, role=OrganizationMember.Role.ADMIN
        )
        add_organization_member(
            self.org, self.member, role=OrganizationMember.Role.MEMBER
        )
        self.other = _make_org(name="別サークル", slug="other-circle", is_listed=True)
        add_organization_member(
            self.other, self.other_owner, role=OrganizationMember.Role.OWNER
        )
        self.client = Client()

    def _url(self, slug: str | None = None) -> str:
        return f"/api/v1/organizations/{slug or self.org.slug}/"

    def _patch_json(self, **payload):
        return self.client.patch(
            self._url(),
            data=json.dumps(payload),
            content_type="application/json",
        )

    def _assert_public_fields(self, data: dict, org: Organization):
        body = data["organization"]
        self.assertEqual(body["id"], org.pk)
        self.assertEqual(body["name"], org.name)
        self.assertEqual(body["slug"], org.slug)
        self.assertEqual(body["description"], org.description)
        self.assertEqual(body["category"], org.category)
        self.assertEqual(body["instagram_url"], org.instagram_url)
        self.assertEqual(body["website_url"], org.website_url)
        self.assertEqual(body["is_verified"], org.is_verified)
        self.assertIn("links", body)
        self.assertIsInstance(body["links"], list)
        self.assertIn("avatar_url", body)
        blob = json.dumps(data)
        self.assertNotIn("@waseda.jp", blob)
        self.assertNotIn("is_operator_verified", blob)
        self.assertNotIn("is_listed", blob)
        self.assertNotIn('"status"', blob)
        self.assertNotIn("memberships", blob)

    def test_get_active_listed_organization(self):
        res = self.client.get(self._url())
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data["ok"])
        self._assert_public_fields(data, self.org)
        self.assertFalse(data["can_manage"])
        self.assertIsNone(data["my_role"])

    def test_logged_in_member_gets_role_but_cannot_manage(self):
        self.client.force_login(self.member)
        res = self.client.get(self._url())
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertFalse(data["can_manage"])
        self.assertEqual(data["my_role"], OrganizationMember.Role.MEMBER)

    def test_get_active_unlisted_by_direct_url(self):
        self.org.is_listed = False
        self.org.save(update_fields=["is_listed"])
        res = self.client.get(self._url())
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["organization"]["slug"], self.org.slug)

    def test_get_is_case_insensitive_slug(self):
        res = self.client.get("/api/v1/organizations/Team-Wasewase/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["organization"]["slug"], "team-wasewase")

    def test_draft_owner_can_get(self):
        self.org.status = Organization.Status.DRAFT
        self.org.is_listed = False
        self.org.save(update_fields=["status", "is_listed"])
        self.client.force_login(self.owner)
        res = self.client.get(self._url())
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data["can_manage"])
        self.assertEqual(data["my_role"], OrganizationMember.Role.OWNER)

    def test_draft_unrelated_user_gets_404(self):
        self.org.status = Organization.Status.DRAFT
        self.org.is_listed = False
        self.org.save(update_fields=["status", "is_listed"])
        self.client.force_login(self.outsider)
        res = self.client.get(self._url())
        self.assertEqual(res.status_code, 404)
        self.assertEqual(res.json()["error"], "not_found")
        self.assertNotIn("WaseWaseの学生団体", json.dumps(res.json()))

    def test_draft_member_gets_404(self):
        self.org.status = Organization.Status.DRAFT
        self.org.save(update_fields=["status"])
        self.client.force_login(self.member)
        res = self.client.get(self._url())
        self.assertEqual(res.status_code, 404)

    def test_missing_organization_is_404(self):
        res = self.client.get("/api/v1/organizations/does-not-exist/")
        self.assertEqual(res.status_code, 404)
        self.assertEqual(res.json()["error"], "not_found")

    def test_suspended_owner_can_get_but_cannot_manage(self):
        self.org.status = Organization.Status.SUSPENDED
        self.org.save(update_fields=["status"])
        self.client.force_login(self.owner)
        res = self.client.get(self._url())
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertFalse(data["can_manage"])
        self.assertEqual(data["my_role"], OrganizationMember.Role.OWNER)
        self.assertFalse(can_manage_organization(self.owner, self.org))

    def test_suspended_unrelated_user_gets_404(self):
        self.org.status = Organization.Status.SUSPENDED
        self.org.save(update_fields=["status"])
        self.client.force_login(self.outsider)
        res = self.client.get(self._url())
        self.assertEqual(res.status_code, 404)

    def test_staff_can_get_draft_but_cannot_manage(self):
        staff = _make_user("org-staff@waseda.jp", is_staff=True, is_superuser=True)
        self.org.status = Organization.Status.DRAFT
        self.org.save(update_fields=["status"])
        self.client.force_login(staff)
        res = self.client.get(self._url())
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertFalse(data["can_manage"])
        self.assertIsNone(data["my_role"])
        patch = self._patch_json(name="運営による編集")
        self.assertEqual(patch.status_code, 403)

    def test_owner_can_update_profile(self):
        self.client.force_login(self.owner)
        res = self._patch_json(
            name="新しい団体名",
            description="更新後の説明",
            category=Organization.Category.CIRCLE,
            instagram_url="https://instagram.com/wasewase",
            website_url="https://wasewase.example/",
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data["ok"])
        self.assertTrue(data["can_manage"])
        self.assertEqual(data["my_role"], OrganizationMember.Role.OWNER)
        self.assertEqual(data["organization"]["name"], "新しい団体名")
        self.assertEqual(data["organization"]["description"], "更新後の説明")
        self.assertEqual(data["organization"]["category"], Organization.Category.CIRCLE)
        self.org.refresh_from_db()
        self.assertEqual(self.org.name, "新しい団体名")
        self.assertEqual(self.org.instagram_url, "https://instagram.com/wasewase")

    def test_admin_can_update_profile(self):
        self.client.force_login(self.admin)
        res = self._patch_json(description="管理者の更新")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["organization"]["description"], "管理者の更新")
        self.assertEqual(res.json()["my_role"], OrganizationMember.Role.ADMIN)

    def test_member_cannot_update(self):
        self.client.force_login(self.member)
        res = self._patch_json(name="メンバー編集")
        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.json()["error"], "forbidden")
        self.org.refresh_from_db()
        self.assertEqual(self.org.name, "チームわせわせ")

    def test_other_organization_admin_cannot_update(self):
        self.client.force_login(self.other_owner)
        res = self._patch_json(name="横取り")
        self.assertEqual(res.status_code, 403)
        self.org.refresh_from_db()
        self.assertEqual(self.org.name, "チームわせわせ")

    def test_unauthenticated_update_is_401(self):
        res = self._patch_json(name="ゲスト編集")
        self.assertEqual(res.status_code, 401)
        self.assertEqual(res.json()["error"], "unauthorized")

    def test_unauthenticated_draft_update_is_401_not_404(self):
        self.org.status = Organization.Status.DRAFT
        self.org.save(update_fields=["status"])
        res = self._patch_json(name="ゲスト編集")
        self.assertEqual(res.status_code, 401)

    def test_inactive_owner_cannot_update(self):
        self.owner.is_active = False
        self.owner.save(update_fields=["is_active"])
        self.client.force_login(self.owner)
        res = self._patch_json(name="停止ユーザー")
        # ModelBackend は is_active=False を未認証として扱うため 401 になる。
        self.assertEqual(res.status_code, 401)
        self.assertEqual(res.json()["error"], "unauthorized")
        self.org.refresh_from_db()
        self.assertEqual(self.org.name, "チームわせわせ")

    def test_suspended_owner_cannot_update(self):
        self.org.status = Organization.Status.SUSPENDED
        self.org.save(update_fields=["status"])
        self.client.force_login(self.owner)
        res = self._patch_json(name="停止中の編集")
        self.assertEqual(res.status_code, 403)
        self.org.refresh_from_db()
        self.assertEqual(self.org.name, "チームわせわせ")

    def test_unrelated_user_cannot_update_draft(self):
        self.org.status = Organization.Status.DRAFT
        self.org.save(update_fields=["status"])
        self.client.force_login(self.outsider)
        res = self._patch_json(name="下書き破壊")
        self.assertEqual(res.status_code, 404)
        self.assertNotIn("WaseWaseの学生団体", json.dumps(res.json()))

    def test_forbidden_fields_are_rejected(self):
        self.client.force_login(self.owner)
        original_slug = self.org.slug
        res = self._patch_json(
            name="許可される名前",
            slug="hacked-slug",
            status=Organization.Status.SUSPENDED,
            is_listed=False,
            is_verified=True,
        )
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["error"], "forbidden_field")
        self.assertEqual(
            set(res.json()["fields"]),
            {"slug", "status", "is_listed", "is_verified"},
        )
        self.org.refresh_from_db()
        self.assertEqual(self.org.slug, original_slug)
        self.assertFalse(self.org.is_verified)
        self.assertEqual(self.org.status, Organization.Status.ACTIVE)

    def test_unknown_fields_are_rejected(self):
        self.client.force_login(self.owner)
        res = self._patch_json(post_count=12)
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["error"], "unknown_field")
        self.assertEqual(res.json()["fields"], ["post_count"])

    def test_invalid_json_is_rejected(self):
        self.client.force_login(self.owner)
        res = self.client.patch(
            self._url(),
            data="{not-json",
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["error"], "invalid_json")

    def test_json_array_is_rejected(self):
        self.client.force_login(self.owner)
        res = self.client.patch(
            self._url(),
            data="[]",
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["error"], "invalid_json")

    def test_unsupported_content_type_is_rejected(self):
        self.client.force_login(self.owner)
        res = self.client.patch(
            self._url(),
            data="name=bad",
            content_type="text/plain",
        )
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["error"], "unsupported_media_type")

    def test_empty_name_is_rejected(self):
        self.client.force_login(self.owner)
        res = self._patch_json(name="   ")
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["error"], "validation")
        self.assertIn("name", res.json()["errors"])

    def test_null_name_is_rejected(self):
        self.client.force_login(self.owner)
        res = self._patch_json(name=None)
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["error"], "validation")

    def test_invalid_category_is_rejected(self):
        self.client.force_login(self.owner)
        res = self._patch_json(category="faculty")
        self.assertEqual(res.status_code, 400)
        self.assertIn("category", res.json()["errors"])

    def test_invalid_url_is_rejected(self):
        self.client.force_login(self.owner)
        res = self._patch_json(website_url="javascript:alert(1)")
        self.assertEqual(res.status_code, 400)
        self.assertIn("website_url", res.json()["errors"])
        res = self._patch_json(instagram_url="not-a-url")
        self.assertEqual(res.status_code, 400)
        self.assertIn("instagram_url", res.json()["errors"])

    def test_description_too_long_is_rejected(self):
        self.client.force_login(self.owner)
        res = self._patch_json(description="あ" * (DESCRIPTION_MAX_LENGTH + 1))
        self.assertEqual(res.status_code, 400)
        self.assertIn("description", res.json()["errors"])

    def test_empty_urls_clear_existing_values(self):
        self.org.website_url = "https://old.example/"
        self.org.save(update_fields=["website_url"])
        self.client.force_login(self.owner)
        res = self._patch_json(website_url="")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["organization"]["website_url"], "")

    def test_json_avatar_is_rejected(self):
        self.client.force_login(self.owner)
        res = self._patch_json(avatar="https://evil.example/x.png")
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["error"], "validation")
        self.assertIn("avatar", res.json()["errors"])

    def test_multipart_avatar_update(self):
        self.client.force_login(self.owner)
        image = SimpleUploadedFile("org.gif", _MINIMAL_GIF, content_type="image/gif")
        res = self.client.patch(
            self._url(),
            data=encode_multipart(
                BOUNDARY, {"name": "画像付き団体", "avatar": image}
            ),
            content_type=MULTIPART_CONTENT,
        )
        self.assertEqual(res.status_code, 200)
        self.org.refresh_from_db()
        self.assertEqual(self.org.name, "画像付き団体")
        self.assertTrue(self.org.avatar)
        self.assertTrue(res.json()["organization"]["avatar_url"])

    def test_invalid_image_is_rejected(self):
        self.client.force_login(self.owner)
        bad = SimpleUploadedFile(
            "notes.txt", b"not-an-image", content_type="text/plain"
        )
        res = self.client.patch(
            self._url(),
            data=encode_multipart(BOUNDARY, {"avatar": bad}),
            content_type=MULTIPART_CONTENT,
        )
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["error"], "validation")
        self.assertIn("avatar", res.json()["errors"])
        self.org.refresh_from_db()
        self.assertFalse(self.org.avatar)

    def test_csrf_failure_returns_json(self):
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.owner)
        res = csrf_client.patch(
            self._url(),
            data=json.dumps({"name": "CSRF欠落"}),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.json()["error"], "csrf_failed")
        self.org.refresh_from_db()
        self.assertEqual(self.org.name, "チームわせわせ")

    def test_does_not_change_user_profile_api(self):
        profile = self.client.get(f"/api/v1/profile/{self.owner.pk}/")
        self.assertEqual(profile.status_code, 200)
        payload = profile.json()
        self.assertEqual(payload["user"]["id"], self.owner.pk)
        self.assertNotIn("organization", payload)
        self.assertNotIn("organizations", payload)
        self.client.force_login(self.owner)
        self._patch_json(name="団体側だけ更新")
        profile_after = self.client.get(f"/api/v1/profile/{self.owner.pk}/")
        self.assertEqual(profile_after.status_code, 200)
        self.assertEqual(profile_after.json()["user"]["id"], self.owner.pk)
        self.owner.refresh_from_db()
        self.assertEqual(self.owner.email, "org-owner@waseda.jp")


@override_settings(BROWSE_MODE_GATE_ENABLED=False)
class OrganizationManagedListApiTests(TestCase):
    def setUp(self):
        self.owner = _make_user("list-owner@waseda.jp", username="listowner")
        self.admin = _make_user("list-admin@waseda.jp", username="listadmin")
        self.member = _make_user("list-member@waseda.jp", username="listmember")
        self.outsider = _make_user("list-out@waseda.jp", username="listout")
        self.org = _make_org(status=Organization.Status.DRAFT, is_listed=False)
        add_organization_member(
            self.org, self.owner, role=OrganizationMember.Role.OWNER
        )
        add_organization_member(
            self.org, self.admin, role=OrganizationMember.Role.ADMIN
        )
        add_organization_member(
            self.org, self.member, role=OrganizationMember.Role.MEMBER
        )
        self.other = _make_org(name="別サークル", slug="other-circle")
        self.other_owner = _make_user("list-other@waseda.jp", username="listother")
        add_organization_member(
            self.other, self.other_owner, role=OrganizationMember.Role.OWNER
        )
        self.client = Client()

    def _url(self) -> str:
        return "/api/v1/me/organizations/"

    def _ids(self, data: dict) -> list[int]:
        return [item["id"] for item in data.get("organizations", [])]

    def _assert_item_shape(self, item: dict, org: Organization, role: str):
        self.assertEqual(set(item.keys()), {
            "id",
            "name",
            "slug",
            "avatar_url",
            "is_verified",
            "my_role",
            "can_manage",
        })
        self.assertEqual(item["id"], org.pk)
        self.assertEqual(item["name"], org.name)
        self.assertEqual(item["slug"], org.slug)
        self.assertEqual(item["is_verified"], org.is_verified)
        self.assertEqual(item["my_role"], role)
        self.assertTrue(item["can_manage"])

    def test_owner_sees_draft_organization(self):
        self.client.force_login(self.owner)
        res = self.client.get(self._url())
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data["ok"])
        self.assertEqual(self._ids(data), [self.org.pk])
        self._assert_item_shape(
            data["organizations"][0], self.org, OrganizationMember.Role.OWNER
        )
        blob = json.dumps(data)
        self.assertNotIn("@waseda.jp", blob)
        self.assertNotIn("list-other@waseda.jp", blob)
        self.assertNotIn("is_operator_verified", blob)
        self.assertNotIn('"status"', blob)
        self.assertNotIn("memberships", blob)

    def test_owner_sees_active_organization(self):
        self.org.status = Organization.Status.ACTIVE
        self.org.is_listed = True
        self.org.save(update_fields=["status", "is_listed"])
        self.client.force_login(self.owner)
        res = self.client.get(self._url())
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(self._ids(data), [self.org.pk])
        self._assert_item_shape(
            data["organizations"][0], self.org, OrganizationMember.Role.OWNER
        )

    def test_query_param_cannot_select_another_user(self):
        self.client.force_login(self.outsider)
        res = self.client.get(self._url(), {"user_id": self.owner.pk})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["organizations"], [])
        self.assertNotIn(self.org.name, json.dumps(res.json()))

    def test_admin_sees_managed_organization(self):
        self.client.force_login(self.admin)
        res = self.client.get(self._url())
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(self._ids(data), [self.org.pk])
        self._assert_item_shape(
            data["organizations"][0], self.org, OrganizationMember.Role.ADMIN
        )

    def test_member_does_not_see_organization(self):
        self.client.force_login(self.member)
        res = self.client.get(self._url())
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["organizations"], [])

    def test_outsider_does_not_see_others_organization(self):
        self.client.force_login(self.outsider)
        res = self.client.get(self._url())
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["organizations"], [])
        self.assertNotIn(self.org.name, json.dumps(res.json()))

    def test_suspended_is_excluded(self):
        self.org.status = Organization.Status.SUSPENDED
        self.org.save(update_fields=["status"])
        self.client.force_login(self.owner)
        res = self.client.get(self._url())
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["organizations"], [])

    def test_staff_without_membership_does_not_gain_organizations(self):
        staff = _make_user(
            "list-staff@waseda.jp",
            username="liststaff",
            is_staff=True,
            is_superuser=True,
        )
        self.client.force_login(staff)
        res = self.client.get(self._url())
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["organizations"], [])

    def test_multiple_managed_organizations(self):
        second = _make_org(name="もう一つの団体", slug="second-org", is_listed=False)
        add_organization_member(
            second, self.owner, role=OrganizationMember.Role.ADMIN
        )
        self.client.force_login(self.owner)
        res = self.client.get(self._url())
        self.assertEqual(res.status_code, 200)
        ids = self._ids(res.json())
        self.assertEqual(set(ids), {self.org.pk, second.pk})
        self.assertNotIn(self.other.pk, ids)

    def test_unauthenticated_is_401(self):
        res = self.client.get(self._url())
        self.assertEqual(res.status_code, 401)
        data = res.json()
        self.assertEqual(data["error"], "unauthorized")
        self.assertNotIn(self.org.name, json.dumps(data))

    def test_me_payload_is_unchanged(self):
        self.client.force_login(self.owner)
        res = self.client.get("/api/v1/me/")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data["authenticated"])
        self.assertEqual(data["user"]["id"], self.owner.pk)
        self.assertNotIn("organizations", data)


@override_settings(BROWSE_MODE_GATE_ENABLED=True, WASE_REACT_SPA=True)
class OrganizationProfileBrowseModeTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.org = _make_org(slug="browse-circle", is_listed=True)

    def test_anonymous_without_browse_mode_is_401(self):
        res = self.client.get(f"/api/v1/organizations/{self.org.slug}/")
        self.assertEqual(res.status_code, 401)
        self.assertEqual(res.json()["error"], "unauthorized")
        self.assertNotIn(self.org.description, json.dumps(res.json()))

    def test_browse_mode_is_401(self):
        enter = self.client.post(
            "/api/v1/auth/browse/",
            data=json.dumps({"next": "/app/"}),
            content_type="application/json",
        )
        self.assertEqual(enter.status_code, 200)
        res = self.client.get(f"/api/v1/organizations/{self.org.slug}/")
        self.assertEqual(res.status_code, 401)
        self.assertEqual(res.json()["error"], "unauthorized")
        self.assertNotIn(self.org.description, json.dumps(res.json()))

    def test_logged_in_user_can_get_listed_organization(self):
        user = _make_user("browse-student@waseda.jp", username="browsestudent")
        self.client.force_login(user)
        res = self.client.get(f"/api/v1/organizations/{self.org.slug}/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["organization"]["slug"], self.org.slug)

    def test_managed_list_anonymous_and_browse_are_401(self):
        res = self.client.get("/api/v1/me/organizations/")
        self.assertEqual(res.status_code, 401)
        self.assertEqual(res.json()["error"], "unauthorized")
        enter = self.client.post(
            "/api/v1/auth/browse/",
            data=json.dumps({"next": "/app/"}),
            content_type="application/json",
        )
        self.assertEqual(enter.status_code, 200)
        browse = self.client.get("/api/v1/me/organizations/")
        self.assertEqual(browse.status_code, 401)
        self.assertEqual(browse.json()["error"], "unauthorized")
        self.assertNotIn(self.org.name, json.dumps(browse.json()))
