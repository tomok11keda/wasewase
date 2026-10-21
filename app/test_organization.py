"""Phase 1-A: Organization model, membership, and admin/operator split."""

from __future__ import annotations

import json

from django.contrib.admin.sites import site
from django.contrib.auth.models import AnonymousUser, Permission
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError, transaction
from django.forms.models import inlineformset_factory
from django.test import Client, RequestFactory, TestCase, override_settings
from django.urls import reverse

from .admin import (
    OrganizationAdmin,
    OrganizationMemberAdmin,
    OrganizationMemberInline,
    UserAdmin,
)
from .models import Community, Organization, OrganizationMember, User, UserProfile
from .organization_services import (
    LastOrganizationOwnerError,
    OrganizationMembershipError,
    add_organization_member,
    apply_organization_visibility_guard,
    can_list_organization,
    can_manage_organization,
    can_view_organization_profile,
    get_organization_membership_role,
    is_organization_admin,
    is_organization_owner,
    is_site_operator,
    organization_has_owner,
    remove_organization_member,
    save_organization_member_formset,
    set_organization_member_role,
)
from .services import user_is_operator_verified


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
    kwargs.setdefault("status", Organization.Status.DRAFT)
    kwargs.setdefault("is_listed", False)
    kwargs.setdefault("is_verified", False)
    return Organization.objects.create(**kwargs)


class OrganizationModelTests(TestCase):
    def test_create_organization(self):
        org = _make_org(description="WaseWaseの学生団体", category=Organization.Category.PROJECT)
        org.refresh_from_db()
        self.assertEqual(org.name, "チームわせわせ")
        self.assertEqual(org.slug, "team-wasewase")
        self.assertEqual(org.status, Organization.Status.DRAFT)
        self.assertFalse(org.is_listed)
        self.assertFalse(org.is_verified)
        self.assertIsNotNone(org.created_at)
        self.assertIsNotNone(org.updated_at)

    def test_slug_must_be_unique(self):
        _make_org(slug="team-wasewase")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Organization.objects.create(name="別団体", slug="team-wasewase")

    def test_slug_unique_is_case_insensitive(self):
        _make_org(slug="team-wasewase")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Organization.objects.create(name="別団体", slug="Team-Wasewase")

    def test_defaults_are_unpublished(self):
        org = Organization.objects.create(name="下書き団体", slug="draft-org")
        self.assertEqual(org.status, Organization.Status.DRAFT)
        self.assertFalse(org.is_listed)
        self.assertFalse(org.is_verified)

    def test_user_model_has_no_organization_fields(self):
        concrete = {field.name for field in User._meta.concrete_fields}
        self.assertIn("is_operator_verified", concrete)
        self.assertNotIn("organization", concrete)
        self.assertNotIn("is_verified", concrete)
        self.assertFalse(
            any(name.startswith("organization") for name in concrete)
        )


