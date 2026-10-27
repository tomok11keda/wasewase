"""Linked personal profiles: create, switch, login, delete, safety."""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth.hashers import make_password
from django.db import IntegrityError, transaction
from django.test import Client, TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .account_identity_services import (
    MAX_LINKED_PROFILES,
    create_linked_profile,
    credential_user,
    same_person,
)
from .follow_services import toggle_follow_relationship
from .growth_metrics import university_verified_users_qs, verified_users_qs
from .models import (
    Follow,
    Notification,
    Organization,
    OrganizationMember,
    PasswordResetOTP,
    TimelineLike,
    TimelinePost,
    User,
    UserBlock,
    UserProfile,
)
from .notification_services import create_notification
from .organization_services import (
    add_organization_member,
    can_manage_organization,
    organization_has_owner,
)
from .otp_services import PASSWORD_RESET_USER_SESSION_KEY
from .ugc_services import is_either_blocked


def _json(payload: dict) -> dict:
    return {"data": json.dumps(payload), "content_type": "application/json"}


def _make_user(email: str, username: str, **kwargs) -> User:
    kwargs.setdefault("password", "test-pass-12345")
    user = User.objects.create_user(email=email, username=username, **kwargs)
    UserProfile.objects.get_or_create(
        user=user,
        defaults={"name": username, "department": "商学部", "onboarding_exempt": True},
    )
    return user


