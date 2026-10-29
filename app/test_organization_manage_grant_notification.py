"""Organization owner/admin grants reuse the existing inbox Notification."""

from __future__ import annotations

from django.test import Client, TestCase, override_settings
from django.urls import reverse

from .account_identity_services import create_linked_profile
from .models import Notification, Organization, OrganizationMember, User
from .notification_api_services import notification_spa_path
from .notification_services import get_unread_notification_count
from .organization_services import (
    add_organization_member,
    organization_manage_grant_link,
    organization_manage_grant_message,
    provision_operator_granted_organization,
    remove_organization_member,
    set_organization_member_role,
)
from .test_organization import (
    _make_org,
    _make_user,
    _org_admin_payload,
    _org_staff,
)


def _grant_notes(user: User) -> list[Notification]:
    return list(
        Notification.objects.filter(recipient=user).order_by("pk")
    )


@override_settings(BROWSE_MODE_GATE_ENABLED=False)
class OrganizationManageGrantNotificationTests(TestCase):
    def setUp(self):
        self.owner = _make_user("grant-note-owner@waseda.jp", username="grantnoteowner")
        self.admin = _make_user("grant-note-admin@waseda.jp", username="grantnoteadmin")
        self.member = _make_user("grant-note-member@waseda.jp", username="grantnotemember")
        self.org = _make_org(name="わせわせサークル", slug="wase-circle")
        self.client = Client()

    def test_owner_grant_creates_inbox_row_and_unread_badge(self):
        add_organization_member(
            self.org, self.owner, role=OrganizationMember.Role.OWNER
        )
        notes = _grant_notes(self.owner)
        self.assertEqual(len(notes), 1)
        note = notes[0]
        self.assertEqual(
            note.message,
            organization_manage_grant_message(self.org),
        )
        self.assertEqual(note.message, "わせわせサークルの管理権限が付与されました")
        self.assertEqual(note.link, organization_manage_grant_link(self.org))
        self.assertFalse(note.is_read)
        self.assertEqual(
            notification_spa_path(note.link),
            "/orgs/wase-circle?org_grant=1",
        )
        self.assertEqual(get_unread_notification_count(self.owner), 1)

        self.client.force_login(self.owner)
        unread = self.client.get("/api/notifications/unread-count/")
        self.assertEqual(unread.status_code, 200)
        self.assertEqual(unread.json()["unread_count"], 1)
        me = self.client.get("/api/v1/me/")
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.json()["unread_notifications"], 1)
        self.assertEqual(me.json()["dm_unread_total"], 0)

    def test_grant_unread_adds_to_existing_inbox_unread(self):
        Notification.objects.create(
            recipient=self.owner,
            message="いいね通知",
            link="/posts/1",
            is_read=False,
        )
        add_organization_member(
            self.org, self.owner, role=OrganizationMember.Role.OWNER
        )
        self.assertEqual(get_unread_notification_count(self.owner), 2)
        self.client.force_login(self.owner)
        unread = self.client.get("/api/notifications/unread-count/")
        self.assertEqual(unread.json()["unread_count"], 2)
        dm = self.client.get("/api/dm/unread-summary/")
        self.assertEqual(dm.status_code, 200)
        self.assertEqual(dm.json()["total_unread"], 0)

    def test_member_role_does_not_notify(self):
        add_organization_member(
            self.org, self.owner, role=OrganizationMember.Role.OWNER
        )
        add_organization_member(
            self.org, self.member, role=OrganizationMember.Role.MEMBER
        )
        self.assertEqual(Notification.objects.filter(recipient=self.member).count(), 0)
        self.assertEqual(Notification.objects.filter(recipient=self.owner).count(), 1)

    def test_duplicate_save_does_not_create_second_notification(self):
        member = add_organization_member(
            self.org, self.owner, role=OrganizationMember.Role.OWNER
        )
        member.save()
        set_organization_member_role(member, OrganizationMember.Role.OWNER)
        self.assertEqual(Notification.objects.filter(recipient=self.owner).count(), 1)

    def test_member_promoted_to_admin_notifies_once(self):
        add_organization_member(
            self.org, self.owner, role=OrganizationMember.Role.OWNER
        )
        member = add_organization_member(
            self.org, self.member, role=OrganizationMember.Role.MEMBER
        )
        set_organization_member_role(member, OrganizationMember.Role.ADMIN)
        notes = _grant_notes(self.member)
        self.assertEqual(len(notes), 1)
        self.assertIn("わせわせサークルの管理権限が付与されました", notes[0].message)
        set_organization_member_role(member, OrganizationMember.Role.OWNER)
        self.assertEqual(Notification.objects.filter(recipient=self.member).count(), 1)

    def test_revoke_and_regrant_creates_a_new_notification(self):
        owner = add_organization_member(
            self.org, self.owner, role=OrganizationMember.Role.OWNER
        )
        extra = add_organization_member(
            self.org, self.admin, role=OrganizationMember.Role.OWNER
        )
        remove_organization_member(extra)
        self.assertEqual(Notification.objects.filter(recipient=self.admin).count(), 1)
        add_organization_member(
            self.org, self.admin, role=OrganizationMember.Role.ADMIN
        )
        self.assertEqual(Notification.objects.filter(recipient=self.admin).count(), 2)
        self.assertTrue(OrganizationMember.objects.filter(pk=owner.pk).exists())

    def test_linked_profile_is_not_notified(self):
        add_organization_member(
            self.org, self.owner, role=OrganizationMember.Role.OWNER
        )
        alt = create_linked_profile(
            self.owner, username="grantnotealt", display_name="Alt"
        )
        self.assertEqual(Notification.objects.filter(recipient=self.owner).count(), 1)
        self.assertEqual(Notification.objects.filter(recipient=alt).count(), 0)
        add_organization_member(
            self.org, alt, role=OrganizationMember.Role.ADMIN
        )
        self.assertEqual(Notification.objects.filter(recipient=alt).count(), 1)
        self.assertEqual(Notification.objects.filter(recipient=self.owner).count(), 1)

    def test_opening_inbox_marks_read_without_removing_membership(self):
        add_organization_member(
            self.org, self.owner, role=OrganizationMember.Role.OWNER
        )
        self.client.force_login(self.owner)
        peek = self.client.get("/api/v1/notifications/?mark_read=0")
        self.assertEqual(peek.status_code, 200)
        self.assertEqual(peek.json()["unread_count"], 1)
        self.assertEqual(peek.json()["marked_count"], 0)
        self.assertFalse(peek.json()["notifications"][0]["is_read"])
        opened = self.client.get("/api/v1/notifications/")
        self.assertEqual(opened.status_code, 200)
        self.assertEqual(opened.json()["unread_count"], 0)
        self.assertGreaterEqual(opened.json()["marked_count"], 1)
        self.assertEqual(
            opened.json()["notifications"][0]["spa_path"],
            "/orgs/wase-circle?org_grant=1",
        )
        self.assertTrue(
            OrganizationMember.objects.filter(
                organization=self.org,
                user=self.owner,
                role=OrganizationMember.Role.OWNER,
            ).exists()
        )
        unread = self.client.get("/api/notifications/unread-count/")
        self.assertEqual(unread.json()["unread_count"], 0)

    def test_provision_helper_notifies_the_owner(self):
        org = provision_operator_granted_organization(
            owner=self.owner,
            name="付与サークル",
            slug="granted-notify",
        )
        notes = Notification.objects.filter(recipient=self.owner, link__contains="granted-notify")
        self.assertEqual(notes.count(), 1)
        self.assertEqual(notes.get().message, "付与サークルの管理権限が付与されました")
        self.assertTrue(
            OrganizationMember.objects.filter(
                organization=org, user=self.owner, role=OrganizationMember.Role.OWNER
            ).exists()
        )


