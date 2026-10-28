"""Phase 4: in-chat organization events and RSVP ACL."""

from __future__ import annotations

import json
from datetime import timedelta

from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.utils import timezone

from .models import (
    ChatRoomMembership,
    Organization,
    OrganizationChatEvent,
    OrganizationMember,
    User,
    UserProfile,
)
from .organization_recruiting_chat_services import (
    create_recruiting_chat,
    deactivate_recruiting_chat,
    join_or_apply_recruiting_chat,
)
from .organization_services import add_organization_member


def _make_user(email: str, **kwargs) -> User:
    kwargs.setdefault("password", "test-pass-12345")
    user = User.objects.create_user(email=email, **kwargs)
    UserProfile.objects.get_or_create(
        user=user,
        defaults={"name": kwargs.get("username") or email.split("@")[0]},
    )
    return user


@override_settings(BROWSE_MODE_GATE_ENABLED=False)
class OrganizationChatEventTests(TestCase):
    def setUp(self):
        cache.clear()
        self.owner = _make_user("ce-owner@waseda.jp", username="ceowner")
        self.admin = _make_user("ce-admin@waseda.jp", username="ceadmin")
        self.student = _make_user("ce-student@waseda.jp", username="cestudent")
        self.outsider = _make_user("ce-out@waseda.jp", username="ceout")
        self.org = Organization.objects.create(
            name="チャットイベント団体",
            slug="chat-event-org",
            status=Organization.Status.ACTIVE,
            is_listed=True,
        )
        self.other_org = Organization.objects.create(
            name="別団体",
            slug="chat-event-other",
            status=Organization.Status.ACTIVE,
            is_listed=True,
        )
        add_organization_member(
            self.org, self.owner, role=OrganizationMember.Role.OWNER
        )
        add_organization_member(
            self.org, self.admin, role=OrganizationMember.Role.ADMIN
        )
        add_organization_member(
            self.other_org, self.outsider, role=OrganizationMember.Role.OWNER
        )
        self.chat = create_recruiting_chat(
            organization=self.org, actor=self.owner, name="新歓チャット"
        )
        self.other_chat = create_recruiting_chat(
            organization=self.org, actor=self.owner, name="別チャット"
        )
        join_or_apply_recruiting_chat(chat=self.chat, user=self.student)
        self.client = Client()
        now = timezone.now()
        self.starts = (now + timedelta(days=3)).isoformat()
        self.ends = (now + timedelta(days=3, hours=2)).isoformat()

    def tearDown(self):
        cache.clear()

    def _url(self, suffix: str = "", chat_id: int | None = None) -> str:
        cid = chat_id if chat_id is not None else self.chat.pk
        base = f"/api/v1/organizations/{self.org.slug}/recruiting-chat/events/{suffix}"
        sep = "&" if "?" in base else "?"
        return f"{base}{sep}chat={cid}"

    def _json(self, method: str, url: str, **payload):
        handler = getattr(self.client, method.lower())
        if payload:
            return handler(
                url,
                data=json.dumps(payload),
                content_type="application/json",
            )
        return handler(url)

    def _create_event(self, actor=None, **overrides):
        self.client.force_login(actor or self.owner)
        data = {
            "title": "練習",
            "description": "体育館",
            "starts_at": self.starts,
            "ends_at": self.ends,
            "venue_name": "戸山",
        }
        data.update(overrides)
        return self._json("post", self._url(), **data)

    def test_participants_can_view_and_rsvp_non_members_cannot(self):
        created = self._create_event()
        self.assertEqual(created.status_code, 201, created.content)
        event_id = created.json()["event"]["id"]
        body = created.json()["event"]
        self.assertEqual(body["going_count"], 0)
        self.assertEqual(body["unanswered_count"], 2)

        self.client.force_login(self.student)
        detail = self.client.get(self._url(f"{event_id}/"))
        self.assertEqual(detail.status_code, 200, detail.content)
        rsvp = self._json("post", self._url(f"{event_id}/rsvp/"), answer="going")
        self.assertEqual(rsvp.status_code, 200, rsvp.content)
        self.assertEqual(rsvp.json()["event"]["viewer_answer"], "going")
        self.assertEqual(rsvp.json()["event"]["going_count"], 1)
        changed = self._json("post", self._url(f"{event_id}/rsvp/"), answer="maybe")
        self.assertEqual(changed.json()["event"]["viewer_answer"], "maybe")
        self.assertEqual(changed.json()["event"]["maybe_count"], 1)
        self.assertEqual(changed.json()["event"]["going_count"], 0)

        self.client.force_login(self.outsider)
        hidden = self.client.get(self._url(f"{event_id}/"))
        self.assertEqual(hidden.status_code, 404)
        other_org = self.client.get(
            f"/api/v1/organizations/{self.other_org.slug}/recruiting-chat/events/"
            f"{event_id}/?chat={self.chat.pk}"
        )
        self.assertIn(other_org.status_code, {403, 404})

        self.client.force_login(self.owner)
        other_chat = self.client.get(self._url(f"{event_id}/", chat_id=self.other_chat.pk))
        self.assertEqual(other_chat.status_code, 404)

    def test_admin_outside_chat_cannot_view_and_kicked_user_loses_access(self):
        created = self._create_event()
        event_id = created.json()["event"]["id"]
        self.client.force_login(self.admin)
        hidden = self.client.get(self._url(f"{event_id}/"))
        self.assertEqual(hidden.status_code, 404)

        self.client.force_login(self.student)
        self._json("post", self._url(f"{event_id}/rsvp/"), answer="going")
        ChatRoomMembership.objects.filter(
            room=self.chat.room, user=self.student
        ).delete()
        denied = self.client.get(self._url(f"{event_id}/"))
        self.assertEqual(denied.status_code, 404)
        rsvp = self._json("post", self._url(f"{event_id}/rsvp/"), answer="not_going")
        self.assertEqual(rsvp.status_code, 404)

        self.client.force_login(self.owner)
        detail = self.client.get(self._url(f"{event_id}/"))
        self.assertEqual(detail.json()["event"]["going_count"], 0)
        self.assertEqual(detail.json()["event"]["unanswered_count"], 1)

    def test_archived_chat_rejects_new_rsvp(self):
        created = self._create_event()
        event_id = created.json()["event"]["id"]
        deactivate_recruiting_chat(chat=self.chat, actor=self.owner)
        self.client.force_login(self.student)
        rsvp = self._json("post", self._url(f"{event_id}/rsvp/"), answer="going")
        self.assertEqual(rsvp.status_code, 403)
        self.assertEqual(rsvp.json()["error"], "inactive")

    def test_public_event_register_api_does_not_apply_to_chat_events(self):
        created = self._create_event()
        event_id = created.json()["event"]["id"]
        chat_event = OrganizationChatEvent.objects.get(pk=event_id)
        self.client.force_login(self.student)
        public = self.client.post(
            f"/api/v1/organizations/{self.org.slug}/events/{event_id}/register/"
        )
        self.assertEqual(public.status_code, 404)
        self.assertTrue(
            OrganizationChatEvent.objects.filter(pk=chat_event.pk).exists()
        )

    def test_linked_profile_switch_does_not_inherit_rsvp_access(self):
        created = self._create_event()
        event_id = created.json()["event"]["id"]
        self.client.force_login(self.student)
        rsvp = self._json("post", self._url(f"{event_id}/rsvp/"), answer="going")
        self.assertEqual(rsvp.status_code, 200, rsvp.content)

        created_alt = self.client.post(
            "/api/v1/me/linked-profiles/create/",
            data=json.dumps(
                {"username": "cestudentalt", "display_name": "Alt"}
            ),
            content_type="application/json",
        )
        self.assertEqual(created_alt.status_code, 200, created_alt.content)
        alt_id = created_alt.json()["me"]["user"]["id"]
        self.assertNotEqual(alt_id, self.student.pk)

        hidden = self.client.get(self._url(f"{event_id}/"))
        self.assertEqual(hidden.status_code, 404)
        denied = self._json("post", self._url(f"{event_id}/rsvp/"), answer="maybe")
        self.assertEqual(denied.status_code, 404)

        switched = self.client.post(
            "/api/v1/me/linked-profiles/switch/",
            data=json.dumps({"user_id": self.student.pk}),
            content_type="application/json",
        )
        self.assertEqual(switched.status_code, 200, switched.content)
        restored = self.client.get(self._url(f"{event_id}/"))
        self.assertEqual(restored.status_code, 200, restored.content)
        self.assertEqual(restored.json()["event"]["viewer_answer"], "going")

    def test_card_is_posted_into_chat(self):
        created = self._create_event()
        self.assertEqual(created.status_code, 201, created.content)
        event_id = created.json()["event"]["id"]
        self.client.force_login(self.student)
        messages = self.client.get(
            f"/api/v1/recruiting-chats/{self.chat.room_id}/messages/"
        )
        self.assertEqual(messages.status_code, 200, messages.content)
        shares = [
            row
            for row in messages.json()["messages"]
            if row.get("message_kind") == "share"
        ]
        self.assertEqual(shares[0]["share"]["type"], "org_chat_event")
        self.assertEqual(shares[0]["share"]["id"], event_id)
