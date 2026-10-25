"""Phase 3-B: recruiting chat JSON APIs, inbox, and message ACL."""

from __future__ import annotations

import json

from django.test import Client, TestCase, override_settings

from .models import (
    ChatMessage,
    ChatRoom,
    ChatRoomMembership,
    ContentReport,
    Follow,
    Notification,
    Organization,
    OrganizationMember,
    OrganizationRecruitingChat,
    OrganizationRecruitingChatApplication,
    User,
    UserProfile,
)
from .organization_recruiting_chat_services import (
    OrganizationRecruitingChatError,
    create_recruiting_chat,
    join_or_apply_recruiting_chat,
    update_recruiting_chat_settings,
)
from .organization_services import add_organization_member, set_organization_member_role
from .ugc_services import get_report_target


def _make_user(email: str, **kwargs) -> User:
    kwargs.setdefault("password", "test-pass-12345")
    user = User.objects.create_user(email=email, **kwargs)
    UserProfile.objects.get_or_create(
        user=user,
        defaults={"name": email.split("@")[0]},
    )
    return user


def _make_org(**kwargs) -> Organization:
    kwargs.setdefault("name", "新歓APIサークル")
    kwargs.setdefault("slug", "recruiting-api-circle")
    kwargs.setdefault("status", Organization.Status.ACTIVE)
    kwargs.setdefault("is_listed", True)
    return Organization.objects.create(**kwargs)