@override_settings(BROWSE_MODE_GATE_ENABLED=False)
class OrganizationManageGrantAdminNotificationTests(TestCase):
    def setUp(self):
        self.staff = _org_staff("grant-note-staff@waseda.jp")
        self.owner = _make_user("grant-note-admin-owner@waseda.jp")
        self.client = Client()
        self.client.force_login(self.staff)

    def test_admin_create_with_owner_notifies_once(self):
        response = self.client.post(
            reverse("admin:app_organization_add"),
            _org_admin_payload(
                **{
                    "name": "運営付与サークル",
                    "slug": "operator-grant-circle",
                    "memberships-TOTAL_FORMS": "1",
                    "memberships-0-user": str(self.owner.pk),
                    "memberships-0-role": OrganizationMember.Role.OWNER,
                }
            ),
        )
        self.assertEqual(response.status_code, 302)
        org = Organization.objects.get(slug="operator-grant-circle")
        member = OrganizationMember.objects.get(organization=org, user=self.owner)
        self.assertEqual(Notification.objects.filter(recipient=self.owner).count(), 1)

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
                },
            ),
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Notification.objects.filter(recipient=self.owner).count(), 1)
        self.assertEqual(Notification.objects.filter(recipient=self.staff).count(), 0)

    def test_admin_adding_second_admin_notifies_that_user_only(self):
        org = _make_org(name="二件目サークル", slug="second-admin-circle")
        owner_member = add_organization_member(
            org, self.owner, role=OrganizationMember.Role.OWNER
        )
        extra = _make_user("grant-note-second-admin@waseda.jp")
        response = self.client.post(
            reverse("admin:app_organization_change", args=[org.pk]),
            _org_admin_payload(
                org,
                **{
                    "memberships-TOTAL_FORMS": "2",
                    "memberships-INITIAL_FORMS": "1",
                    "memberships-0-id": str(owner_member.pk),
                    "memberships-0-organization": str(org.pk),
                    "memberships-0-user": str(self.owner.pk),
                    "memberships-0-role": OrganizationMember.Role.OWNER,
                    "memberships-1-organization": str(org.pk),
                    "memberships-1-user": str(extra.pk),
                    "memberships-1-role": OrganizationMember.Role.ADMIN,
                },
            ),
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Notification.objects.filter(recipient=self.owner).count(), 1)
        self.assertEqual(Notification.objects.filter(recipient=extra).count(), 1)
        self.assertEqual(
            Notification.objects.get(recipient=extra).message,
            "二件目サークルの管理権限が付与されました",
        )