class OrganizationMemberTests(TestCase):
    def setUp(self):
        self.org = _make_org()
        self.owner = _make_user("owner@waseda.jp")
        self.admin = _make_user("admin@waseda.jp")
        self.outsider = _make_user("outsider@waseda.jp")

    def test_add_manager_without_changing_user(self):
        email = self.owner.email
        verified = self.owner.is_operator_verified
        member = add_organization_member(
            self.org, self.owner, role=OrganizationMember.Role.OWNER
        )
        self.owner.refresh_from_db()
        self.assertEqual(self.owner.email, email)
        self.assertIs(self.owner.is_operator_verified, verified)
        self.assertEqual(member.user_id, self.owner.pk)
        self.assertEqual(member.organization_id, self.org.pk)

    def test_one_user_can_manage_multiple_organizations(self):
        other = _make_org(name="別サークル", slug="other-circle")
        add_organization_member(
            self.org, self.owner, role=OrganizationMember.Role.OWNER
        )
        add_organization_member(
            other, self.owner, role=OrganizationMember.Role.OWNER
        )
        self.assertTrue(is_organization_owner(self.owner, self.org))
        self.assertTrue(is_organization_owner(self.owner, other))

    def test_organization_can_have_multiple_admins(self):
        add_organization_member(
            self.org, self.owner, role=OrganizationMember.Role.OWNER
        )
        add_organization_member(
            self.org, self.admin, role=OrganizationMember.Role.ADMIN
        )
        extra = _make_user("admin2@waseda.jp")
        add_organization_member(
            self.org, extra, role=OrganizationMember.Role.ADMIN
        )
        self.assertEqual(self.org.memberships.count(), 3)
        self.assertTrue(is_organization_admin(self.admin, self.org))
        self.assertTrue(is_organization_admin(extra, self.org))
        self.assertFalse(is_organization_owner(self.admin, self.org))

    def test_duplicate_membership_is_rejected(self):
        add_organization_member(
            self.org, self.owner, role=OrganizationMember.Role.OWNER
        )
        with self.assertRaises(OrganizationMembershipError) as raised:
            add_organization_member(
                self.org, self.owner, role=OrganizationMember.Role.ADMIN
            )
        self.assertEqual(raised.exception.code, "already_member")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                OrganizationMember.objects.create(
                    organization=self.org,
                    user=self.owner,
                    role=OrganizationMember.Role.ADMIN,
                )

    def test_unrelated_user_has_no_management_permission(self):
        add_organization_member(
            self.org, self.owner, role=OrganizationMember.Role.OWNER
        )
        self.assertFalse(is_organization_owner(self.outsider, self.org))
        self.assertFalse(is_organization_admin(self.outsider, self.org))
        self.assertFalse(can_manage_organization(self.outsider, self.org))

    def test_anonymous_user_cannot_manage(self):
        add_organization_member(
            self.org, self.owner, role=OrganizationMember.Role.OWNER
        )
        anonymous = AnonymousUser()
        self.assertFalse(is_organization_admin(anonymous, self.org))
        self.assertFalse(can_manage_organization(anonymous, self.org))

    def test_inactive_user_cannot_manage(self):
        add_organization_member(
            self.org, self.owner, role=OrganizationMember.Role.OWNER
        )
        self.owner.is_active = False
        self.owner.save(update_fields=["is_active"])
        self.assertFalse(is_organization_owner(self.owner, self.org))
        self.assertFalse(is_organization_admin(self.owner, self.org))
        self.assertFalse(can_manage_organization(self.owner, self.org))

    def test_owner_and_admin_permissions(self):
        add_organization_member(
            self.org, self.owner, role=OrganizationMember.Role.OWNER
        )
        add_organization_member(
            self.org, self.admin, role=OrganizationMember.Role.ADMIN
        )
        self.org.status = Organization.Status.ACTIVE
        self.org.save(update_fields=["status"])

        self.assertTrue(is_organization_owner(self.owner, self.org))
        self.assertTrue(is_organization_admin(self.owner, self.org))
        self.assertTrue(can_manage_organization(self.owner, self.org))

        self.assertFalse(is_organization_owner(self.admin, self.org))
        self.assertTrue(is_organization_admin(self.admin, self.org))
        self.assertTrue(can_manage_organization(self.admin, self.org))

        member = _make_user("member@waseda.jp")
        add_organization_member(
            self.org, member, role=OrganizationMember.Role.MEMBER
        )
        self.assertFalse(is_organization_admin(member, self.org))
        self.assertFalse(can_manage_organization(member, self.org))
        self.assertEqual(
            get_organization_membership_role(self.owner, self.org),
            OrganizationMember.Role.OWNER,
        )
        self.assertEqual(
            get_organization_membership_role(self.admin, self.org),
            OrganizationMember.Role.ADMIN,
        )
        self.assertEqual(
            get_organization_membership_role(member, self.org),
            OrganizationMember.Role.MEMBER,
        )
        self.assertIsNone(get_organization_membership_role(self.outsider, self.org))

    def test_staff_without_membership_is_not_organization_admin(self):
        staff = _make_user(
            "staff@waseda.jp",
            is_staff=True,
            is_superuser=True,
        )
        add_organization_member(
            self.org, self.owner, role=OrganizationMember.Role.OWNER
        )
        self.assertTrue(is_site_operator(staff))
        self.assertFalse(is_site_operator(self.owner))
        self.assertFalse(is_organization_admin(staff, self.org))
        self.assertFalse(can_manage_organization(staff, self.org))

    def test_suspended_organization_blocks_usual_management(self):
        add_organization_member(
            self.org, self.owner, role=OrganizationMember.Role.OWNER
        )
        add_organization_member(
            self.org, self.admin, role=OrganizationMember.Role.ADMIN
        )
        self.org.status = Organization.Status.SUSPENDED
        self.org.save(update_fields=["status"])

        self.assertTrue(is_organization_owner(self.owner, self.org))
        self.assertTrue(is_organization_admin(self.admin, self.org))
        self.assertFalse(can_manage_organization(self.owner, self.org))
        self.assertFalse(can_manage_organization(self.admin, self.org))

    def test_draft_organization_can_be_managed_by_owner(self):
        add_organization_member(
            self.org, self.owner, role=OrganizationMember.Role.OWNER
        )
        self.assertEqual(self.org.status, Organization.Status.DRAFT)
        self.assertTrue(can_manage_organization(self.owner, self.org))

    def test_last_owner_cannot_be_removed(self):
        member = add_organization_member(
            self.org, self.owner, role=OrganizationMember.Role.OWNER
        )
        with self.assertRaises(LastOrganizationOwnerError):
            member.delete()
        with self.assertRaises(LastOrganizationOwnerError):
            remove_organization_member(member)
        self.assertTrue(OrganizationMember.objects.filter(pk=member.pk).exists())

    def test_last_owner_cannot_be_demoted(self):
        member = add_organization_member(
            self.org, self.owner, role=OrganizationMember.Role.OWNER
        )
        with self.assertRaises(LastOrganizationOwnerError):
            set_organization_member_role(member, OrganizationMember.Role.ADMIN)
        member.refresh_from_db()
        self.assertEqual(member.role, OrganizationMember.Role.OWNER)

    def test_owner_can_be_removed_when_another_owner_exists(self):
        first = add_organization_member(
            self.org, self.owner, role=OrganizationMember.Role.OWNER
        )
        add_organization_member(
            self.org, self.admin, role=OrganizationMember.Role.OWNER
        )
        first.delete()
        self.assertFalse(OrganizationMember.objects.filter(pk=first.pk).exists())
        self.assertTrue(is_organization_owner(self.admin, self.org))

    def test_visibility_guard_reverts_active_without_owner(self):
        self.org.status = Organization.Status.ACTIVE
        self.org.is_listed = True
        self.org.save(update_fields=["status", "is_listed"])
        self.assertFalse(organization_has_owner(self.org))
        changed = apply_organization_visibility_guard(self.org)
        self.assertTrue(changed)
        self.org.refresh_from_db()
        self.assertEqual(self.org.status, Organization.Status.DRAFT)
        self.assertFalse(self.org.is_listed)

    def test_visibility_guard_keeps_active_when_owner_exists(self):
        add_organization_member(
            self.org, self.owner, role=OrganizationMember.Role.OWNER
        )
        self.org.status = Organization.Status.ACTIVE
        self.org.is_listed = True
        self.org.save(update_fields=["status", "is_listed"])
        self.assertFalse(apply_organization_visibility_guard(self.org))
        self.org.refresh_from_db()
        self.assertEqual(self.org.status, Organization.Status.ACTIVE)
        self.assertTrue(self.org.is_listed)


