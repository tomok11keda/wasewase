"""Guards that prevent physical deletion of superuser accounts."""

from __future__ import annotations

from io import StringIO
from unittest.mock import patch

from django.contrib.admin.sites import site
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse

from .account_deletion_services import (
    SUPERUSER_DELETION_DENIED_MESSAGE,
    SuperuserDeletionDenied,
    delete_user_account,
)
from .admin import UserAdmin
from .models import TimelinePost, User


@override_settings(BROWSE_MODE_GATE_ENABLED=False, WASE_REACT_SPA=False)
class SuperuserAccountDeletionGuardTests(TestCase):
    def setUp(self):
        self._firestore_patcher = patch(
            "app.bookmark_services.get_firestore_client",
            return_value=None,
        )
        self._firestore_patcher.start()
        self.addCleanup(self._firestore_patcher.stop)
        UserModel = get_user_model()
        self.member = UserModel.objects.create_user(
            email="member-del@waseda.jp",
            password="pass12345",
            username="member_del",
        )
        self.superuser = UserModel.objects.create_superuser(
            email="admin-del@waseda.jp",
            password="pass12345",
        )
        self.admin_post = TimelinePost.objects.create(
            author=self.superuser,
            body="管理者の投稿は残す",
        )

    def test_normal_user_account_deletion_still_succeeds(self):
        self.client.force_login(self.member)
        response = self.client.post(
            reverse("delete_account"),
            {"confirm_delete": "DELETE"},
        )
        self.assertRedirects(response, reverse("login"))
        self.assertFalse(User.objects.filter(pk=self.member.pk).exists())

    def test_superuser_post_delete_account_is_rejected(self):
        self.client.force_login(self.superuser)
        response = self.client.post(
            reverse("delete_account"),
            {"confirm_delete": "DELETE"},
            follow=True,
        )
        self.assertRedirects(response, reverse("account_settings"))
        self.assertContains(response, SUPERUSER_DELETION_DENIED_MESSAGE)
        self.superuser.refresh_from_db()
        self.assertTrue(User.objects.filter(pk=self.superuser.pk).exists())
        self.assertTrue(self.superuser.is_superuser)
        self.assertTrue(TimelinePost.objects.filter(pk=self.admin_post.pk).exists())
        self.assertEqual(
            str(self.client.session.get("_auth_user_id")),
            str(self.superuser.pk),
        )

    def test_delete_user_account_service_rejects_superuser(self):
        with self.assertRaises(SuperuserDeletionDenied):
            delete_user_account(self.superuser)
        self.superuser.refresh_from_db()
        self.assertTrue(User.objects.filter(pk=self.superuser.pk).exists())
        self.assertTrue(self.superuser.is_superuser)
        self.assertTrue(TimelinePost.objects.filter(pk=self.admin_post.pk).exists())


@override_settings(BROWSE_MODE_GATE_ENABLED=False, WASE_REACT_SPA=False)
class SuperuserAdminDeletionGuardTests(TestCase):
    def setUp(self):
        UserModel = get_user_model()
        self.actor = UserModel.objects.create_superuser(
            email="actor-admin@waseda.jp",
            password="pass12345",
        )
        self.protected = UserModel.objects.create_superuser(
            email="protected-admin@waseda.jp",
            password="pass12345",
        )
        self.normal_a = UserModel.objects.create_user(
            email="normal-a@waseda.jp",
            password="pass12345",
            username="normal_a",
        )
        self.normal_b = UserModel.objects.create_user(
            email="normal-b@waseda.jp",
            password="pass12345",
            username="normal_b",
        )
        self.client.force_login(self.actor)
        self.model_admin = UserAdmin(User, site)
        self.factory = RequestFactory()

    def test_has_delete_permission_denied_for_superuser_object(self):
        request = self.factory.get("/admin/")
        request.user = self.actor
        self.assertFalse(
            self.model_admin.has_delete_permission(request, obj=self.protected)
        )
        self.assertTrue(
            self.model_admin.has_delete_permission(request, obj=self.normal_a)
        )

    def test_direct_admin_delete_url_cannot_delete_superuser(self):
        url = reverse("admin:app_user_delete", args=[self.protected.pk])
        get_response = self.client.get(url)
        self.assertEqual(get_response.status_code, 403)
        post_response = self.client.post(url, {"post": "yes"})
        self.assertEqual(post_response.status_code, 403)
        self.assertTrue(User.objects.filter(pk=self.protected.pk).exists())

    def test_bulk_delete_normal_users_still_works(self):
        changelist = reverse("admin:app_user_changelist")
        response = self.client.post(
            changelist,
            {
                "action": "delete_selected",
                "post": "yes",
                "_selected_action": [str(self.normal_a.pk), str(self.normal_b.pk)],
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(User.objects.filter(pk=self.normal_a.pk).exists())
        self.assertFalse(User.objects.filter(pk=self.normal_b.pk).exists())

    def test_bulk_delete_containing_superuser_is_fully_rejected(self):
        changelist = reverse("admin:app_user_changelist")
        response = self.client.post(
            changelist,
            {
                "action": "delete_selected",
                "post": "yes",
                "_selected_action": [
                    str(self.protected.pk),
                    str(self.normal_a.pk),
                ],
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "管理者アカウント（スーパーユーザー）が含まれているため",
        )
        self.assertTrue(User.objects.filter(pk=self.protected.pk).exists())
        self.assertTrue(User.objects.filter(pk=self.normal_a.pk).exists())
        self.assertTrue(User.objects.filter(pk=self.actor.pk).exists())


class SuperuserDeletionCommandTests(TestCase):
    def setUp(self):
        self._firestore_patcher = patch(
            "app.bookmark_services.get_firestore_client",
            return_value=None,
        )
        self._firestore_patcher.start()
        self.addCleanup(self._firestore_patcher.stop)
        UserModel = get_user_model()
        self.member = UserModel.objects.create_user(
            email="cmd-member@waseda.jp",
            password="pass12345",
            username="cmd_member",
        )
        self.superuser = UserModel.objects.create_superuser(
            email="cmd-admin@waseda.jp",
            password="pass12345",
        )

    @patch("app.management.commands.delete_user_account.ensure_chatroom_group_chat_schema")
    def test_command_deletes_normal_user(self, _schema):
        call_command("delete_user_account", "--user-id", str(self.member.pk))
        self.assertFalse(User.objects.filter(pk=self.member.pk).exists())

    @patch("app.management.commands.delete_user_account.ensure_chatroom_group_chat_schema")
    def test_command_aborts_for_superuser(self, mock_schema):
        out = StringIO()
        with self.assertRaises(CommandError) as ctx:
            call_command(
                "delete_user_account",
                "--email",
                "cmd-admin@waseda.jp",
                stdout=out,
            )
        self.assertIn("Refusing to delete a superuser", str(ctx.exception))
        mock_schema.assert_not_called()
        self.assertTrue(User.objects.filter(pk=self.superuser.pk).exists())
        self.superuser.refresh_from_db()
        self.assertTrue(self.superuser.is_superuser)
