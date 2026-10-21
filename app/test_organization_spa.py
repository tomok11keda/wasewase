"""Phase 1-C: organization profile SPA routes and source contracts."""

from __future__ import annotations

from pathlib import Path

from django.test import SimpleTestCase, TestCase, override_settings

ROOT = Path(__file__).resolve().parents[1]


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


class OrganizationSpaSourceTests(SimpleTestCase):
    def test_routes_are_registered_without_catch_all_collision(self):
        app = _read("frontend/src/App.tsx")
        nested = app.split("function NestedAppRoutes")[1].split("function AppRoutes")[0]
        self.assertIn('path="orgs/:slug/edit"', nested)
        self.assertIn('path="orgs/:slug"', nested)
        self.assertLess(
            nested.find('path="orgs/:slug/edit"'),
            nested.find('path="orgs/:slug"'),
        )
        self.assertLess(
            nested.find('path="orgs/:slug"'),
            nested.find('path="*"'),
        )
        self.assertIn('path="users/:userId"', nested)

    def test_chrome_titles_cover_org_routes(self):
        chrome = _read("frontend/src/lib/chrome.ts")
        self.assertIn('title: "団体"', chrome)
        self.assertIn('title: "団体を編集"', chrome)
        self.assertIn("/orgs/", chrome)

    def test_personal_verified_badge_rules_are_unchanged(self):
        badge = _read("frontend/src/components/VerifiedAccountBadge.tsx")
        self.assertIn('aria-label="WaseWase運営認証アカウント"', badge)
        self.assertIn("shouldShowVerifiedAccountBadge", badge)
        profile = _read("frontend/src/pages/ProfilePage.tsx")
        self.assertIn("is_operator_verified", profile)
        self.assertNotIn("is_verified", profile)
        self.assertNotIn("VerifiedOrganizationBadge", profile)

    def test_organization_badge_is_separate_from_personal_badge(self):
        org_badge = _read(
            "frontend/src/components/VerifiedOrganizationBadge.tsx"
        )
        self.assertIn("運営確認済み団体", org_badge)
        self.assertNotIn("WaseWase運営認証アカウント", org_badge)
        self.assertNotIn("is_operator_verified", org_badge)
        page = _read("frontend/src/pages/OrganizationProfilePage.tsx")
        self.assertIn("VerifiedOrganizationBadge", page)
        self.assertIn("is_verified", page)
        self.assertNotIn("is_operator_verified", page)

    def test_no_hardcoded_dummy_organization(self):
        page = _read("frontend/src/pages/OrganizationProfilePage.tsx")
        edit = _read("frontend/src/pages/OrganizationEditPage.tsx")
        self.assertNotIn("チームわせわせ", page)
        self.assertNotIn("チームわせわせ", edit)
        self.assertNotIn("team-wasewase", page)
        self.assertNotIn("team-wasewase", edit)

    def test_edit_uses_patch_and_formdata_without_content_type(self):
        http = _read("frontend/src/lib/http.ts")
        api = _read("frontend/src/features/orgs/api.ts")
        self.assertIn("export async function apiPatchJson", http)
        self.assertIn("export async function apiPatchForm", http)
        self.assertIn('method: "PATCH"', http)
        form_fn = http.split("export async function apiPatchForm")[1]
        self.assertNotIn("Content-Type", form_fn.split("export function mutationErrorMessage")[0])
        self.assertIn("new FormData()", api)
        self.assertIn("apiPatchForm", api)
        self.assertNotIn("slug", api.split("const fields")[1].split("const result")[0])
        self.assertNotIn("is_verified", api.split("const fields")[1].split("const result")[0])
        self.assertNotIn("status", api.split("const fields")[1].split("const result")[0])

    def test_profile_edit_is_gated_on_can_manage(self):
        page = _read("frontend/src/pages/OrganizationProfilePage.tsx")
        self.assertIn("payload.can_manage", page)
        self.assertIn("プロフィールを編集", page)
        edit = _read("frontend/src/pages/OrganizationEditPage.tsx")
        self.assertIn("permissionLost", edit)
        self.assertIn("disabled={busy || permissionLost}", edit)

    def test_org_pages_do_not_add_duplicate_back_rows(self):
        page = _read("frontend/src/pages/OrganizationProfilePage.tsx")
        edit = _read("frontend/src/pages/OrganizationEditPage.tsx")
        self.assertNotIn("profile-back", page)
        self.assertNotIn("←", page)
        self.assertNotIn("profile-back", edit)


@override_settings(WASE_REACT_SPA=True, BROWSE_MODE_GATE_ENABLED=False)
class OrganizationSpaShellTests(TestCase):
    def test_unknown_org_route_serves_spa_shell(self):
        res = self.client.get("/app/orgs/does-not-exist/")
        self.assertEqual(res.status_code, 200)
        body = res.content.decode("utf-8")
        self.assertIn('id="root"', body)
        self.assertNotIn("チームわせわせ", body)
        self.assertNotIn("下書き", body)

    def test_org_edit_route_serves_spa_shell(self):
        res = self.client.get("/app/orgs/does-not-exist/edit/")
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'id="root"', res.content)

    def test_user_profile_route_still_serves_spa_shell(self):
        res = self.client.get("/app/users/1/posts/")
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'id="root"', res.content)