class OrganizationDeletionTests(TestCase):
    def test_user_delete_does_not_delete_organization(self):
        org = _make_org(slug="keep-org", name="残る団体")
        owner = _make_user("keep-owner@waseda.jp")
        extra = _make_user("keep-extra@waseda.jp")
        add_organization_member(org, owner, role=OrganizationMember.Role.OWNER)
        add_organization_member(org, extra, role=OrganizationMember.Role.ADMIN)
        owner_id = owner.pk

        owner.delete()

        org.refresh_from_db()
        self.assertEqual(org.name, "残る団体")
        self.assertFalse(
            OrganizationMember.objects.filter(
                organization=org, user_id=owner_id
            ).exists()
        )
        self.assertTrue(
            OrganizationMember.objects.filter(
                organization=org, user=extra
            ).exists()
        )

    def test_last_owner_user_delete_leaves_organization_without_owner(self):
        org = _make_org(slug="orphan-org", name="管理者不在")
        owner = _make_user("last-owner@waseda.jp")
        add_organization_member(org, owner, role=OrganizationMember.Role.OWNER)
        owner.delete()
        org.refresh_from_db()
        self.assertFalse(organization_has_owner(org))
        self.assertEqual(Organization.objects.filter(pk=org.pk).count(), 1)


class OrganizationBadgeIsolationTests(TestCase):
    def test_organization_verified_does_not_set_user_operator_badge(self):
        user = _make_user("badge@waseda.jp")
        org = _make_org(is_verified=True)
        add_organization_member(org, user, role=OrganizationMember.Role.OWNER)

        user.refresh_from_db()
        self.assertFalse(user.is_operator_verified)
        self.assertFalse(user_is_operator_verified(user))
        self.assertTrue(org.is_verified)

        user.is_operator_verified = True
        user.save(update_fields=["is_operator_verified"])
        org.is_verified = False
        org.save(update_fields=["is_verified"])
        user.refresh_from_db()
        org.refresh_from_db()
        self.assertTrue(user_is_operator_verified(user))
        self.assertFalse(org.is_verified)

    def test_community_official_flag_is_independent(self):
        community = Community.objects.create(
            slug="org-badge-isolation",
            name="掲示板",
            is_official=True,
        )
        org = _make_org(slug="org-not-community", is_verified=False)
        community.refresh_from_db()
        org.refresh_from_db()
        self.assertTrue(community.is_official)
        self.assertFalse(org.is_verified)


