"""Phase 3-A: 新歓チャットのモデル・権限・既存チャット互換。"""

from __future__ import annotations

import json

from django.db import IntegrityError, transaction
from django.test import Client, TestCase, override_settings

from .chat_message_services import create_chat_message
from .course_chat_services import get_or_create_course_talk_room, join_course_talk
from .course_services import create_offering
from .models import (
    ChatMessage,
    ChatReadState,
    ChatRoom,
    ChatRoomMembership,
    ContentReport,
    Follow,
    Organization,
    OrganizationMember,
    OrganizationRecruitingChat,
    OrganizationRecruitingChatApplication,
    User,
    UserBlock,
    UserProfile,
)
from .organization_recruiting_chat_services import (
    OrganizationRecruitingChatError,
    approve_recruiting_application,
    can_access_recruiting_room,
    create_recruiting_chat,
    deactivate_recruiting_chat,
    join_or_apply_recruiting_chat,
    leave_recruiting_chat,
    list_recruiting_applications,
    list_recruiting_messages,
    list_recruiting_participants,
    list_recruiting_rooms_for_user,
    reject_recruiting_application,
    remove_recruiting_participant,
    send_recruiting_chat_message,
    serialize_recruiting_chat_for_viewer,
    serialize_recruiting_participant,
    update_recruiting_chat_settings,
)
from .organization_services import add_organization_member, set_organization_member_role
from .services import can_access_chat_room
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
    kwargs.setdefault("name", "新歓サークル")
    kwargs.setdefault("slug", "recruiting-circle")
    kwargs.setdefault("status", Organization.Status.ACTIVE)
    kwargs.setdefault("is_listed", True)
    return Organization.objects.create(**kwargs)


