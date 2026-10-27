"""Phase 2: multiple organization chats, visibility modes, event share."""

from __future__ import annotations

import json
from datetime import timedelta

from django.test import Client, TestCase, override_settings
from django.utils import timezone

from .chat_message_services import create_chat_message
from .models import (
    ChatMessage,
    ChatRoomMembership,
    Organization,
    OrganizationChatShare,
    OrganizationMember,
    OrganizationRecruitingChat,
    User,
    UserProfile,
)
from .organization_event_lottery_services import (
    run_organization_event_lottery,
    share_organization_event_lottery,
)
from .organization_event_services import (
    OrganizationEventError,
    create_organization_event,
    publish_organization_event,
    register_organization_event,
    share_organization_event_to_chat,
)
from .organization_recruiting_chat_services import (
    OrganizationRecruitingChatError,
    can_access_recruiting_room,
    create_recruiting_chat,
    join_or_apply_recruiting_chat,
    list_visible_organization_chats,
    send_recruiting_chat_message,
    serialize_recruiting_chat_for_viewer,
)
from .organization_services import add_organization_member, can_manage_organization


def _make_user(email: str, **kwargs) -> User:
    kwargs.setdefault("password", "test-pass-12345")
    user = User.objects.create_user(email=email, **kwargs)
    UserProfile.objects.get_or_create(
        user=user,
        defaults={"name": kwargs.get("username") or email.split("@")[0]},
    )
    return user


def _make_org(**kwargs) -> Organization:
    kwargs.setdefault("name", "マルチチャット団体")
    kwargs.setdefault("slug", "multi-chat-org")
    kwargs.setdefault("status", Organization.Status.ACTIVE)
    kwargs.setdefault("is_listed", True)
    return Organization.objects.create(**kwargs)