class OrganizationAdminTests(TestCase):
    def test_admin_exposes_organization_and_keeps_user_badge(self):
        self.assertIn(Organization, site._registry)
        self.assertIn(OrganizationMember, site._registry)
        self.assertIn(User, site._registry)

        org_admin = OrganizationAdmin(Organization, site)
        listed = set(org_admin.list_display)
        for required in (
            "name",
            "slug",
            "status",
            "is_listed",
            "is_verified",
        ):
            self.assertIn(required, listed)
        self.assertIn("status", org_admin.list_filter)
        self.assertIn("is_listed", org_admin.list_filter)
        self.assertIn("is_verified", org_admin.list_filter)

        user_admin = UserAdmin(User, site)
        self.assertIn("is_operator_verified", user_admin.list_display)
        self.assertIn("is_operator_verified", user_admin.list_filter)
        badge_fields = [
            field
            for _name, opts in user_admin.fieldsets
            for field in opts["fields"]
        ]
        self.assertIn("is_operator_verified", badge_fields)
        self.assertEqual(user_admin.search_fields, ("email", "username"))

    def test_member_inline_uses_autocomplete_not_raw_id(self):
        inline = OrganizationMemberInline(Organization, site)
        self.assertEqual(inline.autocomplete_fields, ("user",))
        self.assertEqual(getattr(inline, "raw_id_fields", ()), ())
        self.assertEqual(inline.get_extra(request=None, obj=None), 1)
        self.assertEqual(inline.get_extra(request=None, obj=_make_org(slug="extra-check")), 0)

    def test_add_formset_defaults_role_to_owner(self):
        inline = OrganizationMemberInline(Organization, site)
        request = RequestFactory().get("/admin/app/organization/add/")
        request.user = _org_staff("inline-formset@waseda.jp")
        formset = inline.get_formset(request, obj=None)
        self.assertEqual(
            formset.form.base_fields["role"].initial,
            OrganizationMember.Role.OWNER,
        )

    def test_slug_is_readonly_after_create(self):
        org = _make_org()
        org_admin = OrganizationAdmin(Organization, site)
        self.assertNotIn("slug", org_admin.get_readonly_fields(request=None, obj=None))
        self.assertIn("slug", org_admin.get_readonly_fields(request=None, obj=org))


class OrganizationVisibilityPolicyTests(TestCase):
    def setUp(self):
        self.org = _make_org()
        self.owner = _make_user("vis-owner@waseda.jp")
        self.outsider = _make_user("vis-out@waseda.jp")
        self.staff = _make_user("vis-staff@waseda.jp", is_staff=True)
        add_organization_member(
            self.org, self.owner, role=OrganizationMember.Role.OWNER
        )

    def test_draft_is_only_for_managers_and_operators(self):
        self.org.status = Organization.Status.DRAFT
        self.org.is_listed = False
        self.org.save(update_fields=["status", "is_listed"])
        self.assertTrue(can_view_organization_profile(self.owner, self.org))
        self.assertTrue(can_view_organization_profile(self.staff, self.org))
        self.assertFalse(can_view_organization_profile(self.outsider, self.org))
        self.assertFalse(can_view_organization_profile(AnonymousUser(), self.org))
        self.assertFalse(can_list_organization(self.org))

    def test_active_unlisted_is_viewable_but_not_listed(self):
        self.org.status = Organization.Status.ACTIVE
        self.org.is_listed = False
        self.org.save(update_fields=["status", "is_listed"])
        self.assertTrue(can_view_organization_profile(AnonymousUser(), self.org))
        self.assertTrue(can_view_organization_profile(self.outsider, self.org))
        self.assertFalse(can_list_organization(self.org))

    def test_active_listed_is_public(self):
        self.org.status = Organization.Status.ACTIVE
        self.org.is_listed = True
        self.org.save(update_fields=["status", "is_listed"])
        self.assertTrue(can_view_organization_profile(AnonymousUser(), self.org))
        self.assertTrue(can_list_organization(self.org))

    def test_suspended_is_hidden_from_general_users(self):
        self.org.status = Organization.Status.SUSPENDED
        self.org.is_listed = True
        self.org.save(update_fields=["status", "is_listed"])
        self.assertTrue(can_view_organization_profile(self.owner, self.org))
        self.assertTrue(can_view_organization_profile(self.staff, self.org))
        self.assertFalse(can_view_organization_profile(self.outsider, self.org))
        self.assertFalse(can_view_organization_profile(AnonymousUser(), self.org))
        self.assertFalse(can_list_organization(self.org))