@override_settings(BROWSE_MODE_GATE_ENABLED=False)
class OrganizationRecruitingChatFoundationTests(TestCase):
    def setUp(self):
        self.owner = _make_user("rec-owner@waseda.jp", username="recowner")
        self.admin = _make_user("rec-admin@waseda.jp", username="recadmin")
        self.member = _make_user("rec-member@waseda.jp", username="recmember")
        self.student = _make_user("rec-student@waseda.jp", username="recstudent")
        self.stranger = _make_user("rec-stranger@waseda.jp", username="recstranger")
        self.other_owner = _make_user("rec-other@waseda.jp", username="recother")
        self.org = _make_org()
        self.other_org = _make_org(name="別団体", slug="other-recruiting-org")
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

    def _create_chat(self, actor=None, **kwargs):
        kwargs.setdefault("name", "2026新歓")
        kwargs.setdefault("description", "新入生向け")
        return create_recruiting_chat(
            organization=self.org,
            actor=actor or self.owner,
            **kwargs,
        )

    def test_owner_and_admin_can_create_member_cannot(self):
        chat = self._create_chat()
        self.assertEqual(chat.room.kind, ChatRoom.Kind.RECRUITING)
        self.assertTrue(chat.is_active)
        with self.assertRaises(OrganizationRecruitingChatError) as ctx:
            create_recruiting_chat(
                organization=self.org,
                actor=self.member,
                name="メンバー作成",
            )
        self.assertEqual(ctx.exception.code, "forbidden")
        with self.assertRaises(OrganizationRecruitingChatError):
            create_recruiting_chat(
                organization=self.org,
                actor=self.other_owner,
                name="別団体",
            )

    def test_one_active_chat_per_organization_allows_history(self):
        first = self._create_chat()
        with self.assertRaises(OrganizationRecruitingChatError) as ctx:
            self._create_chat(name="二重")
        self.assertEqual(ctx.exception.code, "already_exists")
        deactivate_recruiting_chat(chat=first, actor=self.owner)
        second = self._create_chat(name="2027新歓")
        self.assertTrue(second.is_active)
        first.refresh_from_db()
        self.assertFalse(first.is_active)
        self.assertEqual(
            OrganizationRecruitingChat.objects.filter(
                organization=self.org, is_active=True
            ).count(),
            1,
        )
        with transaction.atomic():
            with self.assertRaises(IntegrityError):
                OrganizationRecruitingChat.objects.create(
                    organization=self.org,
                    room=ChatRoom.objects.create(
                        kind=ChatRoom.Kind.RECRUITING, name="不正"
                    ),
                    name="不正",
                    is_active=True,
                )

    def test_join_does_not_create_organization_member(self):
        chat = self._create_chat()
        before = OrganizationMember.objects.filter(organization=self.org).count()
        application = join_or_apply_recruiting_chat(chat=chat, user=self.student)
        self.assertEqual(
            application.status,
            OrganizationRecruitingChatApplication.Status.APPROVED,
        )
        self.assertTrue(
            ChatRoomMembership.objects.filter(room=chat.room, user=self.student).exists()
        )
        self.assertFalse(
            OrganizationMember.objects.filter(
                organization=self.org, user=self.student
            ).exists()
        )
        self.assertEqual(
            OrganizationMember.objects.filter(organization=self.org).count(),
            before,
        )

    def test_open_join_duplicate_and_pending_access_denied(self):
        chat = self._create_chat(
            join_mode=OrganizationRecruitingChat.JoinMode.APPROVAL
        )
        pending = join_or_apply_recruiting_chat(chat=chat, user=self.student)
        self.assertEqual(
            pending.status, OrganizationRecruitingChatApplication.Status.PENDING
        )
        with self.assertRaises(OrganizationRecruitingChatError) as ctx:
            join_or_apply_recruiting_chat(chat=chat, user=self.student)
        self.assertEqual(ctx.exception.code, "already_pending")
        self.assertFalse(can_access_recruiting_room(chat.room, self.student))
        with self.assertRaises(OrganizationRecruitingChatError):
            send_recruiting_chat_message(chat.room, self.student, "まだ見えない")
        with self.assertRaises(OrganizationRecruitingChatError):
            list_recruiting_messages(chat.room, self.student)
        self.assertFalse(
            ChatRoomMembership.objects.filter(room=chat.room, user=self.student).exists()
        )

    def test_unrelated_user_cannot_read_or_send(self):
        chat = self._create_chat()
        join_or_apply_recruiting_chat(chat=chat, user=self.student)
        send_recruiting_chat_message(chat.room, self.student, "参加者の投稿")
        self.assertFalse(can_access_recruiting_room(chat.room, self.stranger))
        with self.assertRaises(OrganizationRecruitingChatError) as ctx:
            create_chat_message(chat.room, self.stranger, "侵入")
        self.assertEqual(ctx.exception.code, "forbidden")
        with self.assertRaises(OrganizationRecruitingChatError):
            list_recruiting_messages(chat.room, self.stranger)

    def test_approve_reject_permissions_and_idor(self):
        chat = self._create_chat(
            join_mode=OrganizationRecruitingChat.JoinMode.APPROVAL
        )
        other_chat = create_recruiting_chat(
            organization=self.other_org,
            actor=self.other_owner,
            name="別新歓",
            join_mode=OrganizationRecruitingChat.JoinMode.APPROVAL,
        )
        application = join_or_apply_recruiting_chat(chat=chat, user=self.student)
        other_app = join_or_apply_recruiting_chat(chat=other_chat, user=self.stranger)
        with self.assertRaises(OrganizationRecruitingChatError):
            approve_recruiting_application(
                chat=chat, application_id=application.pk, actor=self.stranger
            )
        with self.assertRaises(OrganizationRecruitingChatError):
            approve_recruiting_application(
                chat=chat, application_id=application.pk, actor=self.member
            )
        with self.assertRaises(OrganizationRecruitingChatError):
            approve_recruiting_application(
                chat=chat, application_id=application.pk, actor=self.other_owner
            )
        with self.assertRaises(OrganizationRecruitingChatError) as ctx:
            approve_recruiting_application(
                chat=chat, application_id=other_app.pk, actor=self.owner
            )
        self.assertEqual(ctx.exception.code, "not_found")
        approved = approve_recruiting_application(
            chat=chat, application_id=application.pk, actor=self.admin
        )
        self.assertEqual(
            approved.status, OrganizationRecruitingChatApplication.Status.APPROVED
        )
        self.assertTrue(can_access_recruiting_room(chat.room, self.student))
        send_recruiting_chat_message(chat.room, self.student, "承認後")
        with self.assertRaises(OrganizationRecruitingChatError):
            reject_recruiting_application(
                chat=chat, application_id=application.pk, actor=self.owner
            )

    def test_reject_then_reapply_and_leave_stops_send(self):
        chat = self._create_chat(
            join_mode=OrganizationRecruitingChat.JoinMode.APPROVAL
        )
        application = join_or_apply_recruiting_chat(chat=chat, user=self.student)
        reject_recruiting_application(
            chat=chat, application_id=application.pk, actor=self.owner
        )
        application.refresh_from_db()
        self.assertEqual(
            application.status, OrganizationRecruitingChatApplication.Status.REJECTED
        )
        self.assertFalse(can_access_recruiting_room(chat.room, self.student))
        reapplied = join_or_apply_recruiting_chat(chat=chat, user=self.student)
        self.assertEqual(
            reapplied.status, OrganizationRecruitingChatApplication.Status.PENDING
        )
        self.assertEqual(
            OrganizationRecruitingChatApplication.objects.filter(
                recruiting_chat=chat, user=self.student
            ).count(),
            1,
        )
        approve_recruiting_application(
            chat=chat, application_id=reapplied.pk, actor=self.owner
        )
        send_recruiting_chat_message(chat.room, self.student, "参加中")
        leave_recruiting_chat(chat=chat, user=self.student)
        self.assertFalse(can_access_recruiting_room(chat.room, self.student))
        with self.assertRaises(OrganizationRecruitingChatError):
            send_recruiting_chat_message(chat.room, self.student, "退出後")
        with self.assertRaises(OrganizationRecruitingChatError):
            list_recruiting_messages(chat.room, self.student)

    def test_switch_to_open_auto_approves_pending(self):
        chat = self._create_chat(
            join_mode=OrganizationRecruitingChat.JoinMode.APPROVAL
        )
        pending = join_or_apply_recruiting_chat(chat=chat, user=self.student)
        update_recruiting_chat_settings(
            chat=chat,
            actor=self.owner,
            join_mode=OrganizationRecruitingChat.JoinMode.OPEN,
            confirm_auto_approve=True,
        )
        pending.refresh_from_db()
        self.assertEqual(
            pending.status, OrganizationRecruitingChatApplication.Status.APPROVED
        )
        self.assertTrue(
            ChatRoomMembership.objects.filter(room=chat.room, user=self.student).exists()
        )
        send_recruiting_chat_message(chat.room, self.student, "自動承認後")

    def test_suspended_org_blocks_new_joins_and_management(self):
        chat = self._create_chat()
        join_or_apply_recruiting_chat(chat=chat, user=self.student)
        secret = send_recruiting_chat_message(chat.room, self.student, "停止前の本文")
        ChatReadState.objects.update_or_create(
            room=chat.room,
            user=self.student,
            defaults={"last_read_message_id": secret.pk},
        )
        previous_read = ChatReadState.objects.get(
            room=chat.room, user=self.student
        ).last_read_message_id
        membership_count = ChatRoomMembership.objects.filter(room=chat.room).count()
        application_count = OrganizationRecruitingChatApplication.objects.filter(
            recruiting_chat=chat
        ).count()
        self.org.status = Organization.Status.SUSPENDED
        self.org.save(update_fields=["status", "updated_at"])
        chat.refresh_from_db()
        self.org.refresh_from_db()

        self.assertFalse(can_access_recruiting_room(chat.room, self.student))
        self.assertFalse(can_access_recruiting_room(chat.room, self.owner))
        with self.assertRaises(OrganizationRecruitingChatError) as ctx:
            list_recruiting_messages(chat.room, self.student)
        self.assertEqual(ctx.exception.status, 403)
        with self.assertRaises(OrganizationRecruitingChatError):
            send_recruiting_chat_message(chat.room, self.student, "停止中は送れない")
        with self.assertRaises(OrganizationRecruitingChatError):
            send_recruiting_chat_message(chat.room, self.owner, "管理者も送れない")
        with self.assertRaises(OrganizationRecruitingChatError) as join_ctx:
            join_or_apply_recruiting_chat(chat=chat, user=self.stranger)
        self.assertEqual(join_ctx.exception.code, "organization_suspended")
        with self.assertRaises(OrganizationRecruitingChatError):
            update_recruiting_chat_settings(
                chat=chat, actor=self.owner, name="停止中"
            )
        self.assertEqual(list(list_recruiting_rooms_for_user(self.student)), [])
        self.assertEqual(list(list_recruiting_rooms_for_user(self.owner)), [])
        self.assertIsNone(
            get_report_target(
                ContentReport.TargetType.CHAT_MESSAGE,
                secret.pk,
                viewer=self.student,
            )
        )
        payload = serialize_recruiting_chat_for_viewer(chat, self.student)
        self.assertFalse(payload["can_discover"])
        self.assertFalse(payload["can_join"])
        self.assertFalse(payload["can_send"])
        self.assertIsNone(payload["room_id"])

        self.assertTrue(
            ChatRoomMembership.objects.filter(room=chat.room, user=self.student).exists()
        )
        self.assertEqual(
            ChatRoomMembership.objects.filter(room=chat.room).count(), membership_count
        )
        self.assertEqual(
            OrganizationRecruitingChatApplication.objects.filter(
                recruiting_chat=chat
            ).count(),
            application_count,
        )
        self.assertTrue(ChatMessage.objects.filter(pk=secret.pk).exists())
        self.assertEqual(
            ChatReadState.objects.get(room=chat.room, user=self.student).last_read_message_id,
            previous_read,
        )

        self.org.status = Organization.Status.ACTIVE
        self.org.save(update_fields=["status", "updated_at"])
        self.assertTrue(can_access_recruiting_room(chat.room, self.student))
        bodies = [m.body for m in list_recruiting_messages(chat.room, self.student)]
        self.assertIn("停止前の本文", bodies)
        send_recruiting_chat_message(chat.room, self.student, "復帰後")
        self.assertEqual(
            [room.pk for room in list_recruiting_rooms_for_user(self.student)],
            [chat.room_id],
        )

    def test_lost_admin_role_cannot_manage(self):
        chat = self._create_chat(
            join_mode=OrganizationRecruitingChat.JoinMode.APPROVAL
        )
        application = join_or_apply_recruiting_chat(chat=chat, user=self.student)
        admin_row = OrganizationMember.objects.get(
            organization=self.org, user=self.admin
        )
        set_organization_member_role(admin_row, OrganizationMember.Role.MEMBER)
        with self.assertRaises(OrganizationRecruitingChatError):
            approve_recruiting_application(
                chat=chat, application_id=application.pk, actor=self.admin
            )

    def test_deleting_recruiting_chat_removes_room(self):
        chat = self._create_chat()
        room_id = chat.room_id
        chat.delete()
        self.assertFalse(ChatRoom.objects.filter(pk=room_id).exists())

    def test_unique_application_and_membership_constraints(self):
        chat = self._create_chat()
        join_or_apply_recruiting_chat(chat=chat, user=self.student)
        with transaction.atomic():
            with self.assertRaises(IntegrityError):
                OrganizationRecruitingChatApplication.objects.create(
                    recruiting_chat=chat,
                    user=self.student,
                )
        with transaction.atomic():
            with self.assertRaises(IntegrityError):
                ChatRoomMembership.objects.create(room=chat.room, user=self.student)

    def test_applications_and_participants_hide_email(self):
        chat = self._create_chat()
        join_or_apply_recruiting_chat(chat=chat, user=self.student)
        with self.assertRaises(OrganizationRecruitingChatError):
            list_recruiting_applications(chat=chat, actor=self.student)
        rows = list_recruiting_applications(chat=chat, actor=self.owner)
        self.assertEqual(len(rows), 1)
        self.assertNotIn("email", rows[0])
        self.assertNotIn(self.student.email, json.dumps(rows))
        participants = list_recruiting_participants(chat=chat, viewer=self.student)
        self.assertEqual(len(participants), 1)
        self.assertNotIn("email", participants[0])
        self.assertNotIn(self.student.email, json.dumps(participants))
        with self.assertRaises(OrganizationRecruitingChatError):
            list_recruiting_participants(chat=chat, viewer=self.stranger)

    def test_kick_and_wrong_user_id(self):
        chat = self._create_chat()
        join_or_apply_recruiting_chat(chat=chat, user=self.student)
        with self.assertRaises(OrganizationRecruitingChatError) as ctx:
            remove_recruiting_participant(
                chat=chat, actor=self.owner, user_id=self.stranger.pk
            )
        self.assertEqual(ctx.exception.code, "not_member")
        remove_recruiting_participant(
            chat=chat, actor=self.owner, user_id=self.student.pk
        )
        self.assertFalse(can_access_recruiting_room(chat.room, self.student))

    def test_manager_can_access_without_membership(self):
        chat = self._create_chat()
        self.assertTrue(can_access_recruiting_room(chat.room, self.owner))
        self.assertFalse(
            ChatRoomMembership.objects.filter(room=chat.room, user=self.owner).exists()
        )
        send_recruiting_chat_message(chat.room, self.owner, "管理者から")
        rooms = list(list_recruiting_rooms_for_user(self.owner))
        self.assertEqual([room.pk for room in rooms], [chat.room_id])
        self.assertEqual(list(list_recruiting_rooms_for_user(self.stranger)), [])

    def test_recruiting_room_is_isolated_from_group_and_trade_acl(self):
        chat = self._create_chat()
        join_or_apply_recruiting_chat(chat=chat, user=self.student)
        self.client.force_login(self.student)
        group = self.client.get(f"/api/v1/dm/groups/{chat.room_id}/")
        self.assertEqual(group.status_code, 404)
        send = self.client.post(
            f"/api/v1/dm/groups/{chat.room_id}/messages/send/",
            data=json.dumps({"body": "グループ経由"}),
            content_type="application/json",
        )
        self.assertEqual(send.status_code, 404)
        self.assertFalse(can_access_chat_room(chat.room, self.student))

    def test_personal_dm_still_works(self):
        Follow.objects.create(follower=self.student, following=self.stranger)
        self.client.force_login(self.student)
        start = self.client.post(
            "/api/v1/dm/start/",
            data=json.dumps({"user_id": self.stranger.pk}),
            content_type="application/json",
        )
        self.assertEqual(start.status_code, 200)
        room_id = start.json()["room_id"]
        send = self.client.post(
            f"/api/v1/dm/rooms/{room_id}/messages/send/",
            data=json.dumps({"body": "DM互換"}),
            content_type="application/json",
        )
        self.assertEqual(send.status_code, 201)

    def test_existing_group_chat_still_works(self):
        Follow.objects.create(follower=self.student, following=self.stranger)
        self.client.force_login(self.student)
        created = self.client.post(
            "/api/v1/dm/groups/",
            data=json.dumps({"name": "既存グループ", "member_ids": [self.stranger.pk]}),
            content_type="application/json",
        )
        self.assertEqual(created.status_code, 201)
        room_id = created.json()["room_id"]
        room = ChatRoom.objects.get(pk=room_id)
        self.assertEqual(room.kind, ChatRoom.Kind.GROUP)
        send = self.client.post(
            f"/api/v1/dm/groups/{room_id}/messages/send/",
            data=json.dumps({"body": "グループ互換"}),
            content_type="application/json",
        )
        self.assertEqual(send.status_code, 201)

    def test_course_chat_still_works(self):
        offering, _ = create_offering(
            user=self.student,
            title="授業トーク互換",
            instructor="教員",
            academic_year=2026,
            semester="spring",
            day_of_week=1,
            period=2,
            force_create=True,
        )
        room, _membership, _created = join_course_talk(self.student, offering)
        message = create_chat_message(room, self.student, "授業互換")
        self.assertEqual(room.kind, ChatRoom.Kind.COURSE)
        self.assertEqual(message.body, "授業互換")
        self.assertIsNotNone(get_or_create_course_talk_room(offering)[0])

    def test_block_and_report_compatibility(self):
        chat = self._create_chat()
        join_or_apply_recruiting_chat(chat=chat, user=self.student)
        message = send_recruiting_chat_message(chat.room, self.student, "通報対象")
        UserBlock.objects.create(blocker=self.owner, blocked=self.student)
        send_recruiting_chat_message(chat.room, self.student, "ブロック後も新歓は送れる")
        Follow.objects.create(follower=self.owner, following=self.student)
        self.client.force_login(self.owner)
        dm = self.client.post(
            "/api/v1/dm/start/",
            data=json.dumps({"user_id": self.student.pk}),
            content_type="application/json",
        )
        self.assertEqual(dm.status_code, 400)
        self.assertEqual(dm.json()["error"], "blocked")
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
        self.assertEqual(
            get_report_target(
                ContentReport.TargetType.CHAT_MESSAGE,
                message.pk,
                viewer=self.student,
            ).pk,
            message.pk,
        )
        group = ChatRoom.objects.create(kind=ChatRoom.Kind.GROUP, name="通報グループ")
        ChatRoomMembership.objects.create(room=group, user=self.owner)
        group_message = create_chat_message(group, self.owner, "グループ通報")
        self.assertEqual(
            get_report_target(
                ContentReport.TargetType.CHAT_MESSAGE,
                group_message.pk,
                viewer=self.stranger,
            ).pk,
            group_message.pk,
        )

    def test_private_profile_is_not_expanded_by_joining(self):
        profile = self.student.profile
        profile.is_private = True
        profile.save(update_fields=["is_private"])
        chat = self._create_chat()
        join_or_apply_recruiting_chat(chat=chat, user=self.student)
        from .follow_services import can_view_private_content

        self.assertFalse(can_view_private_content(self.owner, self.student))
        payload = serialize_recruiting_participant(
            ChatRoomMembership.objects.get(room=chat.room, user=self.student)
        )
        self.assertNotIn("email", payload)
        self.assertNotIn("is_private", payload)

    def test_listing_closed_and_draft_org_discovery(self):
        chat = self._create_chat()
        join_or_apply_recruiting_chat(chat=chat, user=self.student)
        update_recruiting_chat_settings(
            chat=chat,
            actor=self.owner,
            listing_status=OrganizationRecruitingChat.ListingStatus.CLOSED,
        )
        with self.assertRaises(OrganizationRecruitingChatError) as ctx:
            join_or_apply_recruiting_chat(chat=chat, user=self.stranger)
        self.assertEqual(ctx.exception.code, "listing_closed")
        self.assertTrue(can_access_recruiting_room(chat.room, self.student))
        send_recruiting_chat_message(chat.room, self.student, "募集停止後も会話可")
        self.assertEqual(
            [room.pk for room in list_recruiting_rooms_for_user(self.student)],
            [chat.room_id],
        )
        draft = _make_org(name="下書き", slug="draft-rec-org", status=Organization.Status.DRAFT, is_listed=False)
        add_organization_member(draft, self.owner, role=OrganizationMember.Role.OWNER)
        draft_chat = create_recruiting_chat(
            organization=draft, actor=self.owner, name="下書き新歓"
        )
        with self.assertRaises(OrganizationRecruitingChatError) as ctx:
            join_or_apply_recruiting_chat(chat=draft_chat, user=self.student)
        self.assertEqual(ctx.exception.code, "organization_not_viewable")