@override_settings(BROWSE_MODE_GATE_ENABLED=False, MAX_ACTIVE_ORGANIZATION_CHATS=3)
class OrganizationMultiChatTests(TestCase):
    def setUp(self):
        self.owner = _make_user("mc-owner@waseda.jp", username="mcowner")
        self.admin = _make_user("mc-admin@waseda.jp", username="mcadmin")
        self.member = _make_user("mc-member@waseda.jp", username="mcmember")
        self.student = _make_user("mc-student@waseda.jp", username="mcstudent")
        self.stranger = _make_user("mc-stranger@waseda.jp", username="mcstranger")
        self.org = _make_org()
        add_organization_member(
            self.org, self.owner, role=OrganizationMember.Role.OWNER
        )
        add_organization_member(
            self.org, self.admin, role=OrganizationMember.Role.ADMIN
        )
        add_organization_member(
            self.org, self.member, role=OrganizationMember.Role.MEMBER
        )
        self.client = Client()

    def _json(self, method: str, url: str, **payload):
        handler = getattr(self.client, method.lower())
        if payload:
            return handler(
                url,
                data=json.dumps(payload),
                content_type="application/json",
            )
        return handler(url)

    def _url(self, suffix: str = "", chat_id: int | None = None) -> str:
        url = f"/api/v1/organizations/{self.org.slug}/recruiting-chat/{suffix}"
        if chat_id:
            sep = "&" if "?" in url else "?"
            return f"{url}{sep}chat={chat_id}"
        return url

    def _create_chat(self, **kwargs):
        kwargs.setdefault("name", "公開チャット")
        return create_recruiting_chat(
            organization=self.org, actor=self.owner, **kwargs
        )

    def test_create_multiple_modes_and_cap(self):
        open_chat = self._create_chat(
            name="A 公開自由",
            join_mode=OrganizationRecruitingChat.JoinMode.OPEN,
        )
        approval = self._create_chat(
            name="B 公開承認",
            join_mode=OrganizationRecruitingChat.JoinMode.APPROVAL,
        )
        private = self._create_chat(
            name="C 非公開",
            visibility=OrganizationRecruitingChat.Visibility.PRIVATE,
        )
        self.assertEqual(private.join_mode, OrganizationRecruitingChat.JoinMode.INVITE)
        self.assertEqual(
            private.listing_status, OrganizationRecruitingChat.ListingStatus.CLOSED
        )
        with self.assertRaises(OrganizationRecruitingChatError) as ctx:
            self._create_chat(name="上限超え")
        self.assertEqual(ctx.exception.code, "chat_limit_reached")
        self.assertTrue(
            ChatRoomMembership.objects.filter(
                room=open_chat.room, user=self.owner
            ).exists()
        )
        self.assertTrue(can_access_recruiting_room(open_chat.room, self.owner))
        self.assertFalse(can_access_recruiting_room(approval.room, self.admin))
        join_or_apply_recruiting_chat(chat=approval, user=self.admin)
        self.assertTrue(can_access_recruiting_room(approval.room, self.admin))

    def test_private_chat_is_not_discoverable_and_invite_only(self):
        private = self._create_chat(
            name="幹部",
            visibility=OrganizationRecruitingChat.Visibility.PRIVATE,
        )
        visible = list_visible_organization_chats(self.org, self.student)
        self.assertEqual(visible, [])
        with self.assertRaises(OrganizationRecruitingChatError) as ctx:
            join_or_apply_recruiting_chat(chat=private, user=self.student)
        self.assertEqual(ctx.exception.code, "not_found")
        self.client.force_login(self.student)
        listed = self.client.get(self._url())
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(listed.json()["recruiting_chats"], [])
        hidden = self.client.get(self._url(chat_id=private.pk))
        self.assertEqual(hidden.status_code, 404)

        self.client.force_login(self.owner)
        invited = self._json(
            "post",
            self._url("invites/", chat_id=private.pk),
            invitee_ids=[self.student.pk],
        )
        self.assertEqual(invited.status_code, 201, invited.content)
        invitation_id = invited.json()["invited"][0]["id"]
        self.client.force_login(self.student)
        accepted = self._json(
            "post", f"/api/v1/recruiting-invitations/{invitation_id}/accept/"
        )
        self.assertEqual(accepted.status_code, 200, accepted.content)
        self.assertTrue(can_access_recruiting_room(private.room, self.student))

    def test_public_open_and_approval_and_org_member_is_not_chat_member(self):
        open_chat = self._create_chat(name="自由参加")
        approval = self._create_chat(
            name="承認制",
            join_mode=OrganizationRecruitingChat.JoinMode.APPROVAL,
        )
        self.assertFalse(can_access_recruiting_room(open_chat.room, self.member))
        join_or_apply_recruiting_chat(chat=open_chat, user=self.student)
        self.assertTrue(can_access_recruiting_room(open_chat.room, self.student))
        application = join_or_apply_recruiting_chat(
            chat=approval, user=self.student
        )
        self.assertEqual(application.status, "pending")
        self.assertFalse(can_access_recruiting_room(approval.room, self.student))
        self.client.force_login(self.stranger)
        payload = self.client.get(self._url())
        names = {row["name"] for row in payload.json()["recruiting_chats"]}
        self.assertIn("自由参加", names)
        self.assertIn("承認制", names)

    def test_non_admin_cannot_manage_and_member_cannot_create(self):
        chat = self._create_chat()
        self.client.force_login(self.member)
        created = self._json("post", self._url(), name="メンバー作成")
        self.assertEqual(created.status_code, 403)
        patched = self._json(
            "patch", self._url(chat_id=chat.pk), name="改ざん"
        )
        self.assertEqual(patched.status_code, 403)
        self.client.force_login(self.student)
        patched_student = self._json(
            "patch", self._url(chat_id=chat.pk), name="改ざん2"
        )
        self.assertEqual(patched_student.status_code, 403)

    def test_archive_keeps_messages_and_list_requires_chat_id(self):
        first = self._create_chat(name="残す")
        second = self._create_chat(name="残す2")
        join_or_apply_recruiting_chat(chat=first, user=self.student)
        send_recruiting_chat_message(first.room, self.student, "アーカイブ後も残る")
        self.client.force_login(self.student)
        missing = self._json("post", self._url("join/"))
        self.assertEqual(missing.status_code, 409)
        self.assertEqual(missing.json()["error"], "chat_id_required")
        self.client.force_login(self.owner)
        archived = self._json(
            "patch", self._url(chat_id=first.pk), is_active=False
        )
        self.assertEqual(archived.status_code, 200, archived.content)
        self.assertFalse(archived.json()["recruiting_chat"]["is_active"])
        self.assertTrue(
            ChatMessage.objects.filter(room=first.room, body="アーカイブ後も残る").exists()
        )
        listed = self.client.get(self._url())
        ids = {row["id"] for row in listed.json()["recruiting_chats"]}
        self.assertIn(second.pk, ids)

    def test_admins_only_posting_blocks_regular_member(self):
        chat = self._create_chat(
            name="告知のみ",
            posting_mode=OrganizationRecruitingChat.PostingMode.ADMINS,
        )
        join_or_apply_recruiting_chat(chat=chat, user=self.student)
        send_recruiting_chat_message(chat.room, self.owner, "運営から")
        with self.assertRaises(OrganizationRecruitingChatError) as ctx:
            send_recruiting_chat_message(chat.room, self.student, "一般投稿")
        self.assertEqual(ctx.exception.code, "admins_only")

    def test_event_and_lottery_share_to_chosen_chats_without_private_leak(self):
        public = self._create_chat(name="公開")
        private = self._create_chat(
            name="非公開",
            visibility=OrganizationRecruitingChat.Visibility.PRIVATE,
        )
        now = timezone.now()
        event = create_organization_event(
            organization=self.org,
            actor=self.owner,
            payload={
                "title": "説明会",
                "description": "紹介",
                "starts_at": (now + timedelta(days=3)).isoformat(),
                "ends_at": (now + timedelta(days=3, hours=2)).isoformat(),
                "venue_name": "大隈",
            },
        )
        event = publish_organization_event(event=event, actor=self.owner)
        share = share_organization_event_to_chat(
            event=event, actor=self.owner, chat_id=public.pk
        )
        self.assertEqual(share.recruiting_chat_id, public.pk)
        with self.assertRaises(OrganizationEventError) as ctx:
            share_organization_event_to_chat(
                event=event, actor=self.owner, chat_id=public.pk
            )
        self.assertEqual(ctx.exception.code, "already_shared")
        other = share_organization_event_to_chat(
            event=event, actor=self.owner, chat_id=private.pk
        )
        self.assertEqual(other.recruiting_chat_id, private.pk)
        self.assertEqual(
            OrganizationChatShare.objects.filter(event=event).count(), 2
        )

        register_organization_event(event=event, user=self.student)
        lottery = run_organization_event_lottery(
            event=event,
            actor=self.owner,
            payload={
                "winner_count": 1,
                "excluded": [],
                "applicant_ids": [self.student.pk],
            },
        )
        share_organization_event_lottery(
            event=event, actor=self.owner, chat_id=public.pk
        )
        share_organization_event_lottery(
            event=event, actor=self.owner, chat_id=private.pk
        )
        self.assertTrue(
            OrganizationChatShare.objects.filter(
                event=event,
                recruiting_chat=public,
                share_type=OrganizationChatShare.ShareType.LOTTERY,
            ).exists()
        )
        join_or_apply_recruiting_chat(chat=public, user=self.student)
        self.client.force_login(self.student)
        public_messages = self.client.get(
            f"/api/v1/recruiting-chats/{public.room_id}/messages/"
        )
        self.assertEqual(public_messages.status_code, 200)
        kinds = {
            row.get("share", {}).get("type")
            for row in public_messages.json()["messages"]
            if row.get("message_kind") == "share"
        }
        self.assertIn("org_event", kinds)
        self.assertIn("org_event_lottery", kinds)
        private_messages = self.client.get(
            f"/api/v1/recruiting-chats/{private.room_id}/messages/"
        )
        self.assertIn(private_messages.status_code, {403, 404})
        self.assertFalse(can_access_recruiting_room(private.room, self.student))
        self.assertIsNotNone(lottery.pk)

    def test_identity_switch_does_not_reuse_other_profile_org_admin(self):
        from .account_identity_services import same_person

        chat = self._create_chat()
        self.client.force_login(self.owner)
        created = self._json(
            "post",
            "/api/v1/me/linked-profiles/create/",
            username="mcalt",
            display_name="Alt",
        )
        self.assertEqual(created.status_code, 200, created.content)
        alt_id = created.json()["me"]["user"]["id"]
        alt = User.objects.get(pk=alt_id)
        self.owner.refresh_from_db()
        self.assertTrue(same_person(self.owner, alt))
        self.assertFalse(can_manage_organization(alt, self.org))
        switched = self._json(
            "post",
            "/api/v1/me/linked-profiles/switch/",
            user_id=alt.pk,
        )
        self.assertEqual(switched.status_code, 200, switched.content)
        forbidden = self._json(
            "patch", self._url(chat_id=chat.pk), name="別プロフィール"
        )
        self.assertEqual(forbidden.status_code, 403)
        chat.refresh_from_db()
        self.assertEqual(chat.name, "公開チャット")
        messages = self.client.get(f"/api/v1/recruiting-chats/{chat.room_id}/")
        self.assertIn(messages.status_code, {403, 404})
        self.assertFalse(can_access_recruiting_room(chat.room, alt))

    def test_profile_payload_lists_visible_chats_only(self):
        public = self._create_chat(name="公開一覧")
        self._create_chat(
            name="非公開一覧",
            visibility=OrganizationRecruitingChat.Visibility.PRIVATE,
        )
        join_or_apply_recruiting_chat(chat=public, user=self.student)
        self.client.force_login(self.student)
        profile = self.client.get(f"/api/v1/organizations/{self.org.slug}/")
        self.assertEqual(profile.status_code, 200)
        names = {row["name"] for row in profile.json().get("recruiting_chats") or []}
        self.assertEqual(names, {"公開一覧"})
        owner_view = serialize_recruiting_chat_for_viewer(public, self.owner)
        self.assertEqual(owner_view["visibility"], "public")