class OrganizationOwnerProtectionTests(TestCase):
    def setUp(self):
        self.org = _make_org()
        self.owner = _make_user("prot-owner@waseda.jp")
        self.other = _make_user("prot-other@waseda.jp")
        self.member = add_organization_member(
            self.org, self.owner, role=OrganizationMember.Role.OWNER
        )

    def test_queryset_delete_rejects_last_owner(self):
        with self.assertRaises(LastOrganizationOwnerError):
            OrganizationMember.objects.filter(pk=self.member.pk).delete()
        self.assertTrue(OrganizationMember.objects.filter(pk=self.member.pk).exists())

    def test_queryset_delete_rejects_all_owners_together(self):
        second = add_organization_member(
            self.org, self.other, role=OrganizationMember.Role.OWNER
        )
        with self.assertRaises(LastOrganizationOwnerError):
            OrganizationMember.objects.filter(
                pk__in=[self.member.pk, second.pk]
            ).delete()
        self.assertEqual(
            OrganizationMember.objects.filter(
                organization=self.org, role=OrganizationMember.Role.OWNER
            ).count(),
            2,
        )

    def test_queryset_delete_allows_non_owner(self):
        admin = add_organization_member(
            self.org, self.other, role=OrganizationMember.Role.ADMIN
        )
        OrganizationMember.objects.filter(pk=admin.pk).delete()
        self.assertTrue(organization_has_owner(self.org))

    def test_queryset_update_rejects_demoting_last_owner(self):
        with self.assertRaises(LastOrganizationOwnerError):
            OrganizationMember.objects.filter(pk=self.member.pk).update(
                role=OrganizationMember.Role.ADMIN
            )
        self.member.refresh_from_db()
        self.assertEqual(self.member.role, OrganizationMember.Role.OWNER)

    def test_queryset_update_demotes_when_another_owner_exists(self):
        add_organization_member(
            self.org, self.other, role=OrganizationMember.Role.OWNER
        )
        OrganizationMember.objects.filter(pk=self.member.pk).update(
            role=OrganizationMember.Role.ADMIN
        )
        self.member.refresh_from_db()
        self.assertEqual(self.member.role, OrganizationMember.Role.ADMIN)
        self.assertTrue(is_organization_owner(self.other, self.org))

    def test_owner_handover_in_same_formset(self):
        formset_cls = inlineformset_factory(
            Organization,
            OrganizationMember,
            fields=("user", "role"),
            extra=1,
            can_delete=True,
        )
        data = {
            "memberships-TOTAL_FORMS": "2",
            "memberships-INITIAL_FORMS": "1",
            "memberships-MIN_NUM_FORMS": "0",
            "memberships-MAX_NUM_FORMS": "1000",
            "memberships-0-id": str(self.member.pk),
            "memberships-0-organization": str(self.org.pk),
            "memberships-0-user": str(self.owner.pk),
            "memberships-0-role": OrganizationMember.Role.OWNER,
            "memberships-0-DELETE": "on",
            "memberships-1-organization": str(self.org.pk),
            "memberships-1-user": str(self.other.pk),
            "memberships-1-role": OrganizationMember.Role.OWNER,
        }
        formset = formset_cls(data, instance=self.org)
        self.assertTrue(formset.is_valid(), formset.errors)
        save_organization_member_formset(formset, self.org)
        self.assertFalse(
            OrganizationMember.objects.filter(pk=self.member.pk).exists()
        )
        self.assertTrue(is_organization_owner(self.other, self.org))

    def test_formset_cannot_delete_last_owner_without_replacement(self):
        formset_cls = inlineformset_factory(
            Organization,
            OrganizationMember,
            fields=("user", "role"),
            extra=0,
            can_delete=True,
        )
        data = {
            "memberships-TOTAL_FORMS": "1",
            "memberships-INITIAL_FORMS": "1",
            "memberships-MIN_NUM_FORMS": "0",
            "memberships-MAX_NUM_FORMS": "1000",
            "memberships-0-id": str(self.member.pk),
            "memberships-0-organization": str(self.org.pk),
            "memberships-0-user": str(self.owner.pk),
            "memberships-0-role": OrganizationMember.Role.OWNER,
            "memberships-0-DELETE": "on",
        }
        formset = formset_cls(data, instance=self.org)
        self.assertTrue(formset.is_valid(), formset.errors)
        with self.assertRaises(LastOrganizationOwnerError):
            save_organization_member_formset(formset, self.org)
        self.assertTrue(OrganizationMember.objects.filter(pk=self.member.pk).exists())

    def test_operator_can_restore_owner_on_orphan_org(self):
        self.owner.delete()
        self.org.refresh_from_db()
        self.assertFalse(organization_has_owner(self.org))
        replacement = _make_user("restore-owner@waseda.jp")
        add_organization_member(
            self.org, replacement, role=OrganizationMember.Role.OWNER
        )
        self.org.status = Organization.Status.ACTIVE
        self.org.is_listed = True
        self.org.save(update_fields=["status", "is_listed"])
        self.assertFalse(apply_organization_visibility_guard(self.org))
        self.assertTrue(is_organization_owner(replacement, self.org))
        self.assertTrue(can_list_organization(self.org))

    def test_slug_is_normalized_lowercase(self):
        org = Organization.objects.create(name="大文字", slug="Team-OtherOrg")
        self.assertEqual(org.slug, "team-otherorg")


