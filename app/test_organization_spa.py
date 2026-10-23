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

    def test_account_provider_is_inside_session_provider(self):
        app = _read("frontend/src/App.tsx")
        self.assertLess(app.find("<SessionProvider>"), app.find("<AccountProvider>"))
        self.assertLess(
            app.find("</AccountProvider>"), app.find("</SessionProvider>")
        )
        self.assertIn("from \"./lib/accountContext\"", app)

    def test_account_switcher_covers_menu_sidebar_and_mobile(self):
        menu = _read("frontend/src/components/AccountMenuContent.tsx")
        sidebar = _read("frontend/src/components/SidebarNav.tsx")
        header = _read("frontend/src/components/MobileShellHeader.tsx")
        drawer = _read("frontend/src/components/AccountDrawer.tsx")
        switcher = _read("frontend/src/components/AccountSwitcher.tsx")
        self.assertIn("AccountSwitcher", menu)
        self.assertIn("AccountSwitcher", sidebar)
        self.assertIn("AccountDrawer", drawer)
        self.assertIn("AccountMenuContent", drawer)
        self.assertIn("selectOrganization", switcher)
        self.assertIn("selectPersonal", switcher)
        self.assertNotIn("navigate(`/orgs/${selected.slug}`)", switcher)
        self.assertNotIn("navigate(`/users/${user.id}/posts`)", switcher)
        self.assertIn("onNavigate?.()", switcher)
        self.assertIn("accountSwitchMessage", switcher)
        self.assertIn("shouldLeaveOrganizationEdit", switcher)
        self.assertIn("organizationRoleLabel", switcher)
        self.assertIn("organizations.length === 0 && !error", switcher)
        self.assertIn("useAccount", header)
        self.assertIn("orgActor", header)
        self.assertIn("selectPersonal", menu)
        self.assertIn("selectPersonal", sidebar)
        self.assertIn("to={profilePath}", menu)
        self.assertIn("`/orgs/${orgActor.slug}/edit`", menu)
        self.assertIn("share-toast", switcher)
        helper = _read("frontend/src/features/orgs/accountSwitch.ts")
        self.assertIn("shouldLeaveOrganizationEdit", helper)
        self.assertIn("accountSwitchMessage", helper)

    def test_account_context_restores_only_after_list_load(self):
        ctx = _read("frontend/src/lib/accountContext.tsx")
        managed = _read("frontend/src/features/orgs/managedOrganizations.ts")
        api = _read("frontend/src/features/orgs/api.ts")
        self.assertIn("fetchManagedOrganizations", ctx)
        self.assertIn("resolveActiveOrganization", ctx)
        self.assertIn("listLoaded", ctx)
        self.assertIn("clearStoredOrganizationId", ctx)
        self.assertIn("wase_active_organization:", managed)
        self.assertIn("String(organizationId)", managed)
        self.assertNotIn("JSON.stringify", managed)
        self.assertIn("/api/v1/me/organizations/", api)
        fail = ctx.split("} catch {")[1].split("} finally")[0]
        self.assertIn('setError("load_failed")', fail)
        self.assertIn("setOrganizations([])", fail)
        self.assertIn('setActor({ type: "personal" })', fail)
        self.assertNotIn("readStoredOrganizationId", fail)

    def test_edit_forbidden_refreshes_managed_list(self):
        edit = _read("frontend/src/pages/OrganizationEditPage.tsx")
        self.assertIn("refreshOrganizations", edit)
        self.assertIn('err.code === "forbidden"', edit)
        self.assertIn("permissionLost", edit)
        self.assertIn('loadError === "not_found" || loadError === "forbidden"', edit)
        self.assertNotIn("load_failed", edit.split("refreshOrganizations")[-1][:400])

    def test_personal_surfaces_do_not_switch_to_organization_actor(self):
        for rel in (
            "frontend/src/features/timeline/TimelinePostCard.tsx",
            "frontend/src/pages/DmRoomPage.tsx",
            "frontend/src/pages/NotificationsPage.tsx",
            "frontend/src/pages/TimetablePage.tsx",
            "frontend/src/lib/session.tsx",
        ):
            source = _read(rel)
            with self.subTest(rel=rel):
                self.assertNotIn("useAccount", source)
                self.assertNotIn("AccountSwitcher", source)
        home = _read("frontend/src/pages/HomePage.tsx")
        self.assertIn("me.user.avatar_url", home)
        self.assertIn("createTimelinePost", home)
        self.assertIn("organizationIdForCompose", home)
        self.assertIn("ComposeIdentity", home)
        self.assertIn("actorMismatch", home)
        self.assertIn("disabled={composeBusy || actorMismatch}", home)
        submit = home.split("const submitCompose")[1]
        catch = submit.split("} catch (err)")[1].split("} finally")[0]
        self.assertNotIn("resetComposeDraft", catch)
        self.assertNotIn("organization_id: null", home)
        api = _read("frontend/src/features/timeline/api.ts")
        self.assertIn("個人名義への切り替えは自動では行いません", api)
        self.assertNotIn("PersonalPostingNote", home)
        compose = _read("frontend/src/features/timeline/composeActor.ts")
        self.assertIn("学生団体として投稿", compose)
        self.assertIn("個人アカウントとして投稿", compose)
        profile = _read("frontend/src/pages/OrganizationProfilePage.tsx")
        self.assertIn("fetchOrganizationPosts", profile)
        self.assertIn("TimelinePostCard", profile)
        self.assertIn("管理者プレビュー", profile)
        switcher = _read("frontend/src/components/AccountSwitcher.tsx")
        self.assertNotIn("現在、投稿は個人アカウントから行われます。", switcher)
        me_api = _read("frontend/src/lib/api.ts")
        self.assertIn("/api/v1/me/", me_api)
        self.assertNotIn("/api/v1/me/organizations/", me_api)


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