@override_settings(BROWSE_MODE_GATE_ENABLED=False)
class AccountIdentityApiTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.main = _make_user("linked-main@waseda.jp", "linkedmain")
        self.stranger = _make_user("linked-stranger@waseda.jp", "linkedstranger")

    def _login_main(self):
        self.client.force_login(self.main)

    def _create_alt(self, username="linkedalt", display_name="Alt"):
        return self.client.post(
            "/api/v1/me/linked-profiles/create/",
            **_json({"username": username, "display_name": display_name}),
        )

    def test_existing_email_login_still_works(self):
        res = self.client.post(
            "/api/v1/auth/login/",
            **_json(
                {
                    "email": "linked-main@waseda.jp",
                    "password": "test-pass-12345",
                }
            ),
        )
        self.assertEqual(res.status_code, 200)
        me = res.json()["me"]
        self.assertEqual(me["user"]["id"], self.main.pk)
        self.assertEqual(me["user"]["email"], "linked-main@waseda.jp")

    def test_create_switch_and_third_rejected(self):
        self._login_main()
        created = self._create_alt()
        self.assertEqual(created.status_code, 200, created.content)
        body = created.json()
        self.assertTrue(body["ok"])
        self.assertEqual(len(body["profiles"]), 2)
        self.assertFalse(body["can_add"])
        alt_id = body["me"]["user"]["id"]
        self.assertNotEqual(alt_id, self.main.pk)
        alt = User.objects.get(pk=alt_id)
        self.main.refresh_from_db()
        self.assertFalse(alt.has_usable_password())
        self.assertFalse((alt.email or "").strip())
        self.assertEqual(credential_user(alt).pk, self.main.pk)
        self.assertTrue(same_person(self.main, alt))
        self.assertFalse(alt.is_staff)
        self.assertFalse(alt.is_operator_verified)

        overflow = self._create_alt(username="linkedthird", display_name="Third")
        self.assertEqual(overflow.status_code, 400)
        self.assertEqual(overflow.json()["error"], "limit_reached")
        self.assertEqual(
            User.objects.filter(identity=alt.identity).count(),
            MAX_LINKED_PROFILES,
        )

        switch_back = self.client.post(
            "/api/v1/me/linked-profiles/switch/",
            **_json({"user_id": self.main.pk}),
        )
        self.assertEqual(switch_back.status_code, 200)
        self.assertEqual(switch_back.json()["me"]["user"]["id"], self.main.pk)

    def test_username_login_selects_alt_without_copying_password(self):
        self._login_main()
        alt_id = self._create_alt().json()["me"]["user"]["id"]
        alt = User.objects.get(pk=alt_id)
        main_hash = User.objects.get(pk=self.main.pk).password
        self.assertNotEqual(alt.password, main_hash)
        self.client.logout()

        res = self.client.post(
            "/api/v1/auth/login/",
            **_json({"email": "linkedalt", "password": "test-pass-12345"}),
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["me"]["user"]["id"], alt_id)
        self.assertEqual(res.json()["me"]["user"]["email"], "linked-main@waseda.jp")
        self.client.logout()

        email_login = self.client.post(
            "/api/v1/auth/login/",
            **_json(
                {
                    "email": "linked-main@waseda.jp",
                    "password": "test-pass-12345",
                }
            ),
        )
        self.assertEqual(email_login.status_code, 200)
        self.assertEqual(email_login.json()["me"]["user"]["id"], self.main.pk)

    def test_cannot_switch_to_stranger(self):
        self._login_main()
        res = self.client.post(
            "/api/v1/me/linked-profiles/switch/",
            **_json({"user_id": self.stranger.pk}),
        )
        self.assertEqual(res.status_code, 403)
        me = self.client.get("/api/v1/me/")
        self.assertEqual(me.json()["user"]["id"], self.main.pk)

    def test_posts_dm_notifications_stay_on_selected_profile(self):
        self._login_main()
        post = TimelinePost.objects.create(author=self.main, body="main post")
        create_notification(recipient=self.main, message="main only", link="/")
        Follow.objects.create(follower=self.main, following=self.stranger)
        start = self.client.post(
            "/api/v1/dm/start/",
            **_json({"user_id": self.stranger.pk}),
        )
        self.assertEqual(start.status_code, 200)
        room_id = start.json()["room_id"]

        alt_id = self._create_alt().json()["me"]["user"]["id"]
        me = self.client.get("/api/v1/me/")
        self.assertEqual(me.json()["user"]["id"], alt_id)
        self.assertEqual(me.json()["unread_notifications"], 0)

        inbox = self.client.get("/api/v1/dm/inbox/?tab=dm")
        self.assertEqual(inbox.status_code, 200)
        self.assertFalse(
            any(row["room_id"] == room_id for row in inbox.json()["conversations"])
        )

        like = self.client.post(f"/api/v1/timeline/{post.pk}/like/")
        self.assertEqual(like.status_code, 200)
        self.assertFalse(like.json()["liked"])
        self.assertFalse(
            TimelineLike.objects.filter(timeline_post=post, user_id=alt_id).exists()
        )

        follow = self.client.post(f"/api/v1/profile/{self.main.pk}/follow/")
        self.assertIn(follow.status_code, (400, 403))
        self.assertFalse(
            Follow.objects.filter(follower_id=alt_id, following=self.main).exists()
        )

        dm = self.client.post(
            "/api/v1/dm/start/",
            **_json({"user_id": self.main.pk}),
        )
        self.assertIn(dm.status_code, (400, 403))

        self.assertEqual(Notification.objects.filter(recipient_id=alt_id).count(), 0)
        self.assertEqual(Notification.objects.filter(recipient=self.main).count(), 1)

    def test_block_covers_sibling_profiles(self):
        self._login_main()
        alt_id = self._create_alt().json()["me"]["user"]["id"]
        alt = User.objects.get(pk=alt_id)
        UserBlock.objects.create(blocker=self.stranger, blocked=self.main)
        self.assertTrue(is_either_blocked(alt, self.stranger))
        self.assertTrue(is_either_blocked(self.main, self.stranger))

    def test_delete_current_keeps_sibling_and_credentials(self):
        self._login_main()
        alt_id = self._create_alt().json()["me"]["user"]["id"]
        TimelinePost.objects.create(author_id=alt_id, body="alt only")
        deleted = self.client.post(
            "/api/v1/me/linked-profiles/delete/",
            **_json({}),
        )
        self.assertEqual(deleted.status_code, 200)
        self.assertFalse(User.objects.filter(pk=alt_id).exists())
        remaining = User.objects.get(pk=self.main.pk)
        self.assertEqual(remaining.email, "linked-main@waseda.jp")
        self.assertTrue(remaining.check_password("test-pass-12345"))
        self.assertEqual(deleted.json()["me"]["user"]["id"], self.main.pk)
        self.assertTrue(deleted.json()["me"]["authenticated"])

    def test_delete_credential_moves_login_to_sibling(self):
        self._login_main()
        alt_id = self._create_alt().json()["me"]["user"]["id"]
        self.client.post(
            "/api/v1/me/linked-profiles/switch/",
            **_json({"user_id": self.main.pk}),
        )
        deleted = self.client.post(
            "/api/v1/me/linked-profiles/delete/",
            **_json({}),
        )
        self.assertEqual(deleted.status_code, 200)
        self.assertFalse(User.objects.filter(pk=self.main.pk).exists())
        remaining = User.objects.get(pk=alt_id)
        self.assertEqual(remaining.email, "linked-main@waseda.jp")
        self.assertTrue(remaining.check_password("test-pass-12345"))
        self.assertEqual(deleted.json()["me"]["user"]["id"], alt_id)

        self.client.logout()
        login = self.client.post(
            "/api/v1/auth/login/",
            **_json(
                {
                    "email": "linked-main@waseda.jp",
                    "password": "test-pass-12345",
                }
            ),
        )
        self.assertEqual(login.status_code, 200)
        self.assertEqual(login.json()["me"]["user"]["id"], alt_id)

    def test_entire_identity_delete_removes_both(self):
        self._login_main()
        alt_id = self._create_alt().json()["me"]["user"]["id"]
        identity_id = User.objects.get(pk=alt_id).identity_id
        deleted = self.client.post(
            "/api/v1/me/linked-profiles/delete/",
            **_json({"entire_identity": True}),
        )
        self.assertEqual(deleted.status_code, 200)
        self.assertFalse(deleted.json()["me"]["authenticated"])
        self.assertFalse(User.objects.filter(pk__in=[self.main.pk, alt_id]).exists())
        from .models import AccountIdentity

        self.assertFalse(AccountIdentity.objects.filter(pk=identity_id).exists())

    def test_organization_membership_stays_on_original_user(self):
        org = Organization.objects.create(
            name="リンク確認団体",
            slug="linked-org",
            status=Organization.Status.ACTIVE,
            is_listed=True,
        )
        add_organization_member(
            org, self.main, role=OrganizationMember.Role.OWNER
        )
        self._login_main()
        before = self.client.get("/api/v1/me/organizations/")
        self.assertEqual(before.status_code, 200)
        self.assertTrue(
            any(row["slug"] == "linked-org" for row in before.json()["organizations"])
        )
        self._create_alt()
        after = self.client.get("/api/v1/me/organizations/")
        self.assertEqual(after.status_code, 200)
        self.assertEqual(after.json()["organizations"], [])
        self.assertTrue(
            OrganizationMember.objects.filter(
                organization=org, user=self.main
            ).exists()
        )

    def test_university_metrics_do_not_double_count_alt(self):
        self._login_main()
        before_univ = university_verified_users_qs().count()
        before_verified = verified_users_qs().count()
        self._create_alt()
        self.main.refresh_from_db()
        self.assertEqual(university_verified_users_qs().count(), before_univ)
        self.assertEqual(verified_users_qs().count(), before_verified)
        self.assertEqual(
            university_verified_users_qs()
            .filter(identity_id=self.main.identity_id)
            .count(),
            1,
        )

    def test_delete_main_moves_email_password_and_university_login(self):
        self._login_main()
        alt_id = self._create_alt().json()["me"]["user"]["id"]
        self.client.post(
            "/api/v1/me/linked-profiles/switch/",
            **_json({"user_id": self.main.pk}),
        )
        old_hash = User.objects.get(pk=self.main.pk).password
        deleted = self.client.post(
            "/api/v1/me/linked-profiles/delete/",
            **_json({}),
        )
        self.assertEqual(deleted.status_code, 200)
        remaining = User.objects.get(pk=alt_id)
        self.assertEqual(remaining.email, "linked-main@waseda.jp")
        self.assertEqual(remaining.password, old_hash)
        self.assertTrue(remaining.check_password("test-pass-12345"))
        self.assertTrue(remaining.is_active)
        me = deleted.json()["me"]
        self.assertEqual(me["user"]["email"], "linked-main@waseda.jp")
        self.assertEqual(me["user"]["id"], alt_id)

        self.client.logout()
        login = self.client.post(
            "/api/v1/auth/login/",
            **_json(
                {
                    "email": "linked-main@waseda.jp",
                    "password": "test-pass-12345",
                }
            ),
        )
        self.assertEqual(login.status_code, 200)
        self.assertEqual(login.json()["me"]["user"]["id"], alt_id)

    def test_password_reset_works_after_main_profile_deleted(self):
        self._login_main()
        alt_id = self._create_alt().json()["me"]["user"]["id"]
        self.client.post(
            "/api/v1/me/linked-profiles/switch/",
            **_json({"user_id": self.main.pk}),
        )
        self.client.post("/api/v1/me/linked-profiles/delete/", **_json({}))
        self.client.logout()

        req = self.client.post(
            "/api/v1/auth/password-reset/",
            **_json({"email": "linked-main@waseda.jp"}),
        )
        self.assertEqual(req.status_code, 200)
        remaining = User.objects.get(pk=alt_id)
        self.assertEqual(remaining.email, "linked-main@waseda.jp")
        code = "654321"
        PasswordResetOTP.objects.update_or_create(
            user=remaining,
            defaults={
                "code_hash": make_password(code),
                "expires_at": timezone.now() + timedelta(minutes=10),
            },
        )
        session = self.client.session
        session[PASSWORD_RESET_USER_SESSION_KEY] = remaining.pk
        session.save()
        ver = self.client.post(
            "/api/v1/auth/password-reset/verify/",
            **_json({"code": code}),
        )
        self.assertEqual(ver.status_code, 200)
        setp = self.client.post(
            "/api/v1/auth/password-reset/set/",
            **_json(
                {"password1": "new-pass-12345", "password2": "new-pass-12345"}
            ),
        )
        self.assertEqual(setp.status_code, 200)
        remaining.refresh_from_db()
        self.assertTrue(remaining.check_password("new-pass-12345"))
        login = self.client.post(
            "/api/v1/auth/login/",
            **_json(
                {
                    "email": "linked-main@waseda.jp",
                    "password": "new-pass-12345",
                }
            ),
        )
        self.assertEqual(login.status_code, 200)
        self.assertEqual(login.json()["me"]["user"]["id"], alt_id)

    def test_org_admin_stays_on_original_user_across_switch_and_delete(self):
        org = Organization.objects.create(
            name="権限確認団体",
            slug="linked-org-perm",
            status=Organization.Status.ACTIVE,
            is_listed=True,
        )
        add_organization_member(
            org, self.main, role=OrganizationMember.Role.OWNER
        )
        self._login_main()
        alt_id = self._create_alt().json()["me"]["user"]["id"]
        alt = User.objects.get(pk=alt_id)
        self.assertFalse(can_manage_organization(alt, org))
        self.assertTrue(can_manage_organization(self.main, org))
        listed = self.client.get("/api/v1/me/organizations/")
        self.assertEqual(listed.json()["organizations"], [])

        self.client.post(
            "/api/v1/me/linked-profiles/switch/",
            **_json({"user_id": self.main.pk}),
        )
        listed_main = self.client.get("/api/v1/me/organizations/")
        self.assertTrue(
            any(row["slug"] == "linked-org-perm" for row in listed_main.json()["organizations"])
        )

        self.client.post(
            "/api/v1/me/linked-profiles/switch/",
            **_json({"user_id": alt_id}),
        )
        deleted_alt = self.client.post(
            "/api/v1/me/linked-profiles/delete/",
            **_json({}),
        )
        self.assertEqual(deleted_alt.status_code, 200)
        self.assertFalse(User.objects.filter(pk=alt_id).exists())
        org.refresh_from_db()
        self.assertTrue(can_manage_organization(self.main, org))
        self.assertEqual(org.status, Organization.Status.ACTIVE)
        self.assertTrue(org.is_listed)

        refused = self.client.post(
            "/api/v1/me/linked-profiles/delete/",
            **_json({}),
        )
        self.assertEqual(refused.status_code, 409)
        self.assertEqual(refused.json()["error"], "last_organization_owner")
        self.assertIn("権限確認団体", refused.json()["message"])
        self.assertTrue(User.objects.filter(pk=self.main.pk).exists())
        org.refresh_from_db()
        self.assertTrue(organization_has_owner(org))
        self.assertEqual(org.status, Organization.Status.ACTIVE)
        self.assertTrue(org.is_listed)

    def test_last_owner_profile_and_entire_identity_delete_are_refused(self):
        org = Organization.objects.create(
            name="最終代表の団体",
            slug="linked-last-owner",
            status=Organization.Status.ACTIVE,
            is_listed=True,
        )
        add_organization_member(
            org, self.main, role=OrganizationMember.Role.OWNER
        )
        self._login_main()
        alt_id = self._create_alt().json()["me"]["user"]["id"]
        entire = self.client.post(
            "/api/v1/me/linked-profiles/delete/",
            **_json({"entire_identity": True}),
        )
        self.assertEqual(entire.status_code, 409)
        self.assertEqual(entire.json()["error"], "last_organization_owner")
        self.assertEqual(
            User.objects.filter(pk__in=[self.main.pk, alt_id]).count(),
            2,
        )

        self.client.post(
            "/api/v1/me/linked-profiles/switch/",
            **_json({"user_id": self.main.pk}),
        )
        current = self.client.post(
            "/api/v1/me/linked-profiles/delete/",
            **_json({}),
        )
        self.assertEqual(current.status_code, 409)
        self.assertTrue(User.objects.filter(pk=self.main.pk).exists())
        org.refresh_from_db()
        self.assertEqual(org.status, Organization.Status.ACTIVE)
        self.assertTrue(org.is_listed)

        extra = _make_user("linked-owner-extra@waseda.jp", "linkedownerextra")
        add_organization_member(
            org, extra, role=OrganizationMember.Role.OWNER
        )
        transferred = self.client.post(
            "/api/v1/me/linked-profiles/delete/",
            **_json({"entire_identity": True}),
        )
        self.assertEqual(transferred.status_code, 200)
        self.assertFalse(User.objects.filter(pk__in=[self.main.pk, alt_id]).exists())
        org.refresh_from_db()
        self.assertTrue(
            OrganizationMember.objects.filter(
                organization=org,
                user=extra,
                role=OrganizationMember.Role.OWNER,
            ).exists()
        )
        self.assertTrue(organization_has_owner(org))
        self.assertEqual(org.status, Organization.Status.ACTIVE)
        self.assertTrue(org.is_listed)

    def test_classic_entire_identity_delete_refuses_last_owner(self):
        org = Organization.objects.create(
            name="従来完全退会団体",
            slug="linked-classic-entire",
            status=Organization.Status.ACTIVE,
            is_listed=True,
        )
        add_organization_member(
            org, self.main, role=OrganizationMember.Role.OWNER
        )
        self._login_main()
        alt_id = self._create_alt().json()["me"]["user"]["id"]
        response = self.client.post(
            reverse("delete_account"),
            {"confirm_delete": "DELETE", "entire_identity": "1"},
            follow=True,
        )
        self.assertRedirects(response, reverse("account_settings"))
        self.assertContains(response, "従来完全退会団体")
        self.assertEqual(
            User.objects.filter(pk__in=[self.main.pk, alt_id]).count(),
            2,
        )
        org.refresh_from_db()
        self.assertEqual(org.status, Organization.Status.ACTIVE)

    def test_settings_copy_guides_last_owner_transfer(self):
        root = Path(__file__).resolve().parents[1]
        spa = (root / "frontend/src/pages/SettingsPage.tsx").read_text(
            encoding="utf-8"
        )
        classic = (root / "templates/settings.html").read_text(encoding="utf-8")
        guide = "別の代表管理者へ権限を移してください"
        self.assertIn(guide, spa)
        self.assertIn(guide, classic)

    def test_session_user_changes_on_switch_logout_and_relogin(self):
        self._login_main()
        main_id = str(self.main.pk)
        self.assertEqual(self.client.session.get("_auth_user_id"), main_id)
        alt_id = self._create_alt().json()["me"]["user"]["id"]
        self.assertEqual(self.client.session.get("_auth_user_id"), str(alt_id))
        me_alt = self.client.get("/api/v1/me/").json()
        self.assertEqual(me_alt["user"]["id"], alt_id)

        self.client.post(
            "/api/v1/me/linked-profiles/switch/",
            **_json({"user_id": self.main.pk}),
        )
        self.assertEqual(self.client.session.get("_auth_user_id"), main_id)

        self.client.post("/api/v1/auth/logout/", **_json({}))
        self.assertIsNone(self.client.session.get("_auth_user_id"))
        me_out = self.client.get("/api/v1/me/").json()
        self.assertFalse(me_out["authenticated"])

        login = self.client.post(
            "/api/v1/auth/login/",
            **_json(
                {
                    "email": "linked-main@waseda.jp",
                    "password": "test-pass-12345",
                }
            ),
        )
        self.assertEqual(login.status_code, 200)
        self.assertEqual(login.json()["me"]["user"]["id"], self.main.pk)
        self.assertEqual(self.client.session.get("_auth_user_id"), main_id)

    def test_raising_max_allows_a_third_profile(self):
        self._login_main()
        with patch("app.account_identity_services.MAX_LINKED_PROFILES", 3):
            first = self._create_alt(username="capone", display_name="One")
            self.assertEqual(first.status_code, 200)
            second = self._create_alt(username="captwo", display_name="Two")
            self.assertEqual(second.status_code, 200)
            self.assertEqual(len(second.json()["profiles"]), 3)

    def test_isolated_lifecycle_add_switch_delete(self):
        self._login_main()
        created = self._create_alt()
        alt_id = created.json()["me"]["user"]["id"]
        self.assertEqual(self.client.session.get("_auth_user_id"), str(alt_id))
        switched = self.client.post(
            "/api/v1/me/linked-profiles/switch/",
            **_json({"user_id": self.main.pk}),
        )
        self.assertEqual(switched.json()["me"]["user"]["id"], self.main.pk)
        deleted = self.client.post(
            "/api/v1/me/linked-profiles/delete/",
            **_json({}),
        )
        self.assertEqual(deleted.status_code, 200)
        self.assertFalse(User.objects.filter(pk=self.main.pk).exists())
        remaining = User.objects.get(pk=alt_id)
        self.assertEqual(remaining.email, "linked-main@waseda.jp")
        self.assertTrue(remaining.check_password("test-pass-12345"))