class OrganizationUserDeletionVisibilityTests(TestCase):
    def test_last_owner_user_delete_unpublishes_active_org(self):
        org = _make_org(
            slug="was-public",
            status=Organization.Status.ACTIVE,
            is_listed=True,
        )
        owner = _make_user("public-owner@waseda.jp")
        add_organization_member(org, owner, role=OrganizationMember.Role.OWNER)
        owner.delete()
        org.refresh_from_db()
        self.assertEqual(org.status, Organization.Status.DRAFT)
        self.assertFalse(org.is_listed)
        self.assertFalse(can_list_organization(org))
        self.assertFalse(can_view_organization_profile(AnonymousUser(), org))

    def test_last_owner_user_delete_keeps_suspended_but_unlists(self):
        org = _make_org(
            slug="was-suspended",
            status=Organization.Status.SUSPENDED,
            is_listed=True,
        )
        owner = _make_user("susp-owner@waseda.jp")
        add_organization_member(org, owner, role=OrganizationMember.Role.OWNER)
        owner.delete()
        org.refresh_from_db()
        self.assertEqual(org.status, Organization.Status.SUSPENDED)
        self.assertFalse(org.is_listed)

    def test_non_last_owner_user_delete_keeps_public_org(self):
        org = _make_org(
            slug="still-public",
            status=Organization.Status.ACTIVE,
            is_listed=True,
        )
        owner = _make_user("keep-pub-owner@waseda.jp")
        extra = _make_user("keep-pub-extra@waseda.jp")
        add_organization_member(org, owner, role=OrganizationMember.Role.OWNER)
        add_organization_member(org, extra, role=OrganizationMember.Role.OWNER)
        extra.delete()
        org.refresh_from_db()
        self.assertEqual(org.status, Organization.Status.ACTIVE)
        self.assertTrue(org.is_listed)
        self.assertTrue(is_organization_owner(owner, org))


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


def _org_staff(email: str) -> User:
    user = User.objects.create_user(
        email=email,
        password="test-pass-12345",
        is_staff=True,
    )
    _grant_model_perms(user, Organization, OrganizationMember)
    return user


def _org_staff_with_user_view(email: str) -> User:
    user = _org_staff(email)
    content_type = ContentType.objects.get_for_model(User)
    user.user_permissions.add(
        Permission.objects.get(content_type=content_type, codename="view_user")
    )
    return user


def _org_admin_payload(org: Organization | None = None, **overrides) -> dict[str, str]:
    data = {
        "name": "チームわせわせ",
        "slug": "team-wasewase",
        "description": "",
        "category": Organization.Category.PROJECT,
        "instagram_url": "",
        "website_url": "",
        "status": Organization.Status.DRAFT,
        "memberships-TOTAL_FORMS": "0",
        "memberships-INITIAL_FORMS": "0",
        "memberships-MIN_NUM_FORMS": "0",
        "memberships-MAX_NUM_FORMS": "1000",
        "_save": "保存",
    }
    if org is not None:
        data.update(
            {
                "name": org.name,
                "slug": org.slug,
                "description": org.description,
                "category": org.category,
                "instagram_url": org.instagram_url,
                "website_url": org.website_url,
                "status": org.status,
            }
        )
        if org.is_listed:
            data["is_listed"] = "on"
        if org.is_verified:
            data["is_verified"] = "on"
    data.update(overrides)
    return data


