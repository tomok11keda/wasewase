"""Release B: recruiting-chat operator invites."""

from __future__ import annotations

import json
from datetime import timedelta
from unittest.mock import patch

from django.core.cache import cache
from django.db import IntegrityError, OperationalError, transaction
from django.test import Client, TestCase, override_settings
from django.utils import timezone

from .models import (
    ChatMessage,
    ChatRoom,
    ChatRoomInvitation,
    ChatRoomMembership,
    Notification,
    Organization,
    OrganizationMember,
    OrganizationRecruitingChatApplication,
    User,
    UserBlock,
    UserProfile,
)
from .organization_recruiting_chat_services import get_active_recruiting_chat
from .organization_recruiting_invite_services import create_recruiting_invitations
from .organization_services import add_organization_member


def _make_user(email: str, **kwargs) -> User:
    kwargs.setdefault("password", "test-pass-12345")
    user = User.objects.create_user(email=email, **kwargs)
    UserProfile.objects.get_or_create(
        user=user,
        defaults={"name": kwargs.get("username") or email.split("@")[0]},
    )
    return user


def _make_org(**kwargs) -> Organization:
    kwargs.setdefault("name", "招待サークル")
    kwargs.setdefault("slug", "invite-circle")
    kwargs.setdefault("status", Organization.Status.ACTIVE)
    kwargs.setdefault("is_listed", True)
    return Organization.objects.create(**kwargs)