class OrganizationRecruitingChatTransactionTests(TestCase):
    def setUp(self):
        self.owner = _make_user("tx-owner@waseda.jp")
        self.student = _make_user("tx-student@waseda.jp")
        self.org = _make_org(slug="tx-rec-org")
        add_organization_member(
            self.org, self.owner, role=OrganizationMember.Role.OWNER
        )

    def test_approve_reject_conflict_uses_row_lock_status(self):
        chat = create_recruiting_chat(
            organization=self.org,
            actor=self.owner,
            name="競合",
            join_mode=OrganizationRecruitingChat.JoinMode.APPROVAL,
        )
        application = join_or_apply_recruiting_chat(chat=chat, user=self.student)
        approve_recruiting_application(
            chat=chat, application_id=application.pk, actor=self.owner
        )
        with self.assertRaises(OrganizationRecruitingChatError) as ctx:
            reject_recruiting_application(
                chat=chat, application_id=application.pk, actor=self.owner
            )
        self.assertEqual(ctx.exception.code, "not_pending")
        self.assertTrue(
            ChatRoomMembership.objects.filter(room=chat.room, user=self.student).exists()
        )
        self.assertEqual(
            OrganizationRecruitingChatApplication.objects.get(pk=application.pk).status,
            OrganizationRecruitingChatApplication.Status.APPROVED,
        )
        self.assertFalse(
            OrganizationMember.objects.filter(
                organization=self.org, user=self.student
            ).exists()
        )