@override_settings(BROWSE_MODE_GATE_ENABLED=False)
class OrganizationAdminFlowTests(TestCase):
    def setUp(self):
        self.staff = _org_staff("org-admin@waseda.jp")
        self.client = Client()
        self.client.force_login(self.staff)
        self.owner = _make_user("admin-flow-owner@waseda.jp")

    def test_create_organization_with_owner(self):
        response = self.client.post(
            reverse("admin:app_organization_add"),
            _org_admin_payload(
                **{
                    "memberships-TOTAL_FORMS": "1",
                    "memberships-0-user": str(self.owner.pk),
                    "memberships-0-role": OrganizationMember.Role.OWNER,
                }
            ),
        )
        self.assertEqual(response.status_code, 302)
        org = Organization.objects.get(slug="team-wasewase")
        self.assertTrue(is_organization_owner(self.owner, org))
        self.assertEqual(org.status, Organization.Status.DRAFT)

    def test_cannot_keep_active_without_owner(self):
        response = self.client.post(
            reverse("admin:app_organization_add"),
            _org_admin_payload(status=Organization.Status.ACTIVE, is_listed="on"),
        )
        self.assertEqual(response.status_code, 302)
        org = Organization.objects.get(slug="team-wasewase")
        self.assertEqual(org.status, Organization.Status.DRAFT)
        self.assertFalse(org.is_listed)
        self.assertFalse(organization_has_owner(org))

    def test_cannot_list_without_owner(self):
        org = _make_org(slug="unlist-me", status=Organization.Status.DRAFT)
        response = self.client.post(
            reverse("admin:app_organization_change", args=[org.pk]),
            _org_admin_payload(
                org,
                status=Organization.Status.ACTIVE,
                is_listed="on",
                **{
                    "memberships-TOTAL_FORMS": "0",
                    "memberships-INITIAL_FORMS": "0",
                },
            ),
        )
        self.assertEqual(response.status_code, 302)
        org.refresh_from_db()
        self.assertEqual(org.status, Organization.Status.DRAFT)
        self.assertFalse(org.is_listed)

    def test_staff_can_manage_suspended_org_and_restore_owner(self):
        org = _make_org(slug="suspended-restore", status=Organization.Status.SUSPENDED)
        member = add_organization_member(
            org, self.owner, role=OrganizationMember.Role.OWNER
        )
        change_url = reverse("admin:app_organization_change", args=[org.pk])
        response = self.client.post(
            change_url,
            _org_admin_payload(
                org,
                status=Organization.Status.SUSPENDED,
                **{
                    "memberships-TOTAL_FORMS": "1",
                    "memberships-INITIAL_FORMS": "1",
                    "memberships-0-id": str(member.pk),
                    "memberships-0-organization": str(org.pk),
                    "memberships-0-user": str(self.owner.pk),
                    "memberships-0-role": OrganizationMember.Role.OWNER,
                },
            ),
        )
        self.assertEqual(response.status_code, 302)
        org.refresh_from_db()
        self.assertEqual(org.status, Organization.Status.SUSPENDED)
        self.assertTrue(is_organization_owner(self.owner, org))
        self.assertFalse(can_manage_organization(self.owner, org))

    def test_non_staff_cannot_change_owner_via_admin(self):
        org = _make_org(slug="forbidden-owner")
        add_organization_member(
            org, self.owner, role=OrganizationMember.Role.OWNER
        )
        outsider = _make_user("not-staff@waseda.jp")
        client = Client()
        client.force_login(outsider)
        response = client.post(
            reverse("admin:app_organization_change", args=[org.pk]),
            _org_admin_payload(
                org,
                **{
                    "memberships-TOTAL_FORMS": "1",
                    "memberships-INITIAL_FORMS": "0",
                    "memberships-0-user": str(outsider.pk),
                    "memberships-0-role": OrganizationMember.Role.OWNER,
                },
            ),
        )
        self.assertIn(response.status_code, (302, 403))
        self.assertFalse(is_organization_owner(outsider, org))
        self.assertTrue(is_organization_owner(self.owner, org))

    def test_member_admin_delete_model_blocks_last_owner(self):
        org = _make_org(slug="admin-del-owner")
        member = add_organization_member(
            org, self.owner, role=OrganizationMember.Role.OWNER
        )
        model_admin = OrganizationMemberAdmin(OrganizationMember, site)
        request = type("Req", (), {"user": self.staff})()
        with self.assertRaises(PermissionDenied):
            model_admin.delete_model(request, member)
        self.assertTrue(OrganizationMember.objects.filter(pk=member.pk).exists())

    def test_add_page_shows_autocomplete_owner_row(self):
        response = self.client.get(reverse("admin:app_organization_add"))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn("admin-autocomplete", html)
        self.assertIn('name="memberships-0-user"', html)
        self.assertIn('name="memberships-0-role"', html)
        self.assertNotIn("related-lookup", html)
        self.assertIn("名前・メールアドレス・ユーザー名で検索", html)

    def test_invalid_user_id_does_not_create_organization(self):
        response = self.client.post(
            reverse("admin:app_organization_add"),
            _org_admin_payload(
                **{
                    "memberships-TOTAL_FORMS": "1",
                    "memberships-0-user": "999999",
                    "memberships-0-role": OrganizationMember.Role.OWNER,
                }
            ),
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Organization.objects.filter(slug="team-wasewase").exists())
        self.assertContains(response, "正しく選択してください")

    def test_add_owner_to_existing_organization(self):
        org = _make_org(slug="add-second-owner")
        member = add_organization_member(
            org, self.owner, role=OrganizationMember.Role.OWNER
        )
        extra = _make_user("second-owner@waseda.jp")
        response = self.client.post(
            reverse("admin:app_organization_change", args=[org.pk]),
            _org_admin_payload(
                org,
                **{
                    "memberships-TOTAL_FORMS": "2",
                    "memberships-INITIAL_FORMS": "1",
                    "memberships-0-id": str(member.pk),
                    "memberships-0-organization": str(org.pk),
                    "memberships-0-user": str(self.owner.pk),
                    "memberships-0-role": OrganizationMember.Role.OWNER,
                    "memberships-1-organization": str(org.pk),
                    "memberships-1-user": str(extra.pk),
                    "memberships-1-role": OrganizationMember.Role.OWNER,
                },
            ),
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(is_organization_owner(self.owner, org))
        self.assertTrue(is_organization_owner(extra, org))

    def test_handover_owner_on_change_form(self):
        org = _make_org(slug="handover-owner")
        member = add_organization_member(
            org, self.owner, role=OrganizationMember.Role.OWNER
        )
        replacement = _make_user("new-owner@waseda.jp")
        response = self.client.post(
            reverse("admin:app_organization_change", args=[org.pk]),
            _org_admin_payload(
                org,
                **{
                    "memberships-TOTAL_FORMS": "2",
                    "memberships-INITIAL_FORMS": "1",
                    "memberships-0-id": str(member.pk),
                    "memberships-0-organization": str(org.pk),
                    "memberships-0-user": str(self.owner.pk),
                    "memberships-0-role": OrganizationMember.Role.OWNER,
                    "memberships-0-DELETE": "on",
                    "memberships-1-organization": str(org.pk),
                    "memberships-1-user": str(replacement.pk),
                    "memberships-1-role": OrganizationMember.Role.OWNER,
                },
            ),
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(is_organization_owner(self.owner, org))
        self.assertTrue(is_organization_owner(replacement, org))

    def test_change_form_cannot_delete_last_owner(self):
        org = _make_org(slug="keep-last-owner")
        member = add_organization_member(
            org, self.owner, role=OrganizationMember.Role.OWNER
        )
        response = self.client.post(
            reverse("admin:app_organization_change", args=[org.pk]),
            _org_admin_payload(
                org,
                **{
                    "memberships-TOTAL_FORMS": "1",
                    "memberships-INITIAL_FORMS": "1",
                    "memberships-0-id": str(member.pk),
                    "memberships-0-organization": str(org.pk),
                    "memberships-0-user": str(self.owner.pk),
                    "memberships-0-role": OrganizationMember.Role.OWNER,
                    "memberships-0-DELETE": "on",
                },
            ),
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(OrganizationMember.objects.filter(pk=member.pk).exists())
        self.assertTrue(is_organization_owner(self.owner, org))

    def test_autocomplete_finds_user_by_name_email_username(self):
        picker = _org_staff_with_user_view("picker@waseda.jp")
        target = _make_user("found-owner@waseda.jp")
        target.username = "foundhandle"
        target.save(update_fields=["username"])
        target.profile.name = "代表太郎"
        target.profile.save(update_fields=["name"])
        client = Client()
        client.force_login(picker)
        url = reverse("admin:autocomplete")
        params = {
            "app_label": "app",
            "model_name": "organizationmember",
            "field_name": "user",
        }
        for term in ("found-owner@waseda.jp", "foundhandle", "代表太郎"):
            response = client.get(url, {**params, "term": term})
            self.assertEqual(response.status_code, 200, term)
            payload = json.loads(response.content)
            texts = [item["text"] for item in payload["results"]]
            ids = [item["id"] for item in payload["results"]]
            self.assertIn(str(target.pk), ids, term)
            self.assertTrue(
                any("found-owner@waseda.jp" in text for text in texts),
                texts,
            )
            self.assertTrue(any("代表太郎" in text for text in texts), texts)

    def test_non_staff_cannot_use_user_autocomplete(self):
        outsider = _make_user("no-admin-search@waseda.jp")
        client = Client()
        client.force_login(outsider)
        response = client.get(
            reverse("admin:autocomplete"),
            {
                "app_label": "app",
                "model_name": "organizationmember",
                "field_name": "user",
                "term": outsider.email,
            },
        )
        self.assertIn(response.status_code, (302, 403))
        if response.status_code == 302:
            self.assertIn("/admin/login", response.url)

