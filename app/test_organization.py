"""Phase 1-A: Organization model, membership, and admin/operator split."""

from __future__ import annotations

import json
from datetime import timedelta
from unittest.mock import patch

from django.contrib.admin.sites import site
from django.contrib.auth.models import AnonymousUser, Permission
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import IntegrityError, transaction
from django.forms.models import inlineformset_factory
from django.test import Client, RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .account_deletion_services import delete_user_account
from .admin import (
    OrganizationAdmin,
    OrganizationMemberAdmin,
    OrganizationMemberInline,
    UserAdmin,
)
from .models import (
    Community,
    Organization,
    OrganizationEvent,
    OrganizationMember,
    ProfileLink,
    User,
    UserProfile,
)
from .organization_services import (
    LastOrganizationOwnerError,
    OrganizationMembershipError,
    add_organization_member,
    apply_organization_visibility_guard,
    assert_users_can_be_deleted_without_orphaning_organizations,
    can_list_organization,
    can_manage_organization,
    can_select_managed_organization,
    can_view_organization_profile,
    complete_operator_organization_grant,
    get_organization_membership_role,
    is_organization_admin,
    is_organization_owner,
    is_site_operator,
    organization_has_owner,
    organizations_left_without_owner_if_users_deleted,
    provision_operator_granted_organization,
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
        self.assertTrue(can_select_managed_organization(self.org))

    def test_active_unlisted_is_viewable_but_not_listed(self):
        self.org.status = Organization.Status.ACTIVE
        self.org.is_listed = False
        self.org.save(update_fields=["status", "is_listed"])
        self.assertTrue(can_view_organization_profile(AnonymousUser(), self.org))
        self.assertTrue(can_view_organization_profile(self.outsider, self.org))
        self.assertFalse(can_list_organization(self.org))
        self.assertFalse(can_select_managed_organization(self.org))

    def test_draft_stays_selectable_while_unlisted(self):
        self.org.status = Organization.Status.DRAFT
        self.org.is_listed = False
        self.org.save(update_fields=["status", "is_listed"])
        self.assertFalse(can_list_organization(self.org))
        self.assertTrue(can_select_managed_organization(self.org))

    def test_active_listed_is_public(self):
        self.org.status = Organization.Status.ACTIVE
        self.org.is_listed = True
        self.org.save(update_fields=["status", "is_listed"])
        self.assertTrue(can_view_organization_profile(AnonymousUser(), self.org))
        self.assertTrue(can_list_organization(self.org))
        self.assertTrue(can_select_managed_organization(self.org))

    def test_suspended_is_hidden_from_general_users(self):
        self.org.status = Organization.Status.SUSPENDED
        self.org.is_listed = True
        self.org.save(update_fields=["status", "is_listed"])
        self.assertTrue(can_view_organization_profile(self.owner, self.org))
        self.assertTrue(can_view_organization_profile(self.staff, self.org))
        self.assertFalse(can_view_organization_profile(self.outsider, self.org))
        self.assertFalse(can_view_organization_profile(AnonymousUser(), self.org))
        self.assertFalse(can_list_organization(self.org))
        self.assertFalse(can_select_managed_organization(self.org))


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


class OrganizationAccountDeletionGuardTests(TestCase):
    def setUp(self):
        self._firestore_patcher = patch(
            "app.bookmark_services.get_firestore_client",
            return_value=None,
        )
        self._firestore_patcher.start()
        self.addCleanup(self._firestore_patcher.stop)

    def test_last_owner_account_deletion_is_refused(self):
        org = _make_org(
            slug="guard-public",
            name="公開を守る団体",
            status=Organization.Status.ACTIVE,
            is_listed=True,
        )
        owner = _make_user("guard-owner@waseda.jp")
        add_organization_member(org, owner, role=OrganizationMember.Role.OWNER)
        with self.assertRaises(LastOrganizationOwnerError) as raised:
            delete_user_account(owner)
        self.assertIn("公開を守る団体", str(raised.exception))
        self.assertIn("権限を移してください", str(raised.exception))
        self.assertTrue(User.objects.filter(pk=owner.pk).exists())
        org.refresh_from_db()
        self.assertTrue(organization_has_owner(org))
        self.assertEqual(org.status, Organization.Status.ACTIVE)
        self.assertTrue(org.is_listed)

    def test_last_owner_account_deletion_refused_when_only_admin_remains(self):
        org = _make_org(
            slug="guard-admin-only",
            status=Organization.Status.ACTIVE,
            is_listed=True,
        )
        owner = _make_user("guard-admin-owner@waseda.jp")
        admin = _make_user("guard-admin-remain@waseda.jp")
        add_organization_member(org, owner, role=OrganizationMember.Role.OWNER)
        add_organization_member(org, admin, role=OrganizationMember.Role.ADMIN)
        with self.assertRaises(LastOrganizationOwnerError):
            delete_user_account(owner)
        org.refresh_from_db()
        self.assertTrue(is_organization_owner(owner, org))
        self.assertEqual(org.status, Organization.Status.ACTIVE)
        self.assertTrue(org.is_listed)

    def test_account_deletion_allowed_when_another_owner_remains(self):
        org = _make_org(
            slug="guard-two-owners",
            status=Organization.Status.ACTIVE,
            is_listed=True,
        )
        owner = _make_user("guard-two-owner@waseda.jp")
        extra = _make_user("guard-two-extra@waseda.jp")
        add_organization_member(org, owner, role=OrganizationMember.Role.OWNER)
        add_organization_member(org, extra, role=OrganizationMember.Role.OWNER)
        delete_user_account(owner)
        self.assertFalse(User.objects.filter(pk=owner.pk).exists())
        org.refresh_from_db()
        self.assertTrue(is_organization_owner(extra, org))
        self.assertEqual(org.status, Organization.Status.ACTIVE)
        self.assertTrue(org.is_listed)

    def test_entire_identity_users_are_checked_as_a_set(self):
        org = _make_org(slug="guard-set", name="セット確認")
        owner = _make_user("guard-set-owner@waseda.jp")
        sibling = _make_user("guard-set-sib@waseda.jp")
        add_organization_member(org, owner, role=OrganizationMember.Role.OWNER)
        blocked = organizations_left_without_owner_if_users_deleted(
            [owner.pk, sibling.pk]
        )
        self.assertEqual([item.pk for item in blocked], [org.pk])
        with self.assertRaises(LastOrganizationOwnerError):
            assert_users_can_be_deleted_without_orphaning_organizations(
                [owner.pk, sibling.pk]
            )
        add_organization_member(org, sibling, role=OrganizationMember.Role.OWNER)
        self.assertEqual(
            organizations_left_without_owner_if_users_deleted([owner.pk, sibling.pk]),
            [org],
        )
        extra = _make_user("guard-set-extra@waseda.jp")
        add_organization_member(org, extra, role=OrganizationMember.Role.OWNER)
        self.assertEqual(
            organizations_left_without_owner_if_users_deleted([owner.pk, sibling.pk]),
            [],
        )

    def test_classic_single_profile_withdrawal_unpublishes_last_owner_org(self):
        org = _make_org(
            slug="guard-classic",
            name="従来退会団体",
            status=Organization.Status.ACTIVE,
            is_listed=True,
        )
        owner = _make_user("guard-classic-owner@waseda.jp")
        leftover = _make_user("guard-classic-admin@waseda.jp")
        add_organization_member(org, owner, role=OrganizationMember.Role.OWNER)
        add_organization_member(org, leftover, role=OrganizationMember.Role.ADMIN)
        client = Client()
        client.force_login(owner)
        response = client.post(
            reverse("delete_account"),
            {"confirm_delete": "DELETE"},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertRedirects(response, reverse("login"))
        self.assertFalse(User.objects.filter(pk=owner.pk).exists())
        org.refresh_from_db()
        self.assertEqual(org.status, Organization.Status.DRAFT)
        self.assertFalse(org.is_listed)
        self.assertTrue(
            OrganizationMember.objects.filter(organization=org, user=leftover).exists()
        )
        self.assertTrue(can_manage_organization(leftover, org))

    def test_full_withdrawal_allows_last_owner_and_keeps_remaining_members(self):
        org = _make_org(
            slug="guard-withdraw",
            status=Organization.Status.ACTIVE,
            is_listed=True,
        )
        owner = _make_user("guard-withdraw-owner@waseda.jp")
        leftover = _make_user("guard-withdraw-admin@waseda.jp")
        add_organization_member(org, owner, role=OrganizationMember.Role.OWNER)
        add_organization_member(org, leftover, role=OrganizationMember.Role.MEMBER)
        delete_user_account(owner, allow_orphaning_organizations=True)
        self.assertFalse(User.objects.filter(pk=owner.pk).exists())
        org.refresh_from_db()
        self.assertEqual(org.status, Organization.Status.DRAFT)
        self.assertFalse(org.is_listed)
        self.assertTrue(
            OrganizationMember.objects.filter(organization=org, user=leftover).exists()
        )

    def test_management_command_refuses_last_owner(self):
        org = _make_org(slug="guard-command", name="コマンド団体")
        owner = _make_user("guard-command-owner@waseda.jp")
        add_organization_member(org, owner, role=OrganizationMember.Role.OWNER)
        with self.assertRaises(CommandError) as raised:
            call_command("delete_user_account", "--user-id", str(owner.pk))
        self.assertIn("--allow-unpublished-organizations", str(raised.exception))
        self.assertTrue(User.objects.filter(pk=owner.pk).exists())
        org.refresh_from_db()
        self.assertTrue(organization_has_owner(org))

    def test_management_command_allows_last_owner_with_flag(self):
        org = _make_org(
            slug="guard-command-allow",
            name="コマンド許可団体",
            status=Organization.Status.ACTIVE,
            is_listed=True,
        )
        owner = _make_user("guard-command-allow@waseda.jp")
        add_organization_member(org, owner, role=OrganizationMember.Role.OWNER)
        call_command(
            "delete_user_account",
            "--user-id",
            str(owner.pk),
            "--allow-unpublished-organizations",
        )
        self.assertFalse(User.objects.filter(pk=owner.pk).exists())
        org.refresh_from_db()
        self.assertEqual(org.status, Organization.Status.DRAFT)
        self.assertFalse(org.is_listed)


class OrganizationAdminUserDeletionWarningTests(TestCase):
    def setUp(self):
        self.actor = User.objects.create_superuser(
            email="org-admin-actor@waseda.jp",
            password="pass12345",
        )
        self.client = Client()
        self.client.force_login(self.actor)

    def test_delete_page_warns_and_requires_checkbox_for_last_owner(self):
        org = _make_org(
            slug="admin-warn-org",
            name="Admin警告団体",
            status=Organization.Status.ACTIVE,
            is_listed=True,
        )
        owner = _make_user("admin-warn-owner@waseda.jp")
        leftover = _make_user("admin-warn-member@waseda.jp")
        add_organization_member(org, owner, role=OrganizationMember.Role.OWNER)
        add_organization_member(org, leftover, role=OrganizationMember.Role.ADMIN)
        url = reverse("admin:app_user_delete", args=[owner.pk])
        shown = self.client.get(url)
        self.assertEqual(shown.status_code, 200)
        self.assertContains(shown, "Admin警告団体")
        self.assertContains(shown, "非公開になります")
        self.assertContains(shown, "confirm_unpublish_organizations")
        refused = self.client.post(url, {"post": "yes"})
        self.assertEqual(refused.status_code, 200)
        self.assertTrue(User.objects.filter(pk=owner.pk).exists())
        org.refresh_from_db()
        self.assertEqual(org.status, Organization.Status.ACTIVE)
        confirmed = self.client.post(
            url,
            {"post": "yes", "confirm_unpublish_organizations": "yes"},
        )
        self.assertEqual(confirmed.status_code, 302)
        self.assertFalse(User.objects.filter(pk=owner.pk).exists())
        org.refresh_from_db()
        self.assertEqual(org.status, Organization.Status.DRAFT)
        self.assertFalse(org.is_listed)
        self.assertTrue(
            OrganizationMember.objects.filter(organization=org, user=leftover).exists()
        )

    def test_bulk_delete_without_checkbox_keeps_last_owner(self):
        org = _make_org(
            slug="admin-bulk-org",
            name="一括警告団体",
            status=Organization.Status.ACTIVE,
            is_listed=True,
        )
        owner = _make_user("admin-bulk-owner@waseda.jp")
        add_organization_member(org, owner, role=OrganizationMember.Role.OWNER)
        changelist = reverse("admin:app_user_changelist")
        confirm = self.client.post(
            changelist,
            {
                "action": "delete_selected",
                "_selected_action": [str(owner.pk)],
            },
        )
        self.assertEqual(confirm.status_code, 200)
        self.assertContains(confirm, "一括警告団体")
        self.assertContains(confirm, "非公開になります")
        refused = self.client.post(
            changelist,
            {
                "action": "delete_selected",
                "post": "yes",
                "_selected_action": [str(owner.pk)],
            },
            follow=True,
        )
        self.assertEqual(refused.status_code, 200)
        self.assertContains(refused, "一括削除を中止")
        self.assertTrue(User.objects.filter(pk=owner.pk).exists())
        org.refresh_from_db()
        self.assertEqual(org.status, Organization.Status.ACTIVE)


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
    _grant_model_perms(user, Organization, OrganizationMember, ProfileLink)
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
        "profile_links-TOTAL_FORMS": "0",
        "profile_links-INITIAL_FORMS": "0",
        "profile_links-MIN_NUM_FORMS": "0",
        "profile_links-MAX_NUM_FORMS": "5",
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
        self.assertEqual(org.status, Organization.Status.ACTIVE)
        self.assertTrue(org.is_listed)
        self.assertTrue(can_list_organization(org))

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

    def test_adding_first_owner_publishes_existing_draft(self):
        org = _make_org(slug="complete-grant")
        admin = add_organization_member(
            org, self.owner, role=OrganizationMember.Role.ADMIN
        )
        self.assertEqual(org.status, Organization.Status.DRAFT)
        self.assertFalse(org.is_listed)
        response = self.client.post(
            reverse("admin:app_organization_change", args=[org.pk]),
            _org_admin_payload(
                org,
                **{
                    "memberships-TOTAL_FORMS": "2",
                    "memberships-INITIAL_FORMS": "1",
                    "memberships-0-id": str(admin.pk),
                    "memberships-0-organization": str(org.pk),
                    "memberships-0-user": str(self.owner.pk),
                    "memberships-0-role": OrganizationMember.Role.OWNER,
                    "memberships-1-organization": str(org.pk),
                    "memberships-1-user": str(
                        _make_user("grant-admin@waseda.jp").pk
                    ),
                    "memberships-1-role": OrganizationMember.Role.ADMIN,
                },
            ),
        )
        self.assertEqual(response.status_code, 302)
        org.refresh_from_db()
        self.assertTrue(is_organization_owner(self.owner, org))
        self.assertEqual(org.status, Organization.Status.ACTIVE)
        self.assertTrue(org.is_listed)

    def test_intentional_unlist_is_kept_after_grant(self):
        org = provision_operator_granted_organization(
            owner=self.owner,
            name="掲載解除する団体",
            slug="unlist-after-grant",
        )
        member = OrganizationMember.objects.get(
            organization=org, user=self.owner
        )
        payload = _org_admin_payload(
            org,
            status=Organization.Status.ACTIVE,
            **{
                "memberships-TOTAL_FORMS": "1",
                "memberships-INITIAL_FORMS": "1",
                "memberships-0-id": str(member.pk),
                "memberships-0-organization": str(org.pk),
                "memberships-0-user": str(self.owner.pk),
                "memberships-0-role": OrganizationMember.Role.OWNER,
            },
        )
        payload.pop("is_listed", None)
        response = self.client.post(
            reverse("admin:app_organization_change", args=[org.pk]),
            payload,
        )
        self.assertEqual(response.status_code, 302)
        org.refresh_from_db()
        self.assertEqual(org.status, Organization.Status.ACTIVE)
        self.assertFalse(org.is_listed)
        self.assertFalse(can_list_organization(org))

    def test_create_suspended_with_owner_stays_suspended(self):
        response = self.client.post(
            reverse("admin:app_organization_add"),
            _org_admin_payload(
                status=Organization.Status.SUSPENDED,
                **{
                    "memberships-TOTAL_FORMS": "1",
                    "memberships-0-user": str(self.owner.pk),
                    "memberships-0-role": OrganizationMember.Role.OWNER,
                },
            ),
        )
        self.assertEqual(response.status_code, 302)
        org = Organization.objects.get(slug="team-wasewase")
        self.assertTrue(is_organization_owner(self.owner, org))
        self.assertEqual(org.status, Organization.Status.SUSPENDED)
        self.assertFalse(org.is_listed)


@override_settings(BROWSE_MODE_GATE_ENABLED=False)
class OperatorGrantedOrganizationTests(TestCase):
    def setUp(self):
        self.owner = _make_user("grant-owner@waseda.jp", username="grantowner")
        self.student = _make_user("grant-student@waseda.jp", username="grantstudent")
        self.client = Client()

    def test_provision_sets_owner_active_and_listed(self):
        org = provision_operator_granted_organization(
            owner=self.owner,
            name="付与した団体",
            slug="granted-circle",
        )
        self.assertEqual(org.status, Organization.Status.ACTIVE)
        self.assertTrue(org.is_listed)
        self.assertTrue(is_organization_owner(self.owner, org))
        self.assertTrue(can_list_organization(org))

    def test_provision_rolls_back_when_owner_is_missing(self):
        with self.assertRaises(OrganizationMembershipError):
            provision_operator_granted_organization(
                owner=User(),
                name="失敗する団体",
                slug="grant-rollback",
            )
        self.assertFalse(
            Organization.objects.filter(slug="grant-rollback").exists()
        )

    def test_raw_create_without_owner_stays_unpublished(self):
        org = Organization.objects.create(name="下書きのまま", slug="still-draft")
        self.assertEqual(org.status, Organization.Status.DRAFT)
        self.assertFalse(org.is_listed)
        self.assertFalse(can_list_organization(org))

    def test_complete_grant_helper_skips_later_saves(self):
        org = provision_operator_granted_organization(
            owner=self.owner,
            name="後から非掲載",
            slug="later-unlist",
        )
        org.is_listed = False
        org.save(update_fields=["is_listed"])
        self.assertFalse(
            complete_operator_organization_grant(org, completing_grant=False)
        )
        org.refresh_from_db()
        self.assertFalse(org.is_listed)

    def test_granted_event_share_appears_on_public_feed(self):
        org = provision_operator_granted_organization(
            owner=self.owner,
            name="公開シェア団体",
            slug="granted-share",
        )
        now = timezone.now()
        event = OrganizationEvent.objects.create(
            organization=org,
            title="付与後の公開イベント",
            starts_at=now + timedelta(days=2),
            ends_at=now + timedelta(days=2, hours=2),
            venue_name="大隈講堂",
            status=OrganizationEvent.Status.PUBLISHED,
            created_by=self.owner,
        )
        self.client.force_login(self.owner)
        shared = self.client.post(
            f"/api/v1/organizations/{org.slug}/events/{event.pk}/timeline-share/",
            data=json.dumps({"body": "付与後シェア本文"}),
            content_type="application/json",
        )
        self.assertEqual(shared.status_code, 201, shared.content)
        post_id = shared.json()["post_id"]

        self.client.force_login(self.student)
        detail = self.client.get(f"/api/v1/timeline/{post_id}/")
        self.assertEqual(detail.status_code, 200)
        feed = self.client.get("/api/v1/timeline/", {"sort": "latest"})
        self.assertIn(post_id, [row["id"] for row in feed.json()["posts"]])
        search = self.client.get(
            "/api/v1/search/", {"q": "付与後の公開イベント", "tab": "latest"}
        )
        self.assertEqual(search.status_code, 200)
        search_ids = {row["id"] for row in search.json().get("posts") or []}
        for row in search.json().get("results") or []:
            if row.get("kind") == "post" and row.get("post"):
                search_ids.add(row["post"]["id"])
        self.assertIn(post_id, search_ids)

        draft = OrganizationEvent.objects.create(
            organization=org,
            title="秘密の下書きイベントZZZ",
            starts_at=now + timedelta(days=3),
            ends_at=now + timedelta(days=3, hours=2),
            venue_name="非公開会場",
            status=OrganizationEvent.Status.DRAFT,
            created_by=self.owner,
        )
        self.client.force_login(self.owner)
        hidden = self.client.post(
            f"/api/v1/organizations/{org.slug}/events/{draft.pk}/timeline-share/",
            data=json.dumps({"body": "下書きはシェアしない"}),
            content_type="application/json",
        )
        self.assertEqual(hidden.status_code, 409)
        self.client.force_login(self.student)
        leaked = self.client.get(
            "/api/v1/search/", {"q": "秘密の下書きイベントZZZ", "tab": "latest"}
        )
        self.assertEqual(leaked.status_code, 200)
        leaked_ids = {row["id"] for row in leaked.json().get("posts") or []}
        self.assertNotIn(post_id, leaked_ids)

