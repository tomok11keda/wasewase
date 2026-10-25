"""Phase 4: organization recruiting events (not CalendarEvent)."""

from __future__ import annotations

import json
from datetime import timedelta
from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.utils import timezone

from .models import (
    Notification,
    Organization,
    OrganizationEvent,
    OrganizationEventRegistration,
    OrganizationMember,
    User,
    UserProfile,
)
from .organization_services import add_organization_member
from .spa_canonical import organization_event_url


def _make_user(email: str, **kwargs) -> User:
    kwargs.setdefault("password", "test-pass-12345")
    user = User.objects.create_user(email=email, **kwargs)
    UserProfile.objects.get_or_create(
        user=user,
        defaults={"name": kwargs.get("username") or email.split("@")[0]},
    )
    return user


def _make_org(**kwargs) -> Organization:
    kwargs.setdefault("name", "イベントサークル")
    kwargs.setdefault("slug", "event-circle")
    kwargs.setdefault("status", Organization.Status.ACTIVE)
    kwargs.setdefault("is_listed", True)
    return Organization.objects.create(**kwargs)


@override_settings(BROWSE_MODE_GATE_ENABLED=False)
class OrganizationEventApiTests(TestCase):
    def setUp(self):
        cache.clear()
        self.owner = _make_user("ev-owner@waseda.jp", username="evowner")
        self.admin = _make_user("ev-admin@waseda.jp", username="evadmin")
        self.member = _make_user("ev-member@waseda.jp", username="evmember")
        self.student = _make_user("ev-student@waseda.jp", username="evstudent")
        self.other = _make_user("ev-other@waseda.jp", username="evother")
        self.other_owner = _make_user("ev-otherown@waseda.jp", username="evotherown")
        self.org = _make_org()
        self.other_org = _make_org(name="別イベント団体", slug="event-other-org")
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
        now = timezone.now()
        self.starts = (now + timedelta(days=7)).isoformat()
        self.ends = (now + timedelta(days=7, hours=2)).isoformat()

    def tearDown(self):
        cache.clear()

    def _url(self, suffix: str = "", slug: str | None = None) -> str:
        return f"/api/v1/organizations/{slug or self.org.slug}/events/{suffix}"

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

    def _create_payload(self, **overrides):
        data = {
            "title": "新歓説明会",
            "description": "サークル紹介",
            "starts_at": self.starts,
            "ends_at": self.ends,
            "venue_name": "大隈講堂",
            "venue_address": "早稲田",
        }
        data.update(overrides)
        return data

    def _create_event(self, actor=None, **overrides):
        self.client.force_login(actor or self.owner)
        return self._json("post", self._url(), **self._create_payload(**overrides))

    def _publish(self, event_id, actor=None):
        self.client.force_login(actor or self.owner)
        return self._json("post", self._url(f"{event_id}/publish/"))

    def test_owner_and_admin_can_create_member_and_others_cannot(self):
        created = self._create_event()
        self.assertEqual(created.status_code, 201, created.content)
        body = created.json()["event"]
        self.assertEqual(body["status"], "draft")
        self.assertTrue(body["can_manage"])
        self.assertIsNone(body["viewer_status"])

        admin_created = self._create_event(actor=self.admin, title="admin event")
        self.assertEqual(admin_created.status_code, 201, admin_created.content)

        self.client.force_login(self.member)
        denied_member = self._json("post", self._url(), **self._create_payload())
        self.assertEqual(denied_member.status_code, 403)

        self.client.force_login(self.student)
        denied_student = self._json("post", self._url(), **self._create_payload())
        self.assertEqual(denied_student.status_code, 403)

        self.client.force_login(self.other_owner)
        denied_other = self._json("post", self._url(), **self._create_payload())
        self.assertEqual(denied_other.status_code, 403)

        guest = Client()
        anon = guest.post(
            self._url(),
            data=json.dumps(self._create_payload()),
            content_type="application/json",
        )
        self.assertEqual(anon.status_code, 401)

    def test_draft_is_hidden_from_students_and_visible_to_managers(self):
        created = self._create_event()
        event_id = created.json()["event"]["id"]

        self.client.force_login(self.student)
        listing = self.client.get(self._url())
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.json()["events"], [])
        detail = self.client.get(self._url(f"{event_id}/"))
        self.assertEqual(detail.status_code, 404)

        self.client.force_login(self.owner)
        manage = self.client.get(self._url() + "?manage=1")
        self.assertEqual(manage.status_code, 200)
        self.assertEqual(len(manage.json()["events"]), 1)
        self.assertEqual(self.client.get(self._url(f"{event_id}/")).status_code, 200)

        self.client.force_login(self.student)
        forbidden_manage = self.client.get(self._url() + "?manage=1")
        self.assertEqual(forbidden_manage.status_code, 403)

    def test_publish_register_cancel_reregister_unlimited(self):
        created = self._create_event()
        event_id = created.json()["event"]["id"]
        published = self._publish(event_id)
        self.assertEqual(published.status_code, 200)
        self.assertEqual(published.json()["event"]["status"], "published")

        self.client.force_login(self.student)
        hidden_draft_register = self._json("post", self._url(f"{event_id}/register/"))
        # already published
        self.assertEqual(hidden_draft_register.status_code, 200, hidden_draft_register.content)
        first = hidden_draft_register.json()["event"]
        self.assertTrue(first["viewer_registered"])
        self.assertEqual(first["registered_count"], 1)
        notes = Notification.objects.filter(recipient=self.student)
        self.assertEqual(notes.count(), 1)
        self.assertIn("申し込みました", notes.get().message)
        self.assertEqual(
            notes.get().link,
            organization_event_url(self.org.slug, event_id),
        )

        duplicate = self._json("post", self._url(f"{event_id}/register/"))
        self.assertEqual(duplicate.status_code, 200)
        self.assertEqual(
            OrganizationEventRegistration.objects.filter(event_id=event_id).count(),
            1,
        )

        cancelled = self._json("post", self._url(f"{event_id}/unregister/"))
        self.assertEqual(cancelled.status_code, 200)
        self.assertFalse(cancelled.json()["event"]["viewer_registered"])

        again = self._json("post", self._url(f"{event_id}/register/"))
        self.assertEqual(again.status_code, 200)
        self.assertTrue(again.json()["event"]["viewer_registered"])

        self.client.force_login(self.other)
        second = self._json("post", self._url(f"{event_id}/register/"))
        self.assertEqual(second.status_code, 200)
        extra = _make_user("ev-full@waseda.jp", username="evfull")
        self.client.force_login(extra)
        third = self._json("post", self._url(f"{event_id}/register/"))
        self.assertEqual(third.status_code, 200, third.content)
        self.assertEqual(
            OrganizationEventRegistration.objects.filter(
                event_id=event_id,
                status=OrganizationEventRegistration.Status.REGISTERED,
            ).count(),
            3,
        )
        self.assertNotIn("is_full", third.json()["event"])
        self.assertNotIn("capacity", third.json()["event"])

    def test_cannot_unregister_someone_else_or_edit_other_org(self):
        created = self._create_event()
        event_id = created.json()["event"]["id"]
        self._publish(event_id)
        self.client.force_login(self.student)
        self._json("post", self._url(f"{event_id}/register/"))

        self.client.force_login(self.other)
        stolen = self._json("post", self._url(f"{event_id}/unregister/"))
        self.assertEqual(stolen.status_code, 409)
        self.assertTrue(
            OrganizationEventRegistration.objects.filter(
                event_id=event_id,
                user=self.student,
                status=OrganizationEventRegistration.Status.REGISTERED,
            ).exists()
        )

        self.client.force_login(self.other_owner)
        patched = self._json(
            "patch",
            self._url(f"{event_id}/"),
            title="乗っ取り",
        )
        self.assertEqual(patched.status_code, 403)
        cross = self.client.get(
            f"/api/v1/organizations/{self.other_org.slug}/events/{event_id}/"
        )
        self.assertEqual(cross.status_code, 404)

    def test_validation_rejects_inverted_schedule_and_ignores_capacity(self):
        self.client.force_login(self.owner)
        inverted = self._json(
            "post",
            self._url(),
            **self._create_payload(starts_at=self.ends, ends_at=self.starts),
        )
        self.assertEqual(inverted.status_code, 400)
        self.assertIn("ends_at", inverted.json()["errors"])

        created = self._json(
            "post", self._url(), **self._create_payload(capacity=0)
        )
        self.assertEqual(created.status_code, 201, created.content)
        self.assertNotIn("capacity", created.json()["event"])

    def test_cancel_notifies_registrants_and_blocks_new_signups(self):
        created = self._create_event()
        event_id = created.json()["event"]["id"]
        self._publish(event_id)
        self.client.force_login(self.student)
        self._json("post", self._url(f"{event_id}/register/"))
        Notification.objects.filter(recipient=self.student).delete()

        self.client.force_login(self.owner)
        cancelled = self._json("post", self._url(f"{event_id}/cancel/"))
        self.assertEqual(cancelled.status_code, 200)
        self.assertEqual(cancelled.json()["event"]["status"], "cancelled")

        notes = Notification.objects.filter(recipient=self.student)
        self.assertEqual(notes.count(), 1)
        self.assertIn("中止", notes.get().message)

        self.client.force_login(self.other)
        blocked = self._json("post", self._url(f"{event_id}/register/"))
        self.assertEqual(blocked.status_code, 409)
        self.assertEqual(blocked.json()["error"], "cancelled")

        listing = self.client.get(self._url())
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.json()["events"][0]["status"], "cancelled")

    def test_draft_org_hides_events_from_students_not_invite_access(self):
        self.org.status = Organization.Status.DRAFT
        self.org.is_listed = False
        self.org.save(update_fields=["status", "is_listed"])
        created = self._create_event()
        event_id = created.json()["event"]["id"]
        self._publish(event_id)

        self.client.force_login(self.student)
        self.assertEqual(self.client.get(self._url()).status_code, 404)
        self.assertEqual(self.client.get(self._url(f"{event_id}/")).status_code, 404)
        self.assertEqual(
            self._json("post", self._url(f"{event_id}/register/")).status_code,
            404,
        )

        self.client.force_login(self.owner)
        self.assertEqual(self.client.get(self._url(f"{event_id}/")).status_code, 200)

    def test_suspended_blocks_create_register_and_student_view(self):
        created = self._create_event()
        event_id = created.json()["event"]["id"]
        self._publish(event_id)
        self.org.status = Organization.Status.SUSPENDED
        self.org.save(update_fields=["status"])

        self.client.force_login(self.student)
        self.assertEqual(self.client.get(self._url()).status_code, 404)
        self.assertEqual(
            self._json("post", self._url(f"{event_id}/register/")).status_code,
            404,
        )

        self.client.force_login(self.owner)
        create_blocked = self._json("post", self._url(), **self._create_payload())
        self.assertEqual(create_blocked.status_code, 403)

    def test_ended_and_deadline_and_registration_closed(self):
        now = timezone.now()
        created = self._create_event(
            starts_at=(now + timedelta(hours=2)).isoformat(),
            ends_at=(now + timedelta(hours=4)).isoformat(),
            registration_deadline=(now - timedelta(minutes=1)).isoformat(),
        )
        event_id = created.json()["event"]["id"]
        self._publish(event_id)
        self.client.force_login(self.student)
        late = self._json("post", self._url(f"{event_id}/register/"))
        self.assertEqual(late.status_code, 409)
        self.assertEqual(late.json()["error"], "deadline_passed")

        past = self._create_event(
            title="終了済み",
            starts_at=(now - timedelta(days=2)).isoformat(),
            ends_at=(now - timedelta(days=2, hours=-2)).isoformat(),
            registration_deadline=None,
        )
        # ends_at must be after starts_at; use past window
        self.assertEqual(past.status_code, 201, past.content)
        past_id = past.json()["event"]["id"]
        OrganizationEvent.objects.filter(pk=past_id).update(
            starts_at=now - timedelta(days=2),
            ends_at=now - timedelta(hours=1),
            status=OrganizationEvent.Status.PUBLISHED,
        )
        ended = self._json("post", self._url(f"{past_id}/register/"))
        self.assertEqual(ended.status_code, 409)
        self.assertEqual(ended.json()["error"], "ended")

        open_event = self._create_event(title="受付停止")
        open_id = open_event.json()["event"]["id"]
        self._publish(open_id)
        self.client.force_login(self.owner)
        closed = self._json(
            "patch", self._url(f"{open_id}/"), registration_open=False
        )
        self.assertEqual(closed.status_code, 200)
        self.client.force_login(self.student)
        stopped = self._json("post", self._url(f"{open_id}/register/"))
        self.assertEqual(stopped.status_code, 409)
        self.assertEqual(stopped.json()["error"], "registration_closed")

    def test_registrations_list_is_manager_only_and_hides_email(self):
        created = self._create_event()
        event_id = created.json()["event"]["id"]
        self._publish(event_id)
        self.client.force_login(self.student)
        self._json("post", self._url(f"{event_id}/register/"))

        denied = self.client.get(self._url(f"{event_id}/registrations/"))
        self.assertEqual(denied.status_code, 403)

        self.client.force_login(self.owner)
        listing = self.client.get(self._url(f"{event_id}/registrations/"))
        self.assertEqual(listing.status_code, 200)
        dumped = listing.content.decode("utf-8")
        self.assertNotIn(self.student.email, dumped)
        self.assertEqual(listing.json()["total"], 1)
        self.assertEqual(listing.json()["registrations"][0]["user"]["id"], self.student.pk)

        mine = self.client.get("/api/v1/me/event-registrations/")
        self.assertEqual(mine.status_code, 200)
        self.client.force_login(self.student)
        mine = self.client.get("/api/v1/me/event-registrations/")
        self.assertEqual(len(mine.json()["events"]), 1)

    def test_csrf_required_and_select_for_update_in_register(self):
        created = self._create_event()
        event_id = created.json()["event"]["id"]
        self._publish(event_id)
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.student)
        csrf = csrf_client.post(
            self._url(f"{event_id}/register/"),
            data=json.dumps({}),
            content_type="application/json",
        )
        self.assertEqual(csrf.status_code, 403)
        self.assertEqual(csrf.json()["error"], "csrf_failed")

        from . import organization_event_services as services

        source = services.register_organization_event.__code__.co_filename
        with open(source, encoding="utf-8") as handle:
            body = handle.read()
        self.assertIn("select_for_update", body)

    def test_important_update_notifies_and_delete_hides_event(self):
        created = self._create_event()
        event_id = created.json()["event"]["id"]
        self._publish(event_id)
        self.client.force_login(self.student)
        self._json("post", self._url(f"{event_id}/register/"))
        Notification.objects.filter(recipient=self.student).delete()

        self.client.force_login(self.owner)
        later = (timezone.now() + timedelta(days=8)).isoformat()
        later_end = (timezone.now() + timedelta(days=8, hours=2)).isoformat()
        updated = self._json(
            "patch",
            self._url(f"{event_id}/"),
            starts_at=later,
            ends_at=later_end,
        )
        self.assertEqual(updated.status_code, 200)
        notes = Notification.objects.filter(recipient=self.student)
        self.assertEqual(notes.count(), 1)
        self.assertIn("変更", notes.get().message)

        deleted = self._json("post", self._url(f"{event_id}/delete/"))
        self.assertEqual(deleted.status_code, 200)
        self.client.force_login(self.student)
        self.assertEqual(self.client.get(self._url(f"{event_id}/")).status_code, 404)
        self.assertEqual(self.client.get(self._url()).json()["events"], [])

    def test_calendar_event_is_not_organization_event(self):
        from .models import CalendarEvent
        from datetime import date

        CalendarEvent.objects.create(
            user=self.student, title="個人予定", date=date.today()
        )
        self.client.force_login(self.student)
        listing = self.client.get(self._url())
        self.assertEqual(listing.json()["events"], [])

    def test_unlimited_registration_during_open_period(self):
        created = self._create_event()
        event_id = created.json()["event"]["id"]
        self._publish(event_id)
        for index, user in enumerate((self.student, self.other, self.member)):
            self.client.force_login(user)
            response = self._json("post", self._url(f"{event_id}/register/"))
            self.assertEqual(response.status_code, 200, response.content)
            self.assertEqual(response.json()["event"]["registered_count"], index + 1)