@override_settings(BROWSE_MODE_GATE_ENABLED=False)
class OrganizationRecruitingInviteApiTests(TestCase):
    def setUp(self):
        cache.clear()
        self.owner = _make_user("inv-owner@waseda.jp", username="invowner")
        self.admin = _make_user("inv-admin@waseda.jp", username="invadmin")
        self.member = _make_user("inv-member@waseda.jp", username="invmember")
        self.student = _make_user("inv-student@waseda.jp", username="invstudent")
        self.other = _make_user("inv-other@waseda.jp", username="invother")
        self.stranger = _make_user("inv-stranger@waseda.jp", username="invstranger")
        self.other_owner = _make_user("inv-otherowner@waseda.jp", username="invotherown")
        self.org = _make_org()
        self.other_org = _make_org(name="別招待団体", slug="invite-other-org")
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

    def tearDown(self):
        cache.clear()

    def _url(self, suffix: str = "", slug: str | None = None) -> str:
        return f"/api/v1/organizations/{slug or self.org.slug}/recruiting-chat/{suffix}"

    def _json(self, method: str, url: str, **payload):
        handler = getattr(self.client, method.lower())

        def _request():
            if payload:
                return handler(
                    url,
                    data=json.dumps(payload),
                    content_type="application/json",
                )
            return handler(url)

        if method.lower() in {"post", "patch", "put", "delete"}:
            with self.captureOnCommitCallbacks(execute=True):
                return _request()
        return _request()

    def _create_chat(self, actor=None, **payload):
        self.client.force_login(actor or self.owner)
        payload.setdefault("name", "2026新歓チャット")
        payload.setdefault("description", "新入生向け")
        return self._json("post", self._url(), **payload)

    def _invite(self, *users, actor=None):
        self.client.force_login(actor or self.owner)
        return self._json(
            "post",
            self._url("invites/"),
            invitee_ids=[user.pk for user in users],
        )

    def test_owner_and_admin_can_invite_others_cannot(self):
        created = self._create_chat()
        self.assertEqual(created.status_code, 201, created.content)
        room_id = created.json()["recruiting_chat"]["room_id"]
        ChatMessage.objects.create(
            room_id=room_id, sender=self.owner, body="秘密の本文"
        )

        invited = self._invite(self.student)
        self.assertEqual(invited.status_code, 201, invited.content)
        body = invited.json()
        self.assertEqual(body["invited_count"], 1)
        self.assertEqual(len(body["skipped"]), 0)
        self.assertNotIn("秘密の本文", json.dumps(body))
        self.assertNotIn("@waseda.jp", json.dumps(body))
        invite = ChatRoomInvitation.objects.get(
            room_id=room_id, invitee=self.student
        )
        self.assertEqual(invite.status, ChatRoomInvitation.Status.PENDING)
        self.assertFalse(
            ChatRoomMembership.objects.filter(
                room_id=room_id, user=self.student
            ).exists()
        )

        self.client.force_login(self.admin)
        second = self._invite(self.other, actor=self.admin)
        self.assertEqual(second.status_code, 201)

        self.client.force_login(self.member)
        denied_member = self._invite(self.stranger, actor=self.member)
        self.assertEqual(denied_member.status_code, 403)

        self.client.force_login(self.other_owner)
        denied_other = self._invite(self.stranger, actor=self.other_owner)
        self.assertEqual(denied_other.status_code, 403)

        anon = Client()
        anon_res = anon.post(
            self._url("invites/"),
            data=json.dumps({"invitee_ids": [self.stranger.pk]}),
            content_type="application/json",
        )
        self.assertEqual(anon_res.status_code, 401)

    def test_candidate_search_is_manager_only_and_excludes_blocked_members(self):
        created = self._create_chat()
        room_id = created.json()["recruiting_chat"]["room_id"]
        ChatRoomMembership.objects.create(
            room_id=room_id, user=self.other, role="member"
        )
        UserBlock.objects.create(blocker=self.owner, blocked=self.stranger)
        self.client.force_login(self.owner)
        found = self.client.get(self._url("invite-candidates/?q=invstudent"))
        self.assertEqual(found.status_code, 200)
        usernames = {row["username"] for row in found.json()["users"]}
        self.assertIn("invstudent", usernames)
        self.assertLessEqual(len(found.json()["users"]), 20)

        member_hit = self.client.get(self._url("invite-candidates/?q=invother"))
        member_names = {row["username"] for row in member_hit.json()["users"]}
        self.assertNotIn("invother", member_names)

        blocked_hit = self.client.get(self._url("invite-candidates/?q=invstranger"))
        blocked_names = {row["username"] for row in blocked_hit.json()["users"]}
        self.assertNotIn("invstranger", blocked_names)

        empty = self.client.get(self._url("invite-candidates/?q=a"))
        self.assertEqual(empty.json()["users"], [])

        self.client.force_login(self.member)
        forbidden = self.client.get(self._url("invite-candidates/?q=invstudent"))
        self.assertEqual(forbidden.status_code, 403)

        self.client.force_login(self.other_owner)
        other_org = self.client.get(self._url("invite-candidates/?q=invstudent"))
        self.assertEqual(other_org.status_code, 403)

    def test_private_user_is_skipped_and_duplicate_pending_is_skipped(self):
        self._create_chat()
        profile = self.student.profile
        profile.is_private = True
        profile.save(update_fields=["is_private"])
        private = self._invite(self.student)
        self.assertEqual(private.status_code, 201)
        self.assertEqual(private.json()["invited_count"], 0)
        self.assertEqual(private.json()["skipped"][0]["reason"], "private")

        profile.is_private = False
        profile.save(update_fields=["is_private"])
        first = self._invite(self.student)
        self.assertEqual(first.json()["invited_count"], 1)
        dup = self._invite(self.student)
        self.assertEqual(dup.json()["invited_count"], 0)
        self.assertEqual(dup.json()["skipped"][0]["reason"], "already_pending")

        self_invite = self._invite(self.owner)
        self.assertEqual(self_invite.json()["skipped"][0]["reason"], "self")

    def test_block_and_existing_member_and_batch_limit(self):
        created = self._create_chat()
        room_id = created.json()["recruiting_chat"]["room_id"]
        ChatRoomMembership.objects.create(
            room_id=room_id, user=self.other, role="member"
        )
        UserBlock.objects.create(blocker=self.student, blocked=self.owner)
        blocked = self._invite(self.student, self.other)
        reasons = {row["reason"] for row in blocked.json()["skipped"]}
        self.assertIn("blocked", reasons)
        self.assertIn("already_member", reasons)

        too_many = self._json(
            "post",
            self._url("invites/"),
            invitee_ids=list(range(1, 22)),
        )
        self.assertEqual(too_many.status_code, 400)
        self.assertEqual(too_many.json()["error"], "too_many_invites")

    def test_suspended_closed_inactive_and_approval_invite(self):
        created = self._create_chat(join_mode="approval")
        room_id = created.json()["recruiting_chat"]["room_id"]
        self.org.status = Organization.Status.SUSPENDED
        self.org.save(update_fields=["status"])
        suspended = self._invite(self.student)
        self.assertEqual(suspended.status_code, 403)
        self.org.status = Organization.Status.ACTIVE
        self.org.save(update_fields=["status"])

        self._json("patch", self._url(), listing_status="closed")
        closed = self._invite(self.student)
        self.assertEqual(closed.status_code, 403)
        self.assertEqual(closed.json()["error"], "listing_closed")
        self._json("patch", self._url(), listing_status="open")

        invited = self._invite(self.student)
        self.assertEqual(invited.status_code, 201)
        invitation_id = invited.json()["invited"][0]["id"]
        self.client.force_login(self.student)
        accepted = self._json(
            "post", f"/api/v1/recruiting-invitations/{invitation_id}/accept/"
        )
        self.assertEqual(accepted.status_code, 200, accepted.content)
        self.assertTrue(
            ChatRoomMembership.objects.filter(
                room_id=room_id, user=self.student
            ).exists()
        )
        application = OrganizationRecruitingChatApplication.objects.get(
            recruiting_chat__room_id=room_id, user=self.student
        )
        self.assertEqual(
            application.status,
            OrganizationRecruitingChatApplication.Status.APPROVED,
        )
        self.assertTrue(accepted.json()["recruiting_chat"]["can_send"])
        self.assertIsNotNone(accepted.json()["recruiting_chat"]["room_id"])

    def test_accept_decline_permissions_and_cooldown(self):
        created = self._create_chat()
        room_id = created.json()["recruiting_chat"]["room_id"]
        invited = self._invite(self.student)
        invitation_id = invited.json()["invited"][0]["id"]

        self.client.force_login(self.stranger)
        stolen = self._json(
            "post", f"/api/v1/recruiting-invitations/{invitation_id}/accept/"
        )
        self.assertEqual(stolen.status_code, 404)
        stolen_decline = self._json(
            "post", f"/api/v1/recruiting-invitations/{invitation_id}/decline/"
        )
        self.assertEqual(stolen_decline.status_code, 404)

        self.client.force_login(self.student)
        declined = self._json(
            "post", f"/api/v1/recruiting-invitations/{invitation_id}/decline/"
        )
        self.assertEqual(declined.status_code, 200)
        self.assertFalse(
            ChatRoomMembership.objects.filter(
                room_id=room_id, user=self.student
            ).exists()
        )
        again = self._invite(self.student)
        self.assertEqual(again.json()["invited_count"], 0)
        self.assertEqual(again.json()["skipped"][0]["reason"], "cooldown")

        row = ChatRoomInvitation.objects.get(pk=invitation_id)
        row.responded_at = timezone.now() - timedelta(days=31)
        row.save(update_fields=["responded_at"])
        refreshed = self._invite(self.student)
        self.assertEqual(refreshed.json()["invited_count"], 1)

    def test_cancel_blocks_accept_and_group_api_cannot_operate_recruiting(self):
        created = self._create_chat()
        room_id = created.json()["recruiting_chat"]["room_id"]
        ChatMessage.objects.create(
            room_id=room_id, sender=self.owner, body="本文は見せない"
        )
        invited = self._invite(self.student)
        invitation_id = invited.json()["invited"][0]["id"]

        self.client.force_login(self.student)
        hidden = self.client.get(f"/api/v1/recruiting-chats/{room_id}/messages/")
        self.assertIn(hidden.status_code, {403, 404})
        dumped = hidden.content.decode("utf-8")
        self.assertNotIn("本文は見せない", dumped)
        send = self._json(
            "post",
            f"/api/v1/recruiting-chats/{room_id}/messages/send/",
            body="招待中",
        )
        self.assertEqual(send.status_code, 403)

        group_accept = self._json(
            "post", f"/api/v1/dm/groups/{room_id}/invitations/accept/"
        )
        self.assertEqual(group_accept.status_code, 404)
        group_invite = self._json(
            "post",
            f"/api/v1/dm/groups/{room_id}/invite/",
            invitee_ids=[self.other.pk],
        )
        self.assertEqual(group_invite.status_code, 404)

        self.client.force_login(self.owner)
        cancelled = self._json(
            "post", self._url(f"invites/{invitation_id}/cancel/")
        )
        self.assertEqual(cancelled.status_code, 200)
        self.assertEqual(
            ChatRoomInvitation.objects.get(pk=invitation_id).status,
            ChatRoomInvitation.Status.CANCELLED,
        )
        self.client.force_login(self.student)
        late_accept = self._json(
            "post", f"/api/v1/recruiting-invitations/{invitation_id}/accept/"
        )
        self.assertEqual(late_accept.status_code, 409)
        reinvite = self._invite(self.student)
        self.assertEqual(reinvite.json()["invited_count"], 1)

    def test_pending_application_is_approved_on_invite_accept(self):
        created = self._create_chat(join_mode="approval")
        room_id = created.json()["recruiting_chat"]["room_id"]
        self.client.force_login(self.student)
        applied = self._json("post", self._url("join/"))
        self.assertEqual(applied.status_code, 201)
        invited = self._invite(self.student)
        invitation_id = invited.json()["invited"][0]["id"]
        self.client.force_login(self.student)
        accepted = self._json(
            "post", f"/api/v1/recruiting-invitations/{invitation_id}/accept/"
        )
        self.assertEqual(accepted.status_code, 200)
        application = OrganizationRecruitingChatApplication.objects.get(
            recruiting_chat__room_id=room_id, user=self.student
        )
        self.assertEqual(
            application.status,
            OrganizationRecruitingChatApplication.Status.APPROVED,
        )

    def test_open_join_while_invited_accepts_invite(self):
        created = self._create_chat()
        room_id = created.json()["recruiting_chat"]["room_id"]
        invited = self._invite(self.student)
        self.assertEqual(invited.status_code, 201)
        self.client.force_login(self.student)
        joined = self._json("post", self._url("join/"))
        self.assertEqual(joined.status_code, 201)
        invite = ChatRoomInvitation.objects.get(
            room_id=room_id, invitee=self.student
        )
        self.assertEqual(invite.status, ChatRoomInvitation.Status.ACCEPTED)
        self.assertTrue(
            ChatRoomMembership.objects.filter(
                room_id=room_id, user=self.student
            ).exists()
        )

    def test_listing_closed_still_allows_accepting_existing_invite(self):
        self._create_chat()
        invited = self._invite(self.student)
        invitation_id = invited.json()["invited"][0]["id"]
        self.client.force_login(self.owner)
        self._json("patch", self._url(), listing_status="closed")
        self.client.force_login(self.student)
        accepted = self._json(
            "post", f"/api/v1/recruiting-invitations/{invitation_id}/accept/"
        )
        self.assertEqual(accepted.status_code, 200, accepted.content)

    def test_notifications_are_not_duplicated_and_inbox_hides_body(self):
        created = self._create_chat()
        room_id = created.json()["recruiting_chat"]["room_id"]
        ChatMessage.objects.create(
            room_id=room_id, sender=self.owner, body="秘密の本文"
        )
        first = self._invite(self.student)
        self.assertEqual(first.status_code, 201)
        notes = Notification.objects.filter(recipient=self.student)
        self.assertEqual(notes.count(), 1)
        note = notes.get()
        self.assertIn("招待サークルから団体チャットに招待されました", note.message)
        self.assertIn("/recruiting-chat/invite", note.link)
        self._invite(self.student)
        self.assertEqual(Notification.objects.filter(recipient=self.student).count(), 1)

        self.client.force_login(self.student)
        chat = self.client.get(self._url())
        payload = chat.json()["recruiting_chat"]
        self.assertEqual(payload["membership_status"], "invited")
        self.assertIsNone(payload["room_id"])
        self.assertFalse(payload["can_send"])
        self.assertNotIn("秘密の本文", json.dumps(payload))

        inbox = self.client.get("/api/v1/dm/inbox/")
        kinds = {row["kind"] for row in inbox.json()["conversations"]}
        self.assertIn("recruiting_invite", kinds)
        invite_row = next(
            row
            for row in inbox.json()["conversations"]
            if row["kind"] == "recruiting_invite"
        )
        self.assertEqual(invite_row["latest_body"], "")
        self.assertIn("/recruiting-chat/invite", invite_row["spa_path"])

    def test_invitee_can_open_pending_invite_when_org_profile_is_not_public(self):
        """Inbox/notification show the invite, so the detail API must too.

        Draft/unlisted orgs are the default. Managers can still invite.
        Students must open/accept without org profile visibility.
        """
        from .notification_api_services import notification_spa_path
        from .spa_canonical import recruiting_invite_spa_path

        self.org.status = Organization.Status.DRAFT
        self.org.is_listed = False
        self.org.save(update_fields=["status", "is_listed", "updated_at"])
        created = self._create_chat()
        self.assertEqual(created.status_code, 201, created.content)
        room_id = created.json()["recruiting_chat"]["room_id"]
        ChatMessage.objects.create(
            room_id=room_id, sender=self.owner, body="下書き団体の本文"
        )
        invited = self._invite(self.student)
        self.assertEqual(invited.status_code, 201, invited.content)
        invitation_id = invited.json()["invited"][0]["id"]

        self.client.force_login(self.student)
        inbox = self.client.get("/api/v1/dm/inbox/")
        invite_row = next(
            row
            for row in inbox.json()["conversations"]
            if row["kind"] == "recruiting_invite"
        )
        self.assertEqual(invite_row["latest_body"], "")
        spa_path = invite_row["spa_path"]
        self.assertEqual(spa_path.split("?")[0], recruiting_invite_spa_path(self.org.slug))

        notes = self.client.get("/api/v1/notifications/?mark_read=0")
        note = next(
            row
            for row in notes.json()["notifications"]
            if "団体チャットに招待" in row["message"]
        )
        self.assertEqual(
            notification_spa_path(note["link"]).split("?")[0],
            recruiting_invite_spa_path(self.org.slug),
        )

        by_slug = self.client.get(self._url("invitation/"))
        self.assertEqual(by_slug.status_code, 200, by_slug.content)
        body = by_slug.json()
        self.assertEqual(body["invitation"]["id"], invitation_id)
        self.assertEqual(body["invitation"]["status"], "pending")
        self.assertIsNone(body["recruiting_chat"]["room_id"])
        self.assertFalse(body["recruiting_chat"]["can_send"])
        self.assertNotIn("下書き団体の本文", json.dumps(body))

        pending_chat = self.client.get(self._url())
        self.assertEqual(pending_chat.status_code, 200, pending_chat.content)
        pending_payload = pending_chat.json()["recruiting_chat"]
        self.assertEqual(pending_payload["membership_status"], "invited")
        self.assertIsNone(pending_payload["room_id"])
        hidden = self.client.get(f"/api/v1/recruiting-chats/{room_id}/messages/")
        self.assertEqual(hidden.status_code, 403)

        by_id = self.client.get(f"/api/v1/recruiting-invitations/{invitation_id}/")
        self.assertEqual(by_id.status_code, 200, by_id.content)
        self.assertEqual(by_id.json()["invitation"]["status"], "pending")

        self.client.force_login(self.stranger)
        self.assertEqual(self.client.get(self._url("invitation/")).status_code, 404)
        self.assertEqual(self.client.get(self._url()).status_code, 404)
        self.assertEqual(
            self.client.get("/api/v1/organizations/%s/" % self.org.slug).status_code,
            404,
        )
        self.assertEqual(
            self.client.get(f"/api/v1/recruiting-invitations/{invitation_id}/").status_code,
            404,
        )

        self.client.force_login(self.student)
        accepted = self._json(
            "post", f"/api/v1/recruiting-invitations/{invitation_id}/accept/"
        )
        self.assertEqual(accepted.status_code, 200, accepted.content)
        accepted_chat = accepted.json()["recruiting_chat"]
        self.assertEqual(accepted_chat["room_id"], room_id)
        self.assertTrue(accepted_chat["can_send"])
        self.assertTrue(
            ChatRoomMembership.objects.filter(
                room_id=room_id, user=self.student
            ).exists()
        )

        opened = self.client.get(self._url())
        self.assertEqual(opened.status_code, 200, opened.content)
        opened_chat = opened.json()["recruiting_chat"]
        self.assertEqual(opened_chat["room_id"], room_id)
        self.assertTrue(opened_chat["can_send"])
        history = self.client.get(f"/api/v1/recruiting-chats/{room_id}/messages/")
        self.assertEqual(history.status_code, 200, history.content)
        bodies = [row["body"] for row in history.json()["messages"]]
        self.assertIn("下書き団体の本文", bodies)
        sent = self._json(
            "post",
            f"/api/v1/recruiting-chats/{room_id}/messages/send/",
            body="招待承諾後の返信",
        )
        self.assertEqual(sent.status_code, 201, sent.content)

        self.client.force_login(self.stranger)
        self.assertEqual(self.client.get(self._url()).status_code, 404)
        self.assertIn(
            self.client.get(f"/api/v1/recruiting-chats/{room_id}/messages/").status_code,
            (403, 404),
        )

    def test_group_dm_invite_still_works(self):
        self.client.force_login(self.owner)
        created = self._json(
            "post",
            "/api/v1/dm/groups/",
            name="互換グループ",
            member_ids=[self.student.pk],
        )
        self.assertEqual(created.status_code, 201)
        room_id = created.json()["room_id"]
        self.assertEqual(
            ChatRoom.objects.get(pk=room_id).kind, ChatRoom.Kind.GROUP
        )
        self.client.force_login(self.student)
        accepted = self._json(
            "post", f"/api/v1/dm/groups/{room_id}/invitations/accept/"
        )
        self.assertEqual(accepted.status_code, 200)
        self.assertTrue(
            ChatRoomMembership.objects.filter(
                room_id=room_id, user=self.student
            ).exists()
        )

    def test_csrf_required_and_hourly_limit(self):
        self._create_chat()
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.owner)
        csrf = csrf_client.post(
            self._url("invites/"),
            data=json.dumps({"invitee_ids": [self.student.pk]}),
            content_type="application/json",
        )
        self.assertEqual(csrf.status_code, 403)
        self.assertEqual(csrf.json()["error"], "csrf_failed")

        chat = self.org.recruiting_chats.get(is_active=True)
        extras = [
            User(email=f"rl{i}@waseda.jp", username=f"rluser{i}")
            for i in range(60)
        ]
        User.objects.bulk_create(extras)
        extras = list(User.objects.filter(username__startswith="rluser"))
        now = timezone.now()
        ChatRoomInvitation.objects.bulk_create(
            [
                ChatRoomInvitation(
                    room=chat.room,
                    inviter=self.owner,
                    invitee=user,
                    status=ChatRoomInvitation.Status.PENDING,
                    created_at=now,
                    updated_at=now,
                )
                for user in extras
            ]
        )
        limited = self._invite(self.student)
        self.assertEqual(limited.status_code, 429)
        self.assertEqual(limited.json()["error"], "rate_limited")

    def test_viewer_invitation_endpoint_is_invitee_only(self):
        self._create_chat()
        invited = self._invite(self.student)
        invitation_id = invited.json()["invited"][0]["id"]
        self.client.force_login(self.student)
        mine = self.client.get(self._url("invitation/"))
        self.assertEqual(mine.status_code, 200)
        self.assertEqual(mine.json()["invitation"]["id"], invitation_id)
        self.assertIsNone(mine.json()["recruiting_chat"]["room_id"])
        detail = self.client.get(
            f"/api/v1/recruiting-invitations/{invitation_id}/"
        )
        self.assertEqual(detail.status_code, 200)
        self.client.force_login(self.stranger)
        other = self.client.get(
            f"/api/v1/recruiting-invitations/{invitation_id}/"
        )
        self.assertEqual(other.status_code, 404)
        other_org = self.client.get(self._url("invitation/"))
        self.assertEqual(other_org.status_code, 404)

    def test_demoted_admin_cannot_invite(self):
        self._create_chat()
        OrganizationMember.objects.filter(
            organization=self.org, user=self.admin
        ).update(role=OrganizationMember.Role.MEMBER)
        denied = self._invite(self.student, actor=self.admin)
        self.assertEqual(denied.status_code, 403)

    def test_room_hourly_cap_applies_across_admins(self):
        self._create_chat()
        chat = get_active_recruiting_chat(self.org)
        extras = [
            User(email=f"roomrl{i}@waseda.jp", username=f"roomrl{i}")
            for i in range(60)
        ]
        User.objects.bulk_create(extras)
        extras = list(User.objects.filter(username__startswith="roomrl"))
        now = timezone.now()
        ChatRoomInvitation.objects.bulk_create(
            [
                ChatRoomInvitation(
                    room=chat.room,
                    inviter=self.owner,
                    invitee=user,
                    status=ChatRoomInvitation.Status.PENDING,
                    created_at=now,
                    updated_at=now,
                )
                for user in extras
            ]
        )
        limited = self._invite(self.student, actor=self.admin)
        self.assertEqual(limited.status_code, 429)

    def test_accept_then_cancel_is_conflict(self):
        self._create_chat()
        invited = self._invite(self.student)
        invitation_id = invited.json()["invited"][0]["id"]
        self.client.force_login(self.student)
        accepted = self._json(
            "post", f"/api/v1/recruiting-invitations/{invitation_id}/accept/"
        )
        self.assertEqual(accepted.status_code, 200)
        self.client.force_login(self.owner)
        cancelled = self._json(
            "post", self._url(f"invites/{invitation_id}/cancel/")
        )
        self.assertEqual(cancelled.status_code, 409)

    def test_approving_application_accepts_pending_invite(self):
        self._create_chat(join_mode="approval")
        self.client.force_login(self.student)
        applied = self._json("post", self._url("join/"))
        self.assertEqual(applied.status_code, 201)
        application_id = applied.json()["application_id"]
        invited = self._invite(self.student)
        self.assertEqual(invited.json()["invited_count"], 1)
        self.client.force_login(self.owner)
        approved = self._json(
            "post", self._url(f"applications/{application_id}/approve/")
        )
        self.assertEqual(approved.status_code, 200)
        invite = ChatRoomInvitation.objects.get(
            invitee=self.student, room=get_active_recruiting_chat(self.org).room
        )
        self.assertEqual(invite.status, ChatRoomInvitation.Status.ACCEPTED)
        note = Notification.objects.filter(recipient=self.student).first()
        self.assertIsNotNone(note)
        self.assertTrue(note.is_read)
        self.assertIn("参加しました", note.message)

    def test_skipped_invitees_do_not_consume_hourly_quota(self):
        self._create_chat()
        chat = get_active_recruiting_chat(self.org)
        extras = [
            User(email=f"skiprl{i}@waseda.jp", username=f"skiprl{i}")
            for i in range(59)
        ]
        User.objects.bulk_create(extras)
        extras = list(User.objects.filter(username__startswith="skiprl"))
        ChatRoomMembership.objects.get_or_create(
            room=chat.room, user=self.member
        )
        now = timezone.now()
        ChatRoomInvitation.objects.bulk_create(
            [
                ChatRoomInvitation(
                    room=chat.room,
                    inviter=self.owner,
                    invitee=user,
                    status=ChatRoomInvitation.Status.PENDING,
                    created_at=now,
                    updated_at=now,
                )
                for user in extras
            ]
        )
        mixed = self._invite(self.member, self.student)
        self.assertEqual(mixed.status_code, 201, mixed.content)
        reasons = {row["reason"] for row in mixed.json()["skipped"]}
        self.assertEqual(mixed.json()["invited_count"], 1)
        self.assertIn("already_member", reasons)

    def test_unique_constraint_race_is_skipped(self):
        self._create_chat()
        with patch(
            "app.organization_recruiting_invite_services.ChatRoomInvitation.objects.create",
            side_effect=IntegrityError("duplicate"),
        ):
            raced = self._invite(self.student)
        self.assertEqual(raced.status_code, 201)
        self.assertEqual(raced.json()["invited_count"], 0)
        self.assertEqual(raced.json()["skipped"][0]["reason"], "already_pending")

    def test_unique_constraint_race_does_not_abort_rest_of_batch(self):
        """PostgreSQL needs a savepoint so a duplicate insert can skip one row."""
        self._create_chat()
        real_create = ChatRoomInvitation.objects.create
        calls = {"n": 0}

        def create_with_race(*args, **kwargs):
            calls["n"] += 1
            if calls["n"] == 2:
                raise IntegrityError("duplicate")
            return real_create(*args, **kwargs)

        with patch(
            "app.organization_recruiting_invite_services.ChatRoomInvitation.objects.create",
            side_effect=create_with_race,
        ):
            raced = self._invite(self.student, self.other)
        self.assertEqual(raced.status_code, 201, raced.content)
        body = raced.json()
        self.assertEqual(body["invited_count"], 1)
        self.assertEqual(body["skipped"][0]["id"], self.other.pk)
        self.assertEqual(body["skipped"][0]["reason"], "already_pending")
        self.assertTrue(
            ChatRoomInvitation.objects.filter(
                invitee=self.student, status=ChatRoomInvitation.Status.PENDING
            ).exists()
        )
        self.assertFalse(
            ChatRoomInvitation.objects.filter(invitee=self.other).exists()
        )

    def test_sqlite_lock_is_not_treated_as_duplicate(self):
        self._create_chat()
        with patch(
            "app.organization_recruiting_invite_services.ChatRoomInvitation.objects.create",
            side_effect=OperationalError("database is locked"),
        ):
            locked = self._invite(self.student)
        self.assertEqual(locked.status_code, 503)
        self.assertEqual(locked.json()["error"], "busy")
        self.assertFalse(
            ChatRoomInvitation.objects.filter(invitee=self.student).exists()
        )
        self.assertEqual(
            Notification.objects.filter(recipient=self.student).count(), 0
        )

    def test_postgres_deadlock_is_busy_not_duplicate(self):
        self._create_chat()
        with patch(
            "app.organization_recruiting_invite_services.ChatRoomInvitation.objects.create",
            side_effect=OperationalError("deadlock detected"),
        ):
            deadlocked = self._invite(self.student)
        self.assertEqual(deadlocked.status_code, 503)
        self.assertEqual(deadlocked.json()["error"], "busy")
        self.assertFalse(
            ChatRoomInvitation.objects.filter(invitee=self.student).exists()
        )

    def test_mutating_paths_lock_chat_before_invitation_rows(self):
        from pathlib import Path

        root = Path(__file__).resolve().parent
        invite_src = (root / "organization_recruiting_invite_services.py").read_text()
        chat_src = (root / "organization_recruiting_chat_services.py").read_text()
        cases = [
            (invite_src, "def create_recruiting_invitations"),
            (invite_src, "def cancel_recruiting_invitation"),
            (invite_src, "def accept_recruiting_invitation"),
            (invite_src, "def decline_recruiting_invitation"),
            (chat_src, "def join_or_apply_recruiting_chat"),
            (chat_src, "def approve_recruiting_application"),
        ]
        for src, name in cases:
            start = src.index(name)
            nxt = src.find("\ndef ", start + 4)
            body = src[start:nxt]
            self.assertIn("_lock_chat(", body, msg=name)
            if "ChatRoomInvitation.objects.select_for_update" in body:
                self.assertLess(
                    body.index("_lock_chat("),
                    body.index("ChatRoomInvitation.objects.select_for_update"),
                    msg=name,
                )

    def test_cache_outage_fail_open_still_invites(self):
        self._create_chat()
        with patch(
            "app.course_services.cache.get",
            side_effect=RuntimeError("cache down"),
        ):
            invited = self._invite(self.student)
        self.assertEqual(invited.status_code, 201)
        self.assertEqual(invited.json()["invited_count"], 1)

    def test_rolled_back_transaction_does_not_leave_notification(self):
        self._create_chat()
        chat = get_active_recruiting_chat(self.org)
        with self.assertRaises(RuntimeError):
            with transaction.atomic():
                create_recruiting_invitations(
                    chat=chat,
                    actor=self.owner,
                    invitee_ids=[self.student.pk],
                )
                raise RuntimeError("boom")
        self.assertFalse(
            ChatRoomInvitation.objects.filter(
                invitee=self.student, room=chat.room
            ).exists()
        )
        self.assertEqual(
            Notification.objects.filter(recipient=self.student).count(), 0
        )