class AccountIdentityServiceTests(TestCase):
    def test_same_person_follow_rejected_without_api(self):
        main = _make_user("svc-main@waseda.jp", "svcmain")
        alt = create_linked_profile(main, username="svcalt", display_name="Svc Alt")
        with self.assertRaises(ValueError):
            toggle_follow_relationship(alt, main)
        self.assertFalse(Follow.objects.filter(follower=alt, following=main).exists())


class AccountIdentityEmailConstraintTests(TransactionTestCase):
    def test_multiple_null_emails_are_allowed_and_duplicates_are_not(self):
        first = User(email=None, username="nullmail1")
        first.set_unusable_password()
        first.save()
        second = User(email=None, username="nullmail2")
        second.set_unusable_password()
        second.save()
        self.assertIsNone(first.email)
        self.assertIsNone(second.email)

        _make_user("unique-mail@waseda.jp", "uniquemail")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                User.objects.create_user(
                    email="unique-mail@waseda.jp",
                    username="dupemail",
                    password="test-pass-12345",
                )


class AccountIdentityFrontendCacheTests(TestCase):
    def test_session_clears_user_scoped_caches_on_switch(self):
        source = Path("frontend/src/lib/session.tsx").read_text(encoding="utf-8")
        self.assertIn("clearInboxCache(previousUserId)", source)
        self.assertIn("clearNotificationsCache(previousUserId)", source)
        self.assertIn("clearOwnProfileCache(previousUserId)", source)
        self.assertIn("clearFollowListCache()", source)
        home = Path("frontend/src/pages/HomePage.tsx").read_text(encoding="utf-8")
        self.assertIn("prevUserIdRef.current === sessionUserId", home)
        self.assertIn("setPosts([])", home)
