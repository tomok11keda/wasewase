"""Phase 3-D: cross-path ACL, privilege loss, sequential races, inbox refresh."""

from __future__ import annotations

import json

from django.test import Client, TestCase, override_settings

from .inbox_services import build_inbox_unread_summary
from .models import (
    ChatMessage,
    ChatReadState,
    ChatRoomMembership,
    ContentReport,
    Organization,
    OrganizationMember,
    OrganizationRecruitingChat,
    OrganizationRecruitingChatApplication,
    User,
    UserProfile,
)
from .organization_recruiting_chat_services import (
    OrganizationRecruitingChatError,
    approve_recruiting_application,
    create_recruiting_chat,
    join_or_apply_recruiting_chat,
    leave_recruiting_chat,
    reject_recruiting_application,
    remove_recruiting_participant,
    send_recruiting_chat_message,
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
    kwargs.setdefault("name", "3D新歓サークル")
    kwargs.setdefault("slug", "phase3d-circle")
    kwargs.setdefault("status", Organization.Status.ACTIVE)
    kwargs.setdefault("is_listed", True)
    return Organization.objects.create(**kwargs)


@override_settings(BROWSE_MODE_GATE_ENABLED=False)
class OrganizationRecruitingChatPhase3DTests(TestCase):
    def setUp(self):
        self.owner = _make_user("d-owner@waseda.jp", username="downer")
        self.admin = _make_user("d-admin@waseda.jp", username="dadmin")
        self.member = _make_user("d-member@waseda.jp", username="dmember")
        self.student = _make_user("d-student@waseda.jp", username="dstudent")
        self.pending_user = _make_user("d-pending@waseda.jp", username="dpending")
        self.stranger = _make_user("d-stranger@waseda.jp", username="dstranger")
        self.other_owner = _make_user("d-other@waseda.jp", username="dother")
        self.org = _make_org()
        self.other_org = _make_org(name="別3D団体", slug="phase3d-other")
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
        self.chat = create_recruiting_chat(
            organization=self.org,
            actor=self.owner,
            name="3D新歓",
            description="秘密ではない説明",
        )
        self.room_id = self.chat.room_id
        join_or_apply_recruiting_chat(chat=self.chat, user=self.student)
        send_recruiting_chat_message(self.chat.room, self.student, "参加しました秘密")

    def _org_url(self, suffix: str = "", slug: str | None = None) -> str:
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

    def _assert_no_message_leak(self, response, *, secret="参加しました秘密"):
        dumped = response.content.decode("utf-8", errors="replace")
        self.assertNotIn(secret, dumped)
        self.assertNotIn("@waseda.jp", dumped)
        content_type = response.headers.get("Content-Type", "")
        if not content_type.startswith("application/json"):
            return
        data = response.json()
        self.assertNotIn("messages", data)
        extra = data.get("message")
        if isinstance(extra, dict):
            self.fail("message object leaked in error payload")
        if isinstance(extra, str):
            self.assertNotIn(secret, extra)

    def test_unjoined_states_cannot_read_or_mutate_via_any_chat_api(self):
        approval = create_recruiting_chat(
            organization=self.other_org,
            actor=self.other_owner,
            name="承認制3D",
            join_mode=OrganizationRecruitingChat.JoinMode.APPROVAL,
        )
        pending = join_or_apply_recruiting_chat(
            chat=approval, user=self.pending_user
        )
        self.assertEqual(pending.status, "pending")

        paths = [
            f"/api/v1/recruiting-chats/{self.room_id}/",
            f"/api/v1/recruiting-chats/{self.room_id}/messages/",
            f"/api/v1/dm/groups/{self.room_id}/",
            f"/api/v1/dm/groups/{self.room_id}/messages/",
            f"/api/v1/flea/chats/{self.room_id}/",
            f"/api/v1/flea/chats/{self.room_id}/messages/",
        ]
        actors = [self.stranger, self.pending_user, self.member]
        for actor in actors:
            self.client.force_login(actor)
            for path in paths:
                res = self.client.get(path)
                self.assertIn(res.status_code, (403, 404), msg=f"{actor} GET {path}")
                self._assert_no_message_leak(res)
            send = self._json(
                "post",
                f"/api/v1/recruiting-chats/{self.room_id}/messages/send/",
                body="侵入",
            )
            self.assertEqual(send.status_code, 403)
            self._assert_no_message_leak(send)
            group_send = self._json(
                "post",
                f"/api/v1/dm/groups/{self.room_id}/messages/send/",
                body="グループ経由",
            )
            self.assertEqual(group_send.status_code, 404)

        guest = Client()
        unauth = guest.get(f"/api/v1/recruiting-chats/{self.room_id}/messages/")
        self.assertEqual(unauth.status_code, 401)
        self._assert_no_message_leak(unauth)

    def test_pending_rejected_withdrawn_have_no_room_id_or_inbox(self):
        chat = create_recruiting_chat(
            organization=self.other_org,
            actor=self.other_owner,
            name="申請状態",
            join_mode=OrganizationRecruitingChat.JoinMode.APPROVAL,
        )
        application = join_or_apply_recruiting_chat(chat=chat, user=self.pending_user)
        self.client.force_login(self.pending_user)
        pending = self.client.get(
            f"/api/v1/organizations/{self.other_org.slug}/recruiting-chat/"
        ).json()["recruiting_chat"]
        self.assertEqual(pending["membership_status"], "pending")
        self.assertIsNone(pending["room_id"])
        self.assertFalse(pending["can_send"])
        inbox = self.client.get("/api/v1/dm/inbox/").json()
        self.assertFalse(
            any(item["kind"] == "recruiting" for item in inbox["conversations"])
        )
        unread = build_inbox_unread_summary(self.pending_user)
        self.assertFalse(
            any(room.get("kind") == "recruiting" for room in unread["rooms"])
        )

        self.client.force_login(self.other_owner)
        reject_recruiting_application(
            chat=chat, application_id=application.pk, actor=self.other_owner
        )
        self.client.force_login(self.pending_user)
        rejected = self.client.get(
            f"/api/v1/organizations/{self.other_org.slug}/recruiting-chat/"
        ).json()["recruiting_chat"]
        self.assertEqual(rejected["membership_status"], "rejected")
        self.assertIsNone(rejected["room_id"])
        denied = self.client.get(f"/api/v1/recruiting-chats/{chat.room_id}/messages/")
        self.assertEqual(denied.status_code, 403)
        self._assert_no_message_leak(denied)

        reapplied = join_or_apply_recruiting_chat(chat=chat, user=self.pending_user)
        self.client.force_login(self.other_owner)
        approve_recruiting_application(
            chat=chat, application_id=reapplied.pk, actor=self.other_owner
        )
        leave_recruiting_chat(chat=chat, user=self.pending_user)
        self.client.force_login(self.pending_user)
        left = self.client.get(
            f"/api/v1/organizations/{self.other_org.slug}/recruiting-chat/"
        ).json()["recruiting_chat"]
        self.assertEqual(left["membership_status"], "not_joined")
        self.assertIsNone(left["room_id"])
        after_leave = self.client.get(
            f"/api/v1/recruiting-chats/{chat.room_id}/messages/"
        )
        self.assertEqual(after_leave.status_code, 403)
        self._assert_no_message_leak(after_leave)

    def test_leave_and_kick_immediately_revoke_message_access(self):
        self.client.force_login(self.student)
        before = self.client.get(f"/api/v1/recruiting-chats/{self.room_id}/")
        self.assertEqual(before.status_code, 200)
        bodies = [m["body"] for m in before.json()["messages"]]
        self.assertIn("参加しました秘密", bodies)

        leave_recruiting_chat(chat=self.chat, user=self.student)
        after = self.client.get(f"/api/v1/recruiting-chats/{self.room_id}/")
        self.assertEqual(after.status_code, 403)
        self._assert_no_message_leak(after)
        send = self._json(
            "post",
            f"/api/v1/recruiting-chats/{self.room_id}/messages/send/",
            body="退出直後",
        )
        self.assertEqual(send.status_code, 403)

        join_or_apply_recruiting_chat(chat=self.chat, user=self.student)
        self.client.force_login(self.owner)
        remove_recruiting_participant(
            chat=self.chat, actor=self.owner, user_id=self.student.pk
        )
        self.client.force_login(self.student)
        kicked = self.client.get(f"/api/v1/recruiting-chats/{self.room_id}/messages/")
        self.assertEqual(kicked.status_code, 403)
        self._assert_no_message_leak(kicked)
        inbox = self.client.get("/api/v1/dm/inbox/").json()
        self.assertFalse(
            any(item["kind"] == "recruiting" for item in inbox["conversations"])
        )

    def test_demote_and_suspend_revoke_management_immediately(self):
        self.client.force_login(self.admin)
        ok = self._json("patch", self._org_url(), description="管理者の更新")
        self.assertEqual(ok.status_code, 200)
        row = OrganizationMember.objects.get(organization=self.org, user=self.admin)
        set_organization_member_role(row, OrganizationMember.Role.MEMBER)
        lost = self._json("patch", self._org_url(), description="降格後")
        self.assertEqual(lost.status_code, 403)
        apps = self.client.get(self._org_url("applications/"))
        self.assertEqual(apps.status_code, 403)

        self.org.status = Organization.Status.SUSPENDED
        self.org.save(update_fields=["status", "updated_at"])
        self.client.force_login(self.owner)
        suspended_patch = self._json("patch", self._org_url(), name="停止後")
        self.assertEqual(suspended_patch.status_code, 403)
        self.client.force_login(self.stranger)
        join = self._json("post", self._org_url("join/"))
        self.assertIn(join.status_code, (403, 404))

    def test_suspended_org_hides_inbox_and_blocks_existing_member_messages(self):
        message = ChatMessage.objects.filter(room_id=self.room_id).latest("pk")
        ChatReadState.objects.update_or_create(
            room_id=self.room_id,
            user=self.student,
            defaults={"last_read_message_id": message.pk},
        )
        previous_read = ChatReadState.objects.get(
            room_id=self.room_id, user=self.student
        ).last_read_message_id
        membership_exists = ChatRoomMembership.objects.filter(
            room_id=self.room_id, user=self.student
        ).exists()
        self.assertTrue(membership_exists)
        application_count = OrganizationRecruitingChatApplication.objects.filter(
            recruiting_chat=self.chat
        ).count()

        self.org.status = Organization.Status.SUSPENDED
        self.org.save(update_fields=["status", "updated_at"])

        for actor in (self.student, self.owner):
            self.client.force_login(actor)
            messages = self.client.get(
                f"/api/v1/recruiting-chats/{self.room_id}/messages/"
            )
            self.assertEqual(messages.status_code, 403)
            self._assert_no_message_leak(messages)
            send = self._json(
                "post",
                f"/api/v1/recruiting-chats/{self.room_id}/messages/send/",
                body="停止中送信",
            )
            self.assertEqual(send.status_code, 403)
            self._assert_no_message_leak(send)
            inbox = self.client.get("/api/v1/dm/inbox/").json()
            self.assertFalse(
                any(item["kind"] == "recruiting" for item in inbox["conversations"])
            )

        self.client.force_login(self.owner)
        apps = self.client.get(self._org_url("applications/"))
        self.assertEqual(apps.status_code, 403)
        self.assertTrue(
            ChatRoomMembership.objects.filter(
                room_id=self.room_id, user=self.student
            ).exists()
        )
        self.assertEqual(
            OrganizationRecruitingChatApplication.objects.filter(
                recruiting_chat=self.chat
            ).count(),
            application_count,
        )
        self.assertTrue(ChatMessage.objects.filter(pk=message.pk).exists())
        self.assertEqual(
            ChatReadState.objects.get(
                room_id=self.room_id, user=self.student
            ).last_read_message_id,
            previous_read,
        )

        self.org.status = Organization.Status.ACTIVE
        self.org.save(update_fields=["status", "updated_at"])
        self.client.force_login(self.student)
        restored = self.client.get(
            f"/api/v1/recruiting-chats/{self.room_id}/messages/"
        )
        self.assertEqual(restored.status_code, 200)
        bodies = [m["body"] for m in restored.json()["messages"]]
        self.assertIn("参加しました秘密", bodies)
        inbox = self.client.get("/api/v1/dm/inbox/").json()
        self.assertTrue(
            any(item["kind"] == "recruiting" for item in inbox["conversations"])
        )

    def test_report_and_appeal_do_not_reveal_recruiting_bodies(self):
        message = ChatMessage.objects.filter(room_id=self.room_id).latest("pk")
        self.assertIsNone(
            get_report_target(
                ContentReport.TargetType.CHAT_MESSAGE,
                message.pk,
                viewer=None,
            )
        )
        self.assertIsNone(
            get_report_target(
                ContentReport.TargetType.CHAT_MESSAGE,
                message.pk,
                viewer=self.stranger,
            )
        )
        self.client.force_login(self.stranger)
        report = self.client.post(
            f"/report/chat_message/{message.pk}/",
            data={"reason": "spam"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(report.status_code, 404)
        self._assert_no_message_leak(report)
        appeal = self._json(
            "post",
            f"/api/v1/chat/messages/{message.pk}/appeals/",
            explanation="知りません",
        )
        self.assertEqual(appeal.status_code, 403)
        self._assert_no_message_leak(appeal)

    def test_classic_group_html_and_search_do_not_expose_recruiting(self):
        self.client.force_login(self.stranger)
        html = self.client.get(f"/dm/groups/{self.room_id}/")
        self.assertIn(html.status_code, (301, 302, 404))
        if html.status_code in (301, 302):
            follow = self.client.get(html["Location"])
            dumped = follow.content.decode("utf-8", errors="replace")
            self.assertNotIn("参加しました秘密", dumped)
        search = self.client.get("/api/v1/search/?q=参加しました秘密")
        self.assertEqual(search.status_code, 200)
        self.assertNotIn("参加しました秘密", search.content.decode())

    def test_approve_then_inbox_appears_reject_then_not_pending(self):
        chat = create_recruiting_chat(
            organization=self.other_org,
            actor=self.other_owner,
            name="承認後inbox",
            join_mode=OrganizationRecruitingChat.JoinMode.APPROVAL,
        )
        application = join_or_apply_recruiting_chat(chat=chat, user=self.pending_user)
        self.client.force_login(self.other_owner)
        listed = self.client.get(
            f"/api/v1/organizations/{self.other_org.slug}/recruiting-chat/applications/?status=pending"
        ).json()
        self.assertEqual(listed["pending_count"], 1)
        approve_recruiting_application(
            chat=chat, application_id=application.pk, actor=self.other_owner
        )
        after = self.client.get(
            f"/api/v1/organizations/{self.other_org.slug}/recruiting-chat/applications/?status=pending"
        ).json()
        self.assertEqual(after["pending_count"], 0)
        members = self.client.get(
            f"/api/v1/organizations/{self.other_org.slug}/recruiting-chat/members/"
        ).json()
        self.assertTrue(
            any(row["user_id"] == self.pending_user.pk for row in members["members"])
        )
        self.client.force_login(self.pending_user)
        inbox = self.client.get("/api/v1/dm/inbox/").json()
        recruiting = [
            item for item in inbox["conversations"] if item["kind"] == "recruiting"
        ]
        self.assertEqual(len(recruiting), 1)
        self.assertEqual(
            recruiting[0]["spa_path"],
            f"/organizations/{self.other_org.slug}/recruiting-chat",
        )

    def test_sequential_races_are_rejected_without_duplicate_membership(self):
        self.client.force_login(self.owner)
        duplicate = self._json("post", self._org_url(), name="二重作成")
        self.assertEqual(duplicate.status_code, 409)

        approval = create_recruiting_chat(
            organization=self.other_org,
            actor=self.other_owner,
            name="競合申請",
            join_mode=OrganizationRecruitingChat.JoinMode.APPROVAL,
        )
        first = join_or_apply_recruiting_chat(chat=approval, user=self.pending_user)
        with self.assertRaises(OrganizationRecruitingChatError) as pending_twice:
            join_or_apply_recruiting_chat(chat=approval, user=self.pending_user)
        self.assertEqual(pending_twice.exception.code, "already_pending")

        approve_recruiting_application(
            chat=approval, application_id=first.pk, actor=self.other_owner
        )
        with self.assertRaises(OrganizationRecruitingChatError) as after_approve:
            reject_recruiting_application(
                chat=approval, application_id=first.pk, actor=self.other_owner
            )
        self.assertEqual(after_approve.exception.code, "not_pending")

        update_recruiting_chat_settings(
            chat=approval,
            actor=self.other_owner,
            listing_status=OrganizationRecruitingChat.ListingStatus.CLOSED,
        )
        with self.assertRaises(OrganizationRecruitingChatError) as closed:
            join_or_apply_recruiting_chat(chat=approval, user=self.stranger)
        self.assertEqual(closed.exception.code, "listing_closed")

        with self.assertRaises(OrganizationRecruitingChatError) as unconfirmed:
            update_recruiting_chat_settings(
                chat=self.chat,
                actor=self.owner,
                join_mode=OrganizationRecruitingChat.JoinMode.APPROVAL,
            )
            join_or_apply_recruiting_chat(chat=self.chat, user=self.stranger)
            update_recruiting_chat_settings(
                chat=self.chat,
                actor=self.owner,
                join_mode=OrganizationRecruitingChat.JoinMode.OPEN,
            )
        self.assertEqual(unconfirmed.exception.code, "confirm_auto_approve_required")

    def test_org_member_cannot_manage_and_other_org_ids_404(self):
        self.client.force_login(self.member)
        patch = self._json("patch", self._org_url(), name="所属member")
        self.assertEqual(patch.status_code, 403)
        apps = self.client.get(self._org_url("applications/"))
        self.assertEqual(apps.status_code, 403)
        self.client.force_login(self.other_owner)
        other = self._json("patch", self._org_url(), name="別団体")
        self.assertEqual(other.status_code, 403)

    def test_anonymous_discovery_has_no_room_id(self):
        guest = Client()
        res = guest.get(self._org_url())
        self.assertEqual(res.status_code, 200)
        chat = res.json()["recruiting_chat"]
        self.assertIsNone(chat["room_id"])
        self.assertFalse(chat["can_join"])
        self.assertFalse(chat["can_manage"])
        self.assertNotIn("@waseda.jp", json.dumps(res.json()))
