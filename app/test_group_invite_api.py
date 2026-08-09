"""Group chat invitation (approve-to-join) API tests."""

from __future__ import annotations

from django.test import Client, TestCase, override_settings

from .models import (
    ChatRoom,
    ChatRoomInvitation,
    ChatRoomMembership,
    Notification,
    User,
)


@override_settings(BROWSE_MODE_GATE_ENABLED=False)
class GroupInviteApiTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            email="invite-owner@waseda.jp",
            password="test-pass-12345",
            username="inviteowner",
        )
        self.invitee = User.objects.create_user(
            email="invite-member@waseda.jp",
            password="test-pass-12345",
            username="invitemember",
        )
        self.stranger = User.objects.create_user(
            email="invite-stranger@waseda.jp",
            password="test-pass-12345",
            username="invitestranger",
        )
        self.client = Client()

    def test_create_sends_pending_invite_and_notification(self):
        self.client.force_login(self.owner)
        response = self.client.post(
            "/api/v1/dm/groups/",
            data={"name": "ゼミの会", "member_ids": [self.invitee.pk]},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        room = ChatRoom.objects.get(pk=response.json()["room_id"])
        self.assertEqual(ChatRoomMembership.objects.filter(room=room).count(), 1)
        invite = ChatRoomInvitation.objects.get(room=room, invitee=self.invitee)
        self.assertEqual(invite.status, ChatRoomInvitation.Status.PENDING)
        note = Notification.objects.filter(recipient=self.invitee).latest("pk")
        self.assertIn("招待", note.message)
        self.assertIn("ゼミの会", note.message)

        inbox = self.client.get("/api/v1/dm/inbox/")
        self.client.force_login(self.invitee)
        inbox = self.client.get("/api/v1/dm/inbox/")
        kinds = {c["kind"] for c in inbox.json()["conversations"]}
        self.assertIn("group_invite", kinds)

    def test_accept_joins_and_decline_hides_invite(self):
        self.client.force_login(self.owner)
        created = self.client.post(
            "/api/v1/dm/groups/",
            data={"name": "参加テスト", "member_ids": [self.invitee.pk]},
            content_type="application/json",
        )
        room_id = created.json()["room_id"]

        self.client.force_login(self.invitee)
        room = self.client.get(f"/api/v1/dm/groups/{room_id}/")
        self.assertEqual(room.status_code, 200)
        payload = room.json()["room"]
        self.assertEqual(payload["membership_status"], "pending_invite")
        self.assertFalse(payload["can_send"])
        self.assertEqual(payload["member_count"], 1)

        denied = self.client.post(
            f"/api/v1/dm/groups/{room_id}/messages/send/",
            data={"body": "まだ参加前"},
            content_type="application/json",
        )
        self.assertEqual(denied.status_code, 403)

        accepted = self.client.post(
            f"/api/v1/dm/groups/{room_id}/invitations/accept/",
            data={},
            content_type="application/json",
        )
        self.assertEqual(accepted.status_code, 200)
        self.assertEqual(accepted.json()["room"]["membership_status"], "member")
        self.assertTrue(
            ChatRoomMembership.objects.filter(
                room_id=room_id, user=self.invitee
            ).exists()
        )
        invite = ChatRoomInvitation.objects.get(room_id=room_id, invitee=self.invitee)
        self.assertEqual(invite.status, ChatRoomInvitation.Status.ACCEPTED)

        note = Notification.objects.filter(recipient=self.invitee).latest("pk")
        self.assertIn("参加", note.message)

        # Second invite flow for stranger: decline
        self.client.force_login(self.owner)
        created2 = self.client.post(
            "/api/v1/dm/groups/",
            data={"name": "辞退テスト", "member_ids": [self.stranger.pk]},
            content_type="application/json",
        )
        room2 = created2.json()["room_id"]
        self.client.force_login(self.stranger)
        declined = self.client.post(
            f"/api/v1/dm/groups/{room2}/invitations/decline/",
            data={},
            content_type="application/json",
        )
        self.assertEqual(declined.status_code, 200)
        self.assertFalse(
            ChatRoomMembership.objects.filter(
                room_id=room2, user=self.stranger
            ).exists()
        )
        inbox = self.client.get("/api/v1/dm/inbox/")
        invite_rows = [
            c
            for c in inbox.json()["conversations"]
            if c["kind"] == "group_invite" and c["room_id"] == room2
        ]
        self.assertEqual(invite_rows, [])

    def test_member_can_invite_anyone(self):
        self.client.force_login(self.owner)
        created = self.client.post(
            "/api/v1/dm/groups/",
            data={"name": "追加招待", "member_ids": [self.invitee.pk]},
            content_type="application/json",
        )
        room_id = created.json()["room_id"]
        self.client.force_login(self.invitee)
        self.client.post(
            f"/api/v1/dm/groups/{room_id}/invitations/accept/",
            content_type="application/json",
        )
        invited = self.client.post(
            f"/api/v1/dm/groups/{room_id}/invite/",
            data={"member_ids": [self.stranger.pk]},
            content_type="application/json",
        )
        self.assertEqual(invited.status_code, 201)
        self.assertTrue(
            ChatRoomInvitation.objects.filter(
                room_id=room_id,
                invitee=self.stranger,
                status=ChatRoomInvitation.Status.PENDING,
            ).exists()
        )