@override_settings(BROWSE_MODE_GATE_ENABLED=False)
class OrganizationRecruitingChatApiTests(TestCase):
    def setUp(self):
        self.owner = _make_user("api-owner@waseda.jp", username="apiowner")
        self.admin = _make_user("api-admin@waseda.jp", username="apiadmin")
        self.member = _make_user("api-member@waseda.jp", username="apimember")
        self.student = _make_user("api-student@waseda.jp", username="apistudent")
        self.stranger = _make_user("api-stranger@waseda.jp", username="apistranger")
        self.other_owner = _make_user("api-other@waseda.jp", username="apiother")
        self.org = _make_org()
        self.other_org = _make_org(name="別API団体", slug="other-api-org")
        add_organization_member(
            self.org, self.owner, role=OrganizationMember.Role.OWNER
        )
        add_organization_member(
            self.org, self.admin, role=OrganizationMember.Role.ADMIN
        )
        add_organization_member(
            self.org, self.member, role=OrganizationMember.Role.MEMBER
        )
        add_organization_member(
            self.other_org, self.other_owner, role=OrganizationMember.Role.OWNER
        )
        self.client = Client()

    def _url(self, suffix: str = "", slug: str | None = None) -> str:
        return f"/api/v1/organizations/{slug or self.org.slug}/recruiting-chat/{suffix}"

    def _json(self, method: str, url: str, **payload):
        handler = getattr(self.client, method.lower())
        if payload:
            return handler(
                url,
                data=json.dumps(payload),
                content_type="application/json",
            )
        return handler(url)

    def _create(self, actor=None, **payload):
        self.client.force_login(actor or self.owner)
        payload.setdefault("name", "2026新歓チャット")
        payload.setdefault("description", "新入生向け")
        return self._json("post", self._url(), **payload)

    def test_owner_and_admin_can_create_others_cannot(self):
        created = self._create()
        self.assertEqual(created.status_code, 201, created.content)
        body = created.json()["recruiting_chat"]
        self.assertEqual(body["name"], "2026新歓チャット")
        self.assertEqual(body["join_mode"], "open")
        self.assertTrue(body["can_manage"])
        self.assertIsNotNone(body["room_id"])
        self.assertNotIn("@waseda.jp", json.dumps(body))

        self.client.force_login(self.admin)
        duplicate = self._json("post", self._url(), name="二重")
        self.assertEqual(duplicate.status_code, 409)

        self.client.force_login(self.member)
        denied_member = self._json("post", self._url(), name="メンバー作成")
        self.assertEqual(denied_member.status_code, 403)

        self.client.force_login(self.stranger)
        denied_stranger = self._json("post", self._url(), name="部外者")
        self.assertEqual(denied_stranger.status_code, 403)

        self.client.force_login(self.other_owner)
        denied_other = self._json("post", self._url(), name="別団体")
        self.assertEqual(denied_other.status_code, 403)

        guest = Client()
        unauth = guest.post(
            self._url(),
            data=json.dumps({"name": "未ログイン"}),
            content_type="application/json",
        )
        self.assertEqual(unauth.status_code, 401)

    def test_open_join_and_messages_acl(self):
        created = self._create()
        room_id = created.json()["recruiting_chat"]["room_id"]
        self.client.force_login(self.student)
        joined = self._json("post", self._url("join/"))
        self.assertEqual(joined.status_code, 201)
        payload = joined.json()["recruiting_chat"]
        self.assertEqual(payload["membership_status"], "joined")
        self.assertEqual(payload["room_id"], room_id)
        self.assertFalse(
            OrganizationMember.objects.filter(
                organization=self.org, user=self.student
            ).exists()
        )

        send = self._json(
            "post",
            f"/api/v1/recruiting-chats/{room_id}/messages/send/",
            body="参加しました",
        )
        self.assertEqual(send.status_code, 201)
        self.assertEqual(send.json()["message"]["body"], "参加しました")
        self.assertNotIn("email", send.json()["message"])

        messages = self.client.get(f"/api/v1/recruiting-chats/{room_id}/messages/")
        self.assertEqual(messages.status_code, 200)
        bodies = [m["body"] for m in messages.json()["messages"]]
        self.assertIn("参加しました", bodies)

        self.client.force_login(self.stranger)
        denied = self.client.get(f"/api/v1/recruiting-chats/{room_id}/messages/")
        self.assertEqual(denied.status_code, 403)
        self.assertNotIn("messages", denied.json())
        send_denied = self._json(
            "post",
            f"/api/v1/recruiting-chats/{room_id}/messages/send/",
            body="侵入",
        )
        self.assertEqual(send_denied.status_code, 403)

        group = self.client.get(f"/api/v1/dm/groups/{room_id}/")
        self.assertEqual(group.status_code, 404)

    def test_approval_pending_approve_reject_leave_remove(self):
        self._create(join_mode="approval")
        self.client.force_login(self.student)
        pending = self._json("post", self._url("join/"))
        self.assertEqual(pending.status_code, 201)
        chat_payload = pending.json()["recruiting_chat"]
        self.assertEqual(chat_payload["membership_status"], "pending")
        self.assertIsNone(chat_payload["room_id"])
        application_id = pending.json()["application_id"]

        inbox = self.client.get("/api/v1/dm/inbox/")
        kinds = {c["kind"] for c in inbox.json()["conversations"]}
        self.assertNotIn("recruiting", kinds)

        self.client.force_login(self.stranger)
        apps = self.client.get(self._url("applications/"))
        self.assertEqual(apps.status_code, 403)

        self.client.force_login(self.owner)
        listed = self.client.get(self._url("applications/"))
        self.assertEqual(listed.status_code, 200)
        blob = json.dumps(listed.json())
        self.assertNotIn("@waseda.jp", blob)
        self.assertEqual(listed.json()["pending_count"], 1)

        get_chat = self.client.get(self._url())
        self.assertTrue(get_chat.json()["recruiting_chat"]["would_auto_approve_on_open"])
        self.assertEqual(get_chat.json()["recruiting_chat"]["pending_count"], 1)

        no_confirm = self._json("patch", self._url(), join_mode="open")
        self.assertEqual(no_confirm.status_code, 409)
        self.assertEqual(no_confirm.json()["error"], "confirm_auto_approve_required")
        self.assertEqual(no_confirm.json()["pending_count"], 1)

        approved = self._json(
            "post", self._url(f"applications/{application_id}/approve/")
        )
        self.assertEqual(approved.status_code, 200)
        self.assertEqual(approved.json()["application_status"], "approved")
        self.assertTrue(
            ChatRoomMembership.objects.filter(user=self.student).exists()
        )

        self.client.force_login(self.student)
        room_id = self.client.get(self._url()).json()["recruiting_chat"]["room_id"]
        send = self._json(
            "post",
            f"/api/v1/recruiting-chats/{room_id}/messages/send/",
            body="承認後",
        )
        self.assertEqual(send.status_code, 201)
        left = self._json("post", self._url("leave/"))
        self.assertEqual(left.status_code, 200)
        self.assertEqual(
            left.json()["recruiting_chat"]["membership_status"],
            "not_joined",
        )
        denied = self._json(
            "post",
            f"/api/v1/recruiting-chats/{room_id}/messages/send/",
            body="退出後",
        )
        self.assertEqual(denied.status_code, 403)

        reapply = self._json("post", self._url("join/"))
        self.assertEqual(reapply.status_code, 201)
        self.assertEqual(reapply.json()["application_status"], "pending")
        app_id = reapply.json()["application_id"]
        self.client.force_login(self.admin)
        rejected = self._json("post", self._url(f"applications/{app_id}/reject/"))
        self.assertEqual(rejected.status_code, 200)
        self.client.force_login(self.student)
        self.assertEqual(
            self.client.get(self._url()).json()["recruiting_chat"]["membership_status"],
            "rejected",
        )

    def test_withdraw_pending_and_duplicate_join(self):
        self._create(join_mode="approval")
        self.client.force_login(self.student)
        first = self._json("post", self._url("join/"))
        second = self._json("post", self._url("join/"))
        self.assertEqual(second.status_code, 409)
        self.assertEqual(second.json()["error"], "already_pending")
        withdrawn = self._json("post", self._url("withdraw/"))
        self.assertEqual(withdrawn.status_code, 200)
        self.assertEqual(withdrawn.json()["application_status"], "withdrawn")
        again = self._json("post", self._url("join/"))
        self.assertEqual(again.status_code, 201)
        self.assertEqual(first.json()["application_id"], again.json()["application_id"])

    def test_remove_member_and_wrong_ids(self):
        created = self._create()
        room_id = created.json()["recruiting_chat"]["room_id"]
        self.client.force_login(self.student)
        self._json("post", self._url("join/"))
        self.client.force_login(self.owner)
        missing = self._json(
            "post", self._url(f"members/{self.stranger.pk}/remove/")
        )
        self.assertEqual(missing.status_code, 404)
        removed = self._json(
            "post", self._url(f"members/{self.student.pk}/remove/")
        )
        self.assertEqual(removed.status_code, 200)
        self.client.force_login(self.student)
        self.assertEqual(
            self.client.get(f"/api/v1/recruiting-chats/{room_id}/messages/").status_code,
            403,
        )
        other_chat = create_recruiting_chat(
            organization=self.other_org,
            actor=self.other_owner,
            name="別新歓",
            join_mode=OrganizationRecruitingChat.JoinMode.APPROVAL,
        )
        other_app = join_or_apply_recruiting_chat(
            chat=other_chat, user=self.stranger
        )
        self.client.force_login(self.owner)
        idor = self._json(
            "post",
            self._url(f"applications/{other_app.pk}/approve/"),
        )
        self.assertEqual(idor.status_code, 404)

    def test_switch_to_open_requires_confirm_then_approves(self):
        self._create(join_mode="approval")
        self.client.force_login(self.student)
        self._json("post", self._url("join/"))
        self.client.force_login(self.owner)
        confirmed = self._json(
            "patch",
            self._url(),
            join_mode="open",
            confirm_auto_approve=True,
        )
        self.assertEqual(confirmed.status_code, 200)
        self.assertEqual(confirmed.json()["auto_approved_count"], 1)
        self.assertTrue(confirmed.json()["would_auto_approve"])
        self.client.force_login(self.student)
        status = self.client.get(self._url()).json()["recruiting_chat"]
        self.assertEqual(status["membership_status"], "joined")
        self.assertIsNotNone(status["room_id"])

    def test_inbox_for_member_and_manager_not_pending(self):
        created = self._create()
        room_id = created.json()["recruiting_chat"]["room_id"]
        self.client.force_login(self.student)
        self._json("post", self._url("join/"))
        self._json(
            "post",
            f"/api/v1/recruiting-chats/{room_id}/messages/send/",
            body="inbox本文",
        )
        member_inbox = self.client.get("/api/v1/dm/inbox/?tab=dm").json()
        recruiting = [
            c for c in member_inbox["conversations"] if c["kind"] == "recruiting"
        ]
        self.assertEqual(len(recruiting), 1)
        item = recruiting[0]
        self.assertEqual(item["room_id"], room_id)
        self.assertEqual(item["organization_slug"], self.org.slug)
        self.assertEqual(item["organization_name"], self.org.name)
        self.assertEqual(item["viewer_role"], "member")
        self.assertEqual(item["latest_body"], "inbox本文")
        self.assertEqual(item["status_label"], "団体チャット")
        self.assertEqual(
            item["spa_path"],
            f"/organizations/{self.org.slug}/recruiting-chat",
        )
        self.assertFalse(item["spa_path"].startswith("/app/"))
        self.assertNotIn("@waseda.jp", json.dumps(item))

        self.client.force_login(self.owner)
        manager_inbox = self.client.get("/api/v1/dm/inbox/?tab=all").json()
        manager_item = [
            c for c in manager_inbox["conversations"] if c["kind"] == "recruiting"
        ][0]
        self.assertEqual(manager_item["viewer_role"], "manager")

        self.client.force_login(self.stranger)
        stranger_inbox = self.client.get("/api/v1/dm/inbox/").json()
        self.assertFalse(
            any(c["kind"] == "recruiting" for c in stranger_inbox["conversations"])
        )

    def test_suspended_and_closed_and_lost_role(self):
        created = self._create(join_mode="approval")
        self.client.force_login(self.student)
        pending = self._json("post", self._url("join/"))
        application_id = pending.json()["application_id"]
        self.org.status = Organization.Status.SUSPENDED
        self.org.save(update_fields=["status", "updated_at"])
        join_again = self._json("post", self._url("join/"))
        self.assertIn(join_again.status_code, (403, 404))
        self.client.force_login(self.owner)
        manage = self._json("patch", self._url(), name="停止中")
        self.assertEqual(manage.status_code, 403)
        approve = self._json(
            "post", self._url(f"applications/{application_id}/approve/")
        )
        self.assertEqual(approve.status_code, 403)

        self.org.status = Organization.Status.ACTIVE
        self.org.save(update_fields=["status", "updated_at"])
        chat = OrganizationRecruitingChat.objects.get(organization=self.org)
        update_recruiting_chat_settings(
            chat=chat,
            actor=self.owner,
            listing_status=OrganizationRecruitingChat.ListingStatus.CLOSED,
        )
        self.client.force_login(self.stranger)
        closed_join = self._json("post", self._url("join/"))
        self.assertEqual(closed_join.status_code, 403)

        admin_row = OrganizationMember.objects.get(
            organization=self.org, user=self.admin
        )
        set_organization_member_role(admin_row, OrganizationMember.Role.MEMBER)
        self.client.force_login(self.admin)
        lost = self._json("patch", self._url(), name="降格後")
        self.assertEqual(lost.status_code, 403)

    def test_reply_delete_report_and_notification_path(self):
        created = self._create()
        room_id = created.json()["recruiting_chat"]["room_id"]
        self.client.force_login(self.student)
        self._json("post", self._url("join/"))
        parent = self._json(
            "post",
            f"/api/v1/recruiting-chats/{room_id}/messages/send/",
            body="親メッセージ",
        )
        parent_id = parent.json()["message"]["id"]
        reply = self._json(
            "post",
            f"/api/v1/recruiting-chats/{room_id}/messages/send/",
            body="返信です",
            reply_to_id=parent_id,
        )
        self.assertEqual(reply.status_code, 201)
        self.assertEqual(reply.json()["message"]["reply_to"]["id"], parent_id)
        self.assertNotIn("image_url", reply.json()["message"])
        deleted = self._json(
            "post",
            f"/api/v1/recruiting-chats/{room_id}/messages/{parent_id}/delete/",
        )
        self.assertEqual(deleted.status_code, 200)

        Notification.objects.create(
            recipient=self.stranger,
            message="新歓を見て",
            link=f"/api/v1/recruiting-chats/{room_id}/messages/",
        )
        self.client.force_login(self.stranger)
        leaked = self.client.get(f"/api/v1/recruiting-chats/{room_id}/messages/")
        self.assertEqual(leaked.status_code, 403)
        report = get_report_target(
            ContentReport.TargetType.CHAT_MESSAGE,
            reply.json()["message"]["id"],
            viewer=self.stranger,
        )
        self.assertIsNone(report)
        members = self.client.get(self._url("members/"))
        self.assertEqual(members.status_code, 403)

    def test_csrf_and_compat_dm_group_course(self):
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.owner)
        csrf = csrf_client.post(
            self._url(),
            data=json.dumps({"name": "CSRF欠落"}),
            content_type="application/json",
        )
        self.assertEqual(csrf.status_code, 403)
        self.assertEqual(csrf.json()["error"], "csrf_failed")

        Follow.objects.create(follower=self.student, following=self.stranger)
        self.client.force_login(self.student)
        dm = self._json(
            "post",
            "/api/v1/dm/start/",
            user_id=self.stranger.pk,
        )
        self.assertEqual(dm.status_code, 200)
        group = self._json(
            "post",
            "/api/v1/dm/groups/",
            name="互換グループ",
            member_ids=[self.stranger.pk],
        )
        self.assertEqual(group.status_code, 201)
        self.assertEqual(
            ChatRoom.objects.get(pk=group.json()["room_id"]).kind,
            ChatRoom.Kind.GROUP,
        )

        from .course_chat_services import join_course_talk
        from .course_services import create_offering

        offering, _ = create_offering(
            user=self.student,
            title="授業互換API",
            instructor="教員",
            academic_year=2026,
            semester="spring",
            day_of_week=1,
            period=3,
            force_create=True,
        )
        room, _membership, _created = join_course_talk(self.student, offering)
        message = ChatMessage.objects.create(room=room, sender=self.student, body="授業")
        self.assertEqual(room.kind, ChatRoom.Kind.COURSE)
        self.assertEqual(message.body, "授業")

    def test_org_profile_includes_recruiting_summary(self):
        self._create()
        self.client.force_login(self.student)
        profile = self.client.get(f"/api/v1/organizations/{self.org.slug}/")
        self.assertEqual(profile.status_code, 200)
        summary = profile.json()["recruiting_chat"]
        self.assertEqual(summary["name"], "2026新歓チャット")
        self.assertEqual(summary["membership_status"], "not_joined")
        self.assertTrue(summary["can_join"])
        self.assertIsNone(summary["room_id"])
        self.assertNotIn("@waseda.jp", json.dumps(profile.json()))

    def test_service_confirm_auto_approve_required(self):
        chat = create_recruiting_chat(
            organization=self.org,
            actor=self.owner,
            name="確認必須",
            join_mode=OrganizationRecruitingChat.JoinMode.APPROVAL,
        )
        join_or_apply_recruiting_chat(chat=chat, user=self.student)
        with self.assertRaises(OrganizationRecruitingChatError) as ctx:
            update_recruiting_chat_settings(
                chat=chat,
                actor=self.owner,
                join_mode=OrganizationRecruitingChat.JoinMode.OPEN,
            )
        self.assertEqual(ctx.exception.code, "confirm_auto_approve_required")
        self.assertEqual(ctx.exception.extra["pending_count"], 1)
