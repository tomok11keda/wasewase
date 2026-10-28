"""Optional organization-event lottery: exclusion notes, fairness, share, ACL."""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.utils import timezone

from .models import (
    ChatMessage,
    Notification,
    Organization,
    OrganizationEvent,
    OrganizationEventLottery,
    OrganizationEventLotteryEntry,
    OrganizationEventRegistration,
    OrganizationMember,
    User,
    UserProfile,
)
from .organization_recruiting_chat_services import (
    create_recruiting_chat,
    join_or_apply_recruiting_chat,
)
from .organization_services import add_organization_member
from .spa_canonical import organization_event_lottery_url


def _make_user(email: str, **kwargs) -> User:
    kwargs.setdefault("password", "test-pass-12345")
    user = User.objects.create_user(email=email, **kwargs)
    UserProfile.objects.get_or_create(
        user=user,
        defaults={"name": kwargs.get("username") or email.split("@")[0]},
    )
    return user


def _make_org(**kwargs) -> Organization:
    kwargs.setdefault("name", "抽選サークル")
    kwargs.setdefault("slug", "lottery-circle")
    kwargs.setdefault("status", Organization.Status.ACTIVE)
    kwargs.setdefault("is_listed", True)
    return Organization.objects.create(**kwargs)


@override_settings(BROWSE_MODE_GATE_ENABLED=False)
class OrganizationEventLotteryApiTests(TestCase):
    def setUp(self):
        cache.clear()
        self.owner = _make_user("lot-owner@waseda.jp", username="lotowner")
        self.admin = _make_user("lot-admin@waseda.jp", username="lotadmin")
        self.member = _make_user("lot-member@waseda.jp", username="lotmember")
        self.student = _make_user("lot-student@waseda.jp", username="lotstudent")
        self.other = _make_user("lot-other@waseda.jp", username="lotother")
        self.third = _make_user("lot-third@waseda.jp", username="lotthird")
        self.other_owner = _make_user("lot-otherown@waseda.jp", username="lototherown")
        self.org = _make_org()
        self.other_org = _make_org(name="別抽選団体", slug="lottery-other-org")
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

    def _event_url(self, suffix: str = "", slug: str | None = None) -> str:
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

    def _create_published_event(self, actor=None, **overrides):
        self.client.force_login(actor or self.owner)
        data = {
            "title": "新歓説明会",
            "description": "紹介",
            "starts_at": self.starts,
            "ends_at": self.ends,
            "venue_name": "大隈講堂",
            "venue_address": "早稲田",
        }
        data.update(overrides)
        created = self._json("post", self._event_url(), **data)
        self.assertEqual(created.status_code, 201, created.content)
        event_id = created.json()["event"]["id"]
        published = self._json("post", self._event_url(f"{event_id}/publish/"))
        self.assertEqual(published.status_code, 200, published.content)
        return event_id

    def _register(self, event_id, user):
        self.client.force_login(user)
        response = self._json("post", self._event_url(f"{event_id}/register/"))
        self.assertEqual(response.status_code, 200, response.content)
        return response

    def _close_registration(self, event_id, actor=None):
        self.client.force_login(actor or self.owner)
        response = self._json(
            "patch",
            self._event_url(f"{event_id}/"),
            registration_open=False,
        )
        self.assertEqual(response.status_code, 200, response.content)
        return response

    def _run_lottery(self, event_id, actor=None, **payload):
        self._close_registration(event_id, actor=self.owner)
        self.client.force_login(actor or self.owner)
        if "applicant_ids" not in payload:
            payload = {
                **payload,
                "applicant_ids": list(
                    OrganizationEventRegistration.objects.filter(
                        event_id=event_id,
                        status=OrganizationEventRegistration.Status.REGISTERED,
                    ).values_list("user_id", flat=True)
                ),
            }
        return self._json("post", self._event_url(f"{event_id}/lottery/"), **payload)

    def test_event_without_lottery_stays_normal(self):
        event_id = self._create_published_event()
        self._register(event_id, self.student)
        self.client.force_login(self.student)
        detail = self.client.get(self._event_url(f"{event_id}/"))
        body = detail.json()["event"]
        self.assertFalse(body["has_lottery"])
        self.assertIsNone(body["viewer_lottery_result"])
        self.assertFalse(body["can_run_lottery"])
        self.client.force_login(self.owner)
        manage = self.client.get(self._event_url(f"{event_id}/"))
        self.assertFalse(manage.json()["event"]["can_run_lottery"])
        self._close_registration(event_id)
        manage = self.client.get(self._event_url(f"{event_id}/"))
        self.assertTrue(manage.json()["event"]["can_run_lottery"])
        missing = self.client.get(self._event_url(f"{event_id}/lottery/"))
        self.assertEqual(missing.status_code, 404)
        self.assertEqual(missing.json()["error"], "no_lottery")

    def test_owner_and_admin_can_draw_member_student_and_other_org_cannot(self):
        event_id = self._create_published_event()
        self._register(event_id, self.student)
        self._register(event_id, self.other)

        self.client.force_login(self.member)
        denied_member = self._run_lottery(event_id, actor=self.member, winner_count=1)
        self.assertEqual(denied_member.status_code, 403)

        self.client.force_login(self.student)
        denied_student = self._run_lottery(event_id, actor=self.student, winner_count=1)
        self.assertEqual(denied_student.status_code, 403)

        self.client.force_login(self.other_owner)
        denied_other = self._run_lottery(
            event_id, actor=self.other_owner, winner_count=1
        )
        self.assertEqual(denied_other.status_code, 403)

        guest = Client()
        anon = guest.post(
            self._event_url(f"{event_id}/lottery/"),
            data=json.dumps({"winner_count": 1}),
            content_type="application/json",
        )
        self.assertEqual(anon.status_code, 401)

        drawn = self._run_lottery(event_id, actor=self.admin, winner_count=1)
        self.assertEqual(drawn.status_code, 201, drawn.content)
        lottery = drawn.json()["lottery"]
        self.assertEqual(lottery["applicant_count"], 2)
        self.assertEqual(lottery["eligible_count"], 2)
        self.assertEqual(lottery["winner_count"], 1)
        self.assertEqual(lottery["not_selected_count"], 1)
        self.assertEqual(lottery["excluded_count"], 0)
        self.assertEqual(len(lottery["selected"]), 1)
        self.assertEqual(len(lottery["not_selected"]), 1)

    def test_exclude_notes_counts_and_no_sensitive_note_in_notifications(self):
        event_id = self._create_published_event()
        self._register(event_id, self.student)
        self._register(event_id, self.other)
        self._register(event_id, self.third)
        Notification.objects.all().delete()

        with patch(
            "app.organization_event_lottery_services.secrets.SystemRandom"
        ) as rng:
            rng.return_value.sample.side_effect = lambda seq, k: list(seq)[:k]
            drawn = self._run_lottery(
                event_id,
                winner_count=1,
                excluded=[
                    {"user_id": self.student.pk, "note": "サークル運営メンバー"}
                ],
            )
        self.assertEqual(drawn.status_code, 201, drawn.content)
        lottery = drawn.json()["lottery"]
        self.assertEqual(lottery["applicant_count"], 3)
        self.assertEqual(lottery["eligible_count"], 2)
        self.assertEqual(lottery["excluded_count"], 1)
        self.assertEqual(lottery["winner_count"], 1)
        self.assertEqual(lottery["not_selected_count"], 1)
        self.assertEqual(lottery["excluded"][0]["exclusion_note"], "サークル運営メンバー")
        self.assertNotIn("email", json.dumps(lottery))

        notes = list(Notification.objects.all())
        self.assertEqual(len(notes), 3)
        self.assertTrue(any("当選" in row.message for row in notes))
        self.assertTrue(any("抽選結果が出ました" in row.message for row in notes))
        self.assertTrue(any("対象外" in row.message for row in notes))
        for row in notes:
            self.assertNotIn("サークル運営メンバー", row.message)
            self.assertEqual(
                row.link,
                organization_event_lottery_url(self.org.slug, event_id),
            )

        event = OrganizationEvent.objects.get(pk=event_id)
        self.assertFalse(event.registration_open)
        self.client.force_login(self.member)
        closed = self._json("post", self._event_url(f"{event_id}/register/"))
        self.assertEqual(closed.status_code, 409)
        self.assertEqual(closed.json()["error"], "lottery_closed")

        self.client.force_login(self.student)
        own = self.client.get(self._event_url(f"{event_id}/"))
        self.assertEqual(own.json()["event"]["viewer_lottery_result"], "excluded")

    def test_zero_eligible_and_winner_count_over_eligible(self):
        event_id = self._create_published_event()
        self._register(event_id, self.student)
        over = self._run_lottery(event_id, winner_count=2)
        self.assertEqual(over.status_code, 400)
        self.assertEqual(over.json()["error"], "winner_count_exceeds_eligible")

        empty = self._run_lottery(
            event_id,
            winner_count=0,
            excluded=[{"user_id": self.student.pk, "note": ""}],
        )
        self.assertEqual(empty.status_code, 400)
        self.assertEqual(empty.json()["error"], "no_eligible")
        self.assertFalse(
            OrganizationEventLottery.objects.filter(event_id=event_id).exists()
        )
        event = OrganizationEvent.objects.get(pk=event_id)
        self.assertFalse(event.registration_open)

    def test_double_lottery_is_rejected_and_source_uses_secrets(self):
        event_id = self._create_published_event()
        self._register(event_id, self.student)
        first = self._run_lottery(event_id, winner_count=1)
        self.assertEqual(first.status_code, 201, first.content)
        second = self._run_lottery(event_id, winner_count=1)
        self.assertEqual(second.status_code, 409)
        self.assertEqual(second.json()["error"], "already_drawn")
        self.assertEqual(OrganizationEventLottery.objects.filter(event_id=event_id).count(), 1)

        from . import organization_event_lottery_services as services

        with open(services.run_organization_event_lottery.__code__.co_filename, encoding="utf-8") as handle:
            body = handle.read()
        self.assertIn("secrets.SystemRandom", body)
        self.assertIn("select_for_update", body)
        self.assertIn("transaction.atomic", body)
        self.assertIn("registration_open = False", body)
        self.assertNotIn("Math.random", body)

    def test_transaction_failure_rolls_back_lottery_and_notifications(self):
        event_id = self._create_published_event()
        self._register(event_id, self.student)
        Notification.objects.all().delete()
        with patch.object(
            OrganizationEventLotteryEntry.objects,
            "bulk_create",
            side_effect=RuntimeError("boom"),
        ):
            with self.assertRaises(RuntimeError):
                self._run_lottery(event_id, winner_count=1)
        self.assertFalse(OrganizationEventLottery.objects.filter(event_id=event_id).exists())
        self.assertEqual(Notification.objects.count(), 0)
        event = OrganizationEvent.objects.get(pk=event_id)
        self.assertFalse(event.registration_open)

    def test_lottery_view_requires_recruiting_member_or_manager(self):
        event_id = self._create_published_event()
        self._register(event_id, self.student)
        self._register(event_id, self.other)
        chat = create_recruiting_chat(
            organization=self.org, actor=self.owner, name="2026新歓"
        )
        join_or_apply_recruiting_chat(chat=chat, user=self.student)
        drawn = self._run_lottery(event_id, winner_count=1)
        self.assertEqual(drawn.status_code, 201, drawn.content)

        self.client.force_login(self.student)
        allowed = self.client.get(self._event_url(f"{event_id}/lottery/"))
        self.assertEqual(allowed.status_code, 200, allowed.content)
        self.assertEqual(len(allowed.json()["lottery"]["selected"]), 1)

        self.client.force_login(self.other)
        own_only = self.client.get(self._event_url(f"{event_id}/lottery/"))
        self.assertEqual(own_only.status_code, 200, own_only.content)
        own_lottery = own_only.json()["lottery"]
        self.assertFalse(own_lottery["lists_visible"])
        self.assertFalse(own_lottery["can_view"])
        self.assertNotIn("selected", own_lottery)
        self.assertNotIn("not_selected", own_lottery)
        self.assertNotIn("excluded", own_lottery)
        self.assertIn(own_lottery["viewer_entry"]["result"], {"selected", "not_selected"})
        own = self.client.get(self._event_url(f"{event_id}/"))
        self.assertIn(own.json()["event"]["viewer_lottery_result"], {"selected", "not_selected"})
        self.assertFalse(own.json()["event"]["can_view_lottery"])

        self.client.force_login(self.other_owner)
        other_manager = self.client.get(self._event_url(f"{event_id}/lottery/"))
        self.assertEqual(other_manager.status_code, 403)

    def test_share_to_recruiting_chat_is_once_and_reads_saved_result(self):
        event_id = self._create_published_event()
        self._register(event_id, self.student)
        chat = create_recruiting_chat(
            organization=self.org, actor=self.owner, name="2026新歓"
        )
        join_or_apply_recruiting_chat(chat=chat, user=self.student)
        drawn = self._run_lottery(event_id, winner_count=1)
        self.assertEqual(drawn.status_code, 201, drawn.content)

        self.client.force_login(self.student)
        student_share = self._json(
            "post", self._event_url(f"{event_id}/lottery/share/")
        )
        self.assertEqual(student_share.status_code, 403)

        self.client.force_login(self.owner)
        shared = self._json("post", self._event_url(f"{event_id}/lottery/share/"))
        self.assertEqual(shared.status_code, 200, shared.content)
        self.assertTrue(shared.json()["lottery"]["shared"])
        duplicate = self._json("post", self._event_url(f"{event_id}/lottery/share/"))
        self.assertEqual(duplicate.status_code, 409)
        self.assertEqual(duplicate.json()["error"], "already_shared")

        self.client.force_login(self.student)
        messages = self.client.get(f"/api/v1/recruiting-chats/{chat.room_id}/messages/")
        self.assertEqual(messages.status_code, 200, messages.content)
        rows = messages.json()["messages"]
        share_rows = [row for row in rows if row.get("message_kind") == "share"]
        self.assertEqual(len(share_rows), 1)
        share = share_rows[0]["share"]
        self.assertEqual(share["type"], "org_event_lottery")
        self.assertEqual(share["content"]["winner_count"], 1)
        self.assertEqual(
            share["content"]["path"],
            f"/organizations/{self.org.slug}/events/{event_id}/lottery",
        )
        self.assertEqual(ChatMessage.objects.filter(room=chat.room).count(), 1)

        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.owner)
        csrf = csrf_client.post(
            self._event_url(f"{event_id}/lottery/"),
            data=json.dumps({"winner_count": 1}),
            content_type="application/json",
        )
        self.assertEqual(csrf.status_code, 403)
        self.assertEqual(csrf.json()["error"], "csrf_failed")

    def test_share_can_retry_after_message_delete_without_changing_results(self):
        from .chat_message_services import soft_delete_own_chat_message

        event_id = self._create_published_event()
        self._register(event_id, self.student)
        chat = create_recruiting_chat(
            organization=self.org, actor=self.owner, name="2026新歓"
        )
        join_or_apply_recruiting_chat(chat=chat, user=self.student)
        drawn = self._run_lottery(event_id, winner_count=1)
        self.assertEqual(drawn.status_code, 201, drawn.content)
        winner_count = drawn.json()["lottery"]["winner_count"]
        excluded_count = drawn.json()["lottery"]["excluded_count"]
        lottery_id = drawn.json()["lottery"]["id"]

        self.client.force_login(self.owner)
        shared = self._json("post", self._event_url(f"{event_id}/lottery/share/"))
        self.assertEqual(shared.status_code, 200, shared.content)
        self.assertTrue(shared.json()["lottery"]["shared"])
        message = ChatMessage.objects.get(
            pk=OrganizationEventLottery.objects.get(pk=lottery_id).shared_message_id
        )
        soft_delete_own_chat_message(message, self.owner)

        self.client.force_login(self.student)
        tombstones = self.client.get(
            f"/api/v1/recruiting-chats/{chat.room_id}/messages/"
        )
        self.assertEqual(tombstones.status_code, 200, tombstones.content)
        rows = tombstones.json()["messages"]
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0]["is_deleted"])
        self.assertNotEqual(rows[0].get("message_kind"), "share")
        self.assertIsNone(rows[0].get("share"))

        self.client.force_login(self.owner)
        after_delete = self.client.get(self._event_url(f"{event_id}/lottery/"))
        self.assertEqual(after_delete.status_code, 200, after_delete.content)
        self.assertFalse(after_delete.json()["lottery"]["shared"])
        self.assertTrue(after_delete.json()["lottery"]["can_share"])
        retried = self._json("post", self._event_url(f"{event_id}/lottery/share/"))
        self.assertEqual(retried.status_code, 200, retried.content)
        self.assertTrue(retried.json()["lottery"]["shared"])
        self.assertEqual(retried.json()["lottery"]["id"], lottery_id)
        self.assertEqual(retried.json()["lottery"]["winner_count"], winner_count)
        self.assertEqual(retried.json()["lottery"]["excluded_count"], excluded_count)
        self.assertEqual(
            OrganizationEventLotteryEntry.objects.filter(lottery_id=lottery_id).count(),
            1,
        )
        duplicate = self._json("post", self._event_url(f"{event_id}/lottery/share/"))
        self.assertEqual(duplicate.status_code, 409)
        self.assertEqual(duplicate.json()["error"], "already_shared")

        self.client.force_login(self.student)
        messages = self.client.get(f"/api/v1/recruiting-chats/{chat.room_id}/messages/")
        live_shares = [
            row
            for row in messages.json()["messages"]
            if row.get("message_kind") == "share" and not row.get("is_deleted")
        ]
        self.assertEqual(len(live_shares), 1)
        self.assertEqual(live_shares[0]["share"]["content"]["winner_count"], winner_count)
        self.assertEqual(ChatMessage.objects.filter(room=chat.room).count(), 2)

        lottery = OrganizationEventLottery.objects.get(pk=lottery_id)
        previous_message_id = lottery.shared_message_id
        lottery.shared_message = None
        lottery.save(update_fields=["shared_message", "updated_at"])
        self.client.force_login(self.owner)
        after_null = self._json("post", self._event_url(f"{event_id}/lottery/share/"))
        self.assertEqual(after_null.status_code, 409, after_null.content)
        self.assertEqual(after_null.json()["error"], "already_shared")
        lottery.refresh_from_db()
        self.assertIsNone(lottery.shared_message_id)
        self.assertTrue(
            ChatMessage.objects.filter(pk=previous_message_id, is_hidden=False).exists()
        )

    def test_cancel_after_register_is_not_in_lottery_snapshot(self):
        event_id = self._create_published_event()
        self._register(event_id, self.student)
        self._register(event_id, self.other)
        self.client.force_login(self.student)
        cancelled = self._json("post", self._event_url(f"{event_id}/unregister/"))
        self.assertEqual(cancelled.status_code, 200)
        drawn = self._run_lottery(event_id, winner_count=1)
        self.assertEqual(drawn.status_code, 201, drawn.content)
        self.assertEqual(drawn.json()["lottery"]["applicant_count"], 1)
        user_ids = [
            row["user"]["id"]
            for row in drawn.json()["lottery"]["selected"]
            + drawn.json()["lottery"]["not_selected"]
            + drawn.json()["lottery"]["excluded"]
        ]
        self.assertEqual(user_ids, [self.other.pk])
        self.assertFalse(
            OrganizationEventLotteryEntry.objects.filter(
                lottery__event_id=event_id, user=self.student
            ).exists()
        )

    def test_lottery_closes_register_reopen_and_keeps_result_after_withdraw(self):
        event_id = self._create_published_event()
        self._register(event_id, self.student)
        self._register(event_id, self.other)
        drawn = self._run_lottery(event_id, winner_count=1)
        self.assertEqual(drawn.status_code, 201, drawn.content)
        self.client.force_login(self.owner)
        event_body = self.client.get(self._event_url(f"{event_id}/")).json()["event"]
        self.assertFalse(event_body["can_reopen_registration"])
        self.assertFalse(event_body["can_register"])

        reopen = self._json(
            "patch", self._event_url(f"{event_id}/"), registration_open=True
        )
        self.assertEqual(reopen.status_code, 409)
        self.assertEqual(reopen.json()["error"], "lottery_closed")

        self.client.force_login(self.student)
        detail = self.client.get(self._event_url(f"{event_id}/")).json()["event"]
        result = detail["viewer_lottery_result"]
        cancelled = self._json("post", self._event_url(f"{event_id}/unregister/"))
        self.assertEqual(cancelled.status_code, 200)
        after = self.client.get(self._event_url(f"{event_id}/")).json()["event"]
        self.assertEqual(after["viewer_status"], "cancelled")
        self.assertEqual(after["viewer_lottery_result"], result)
        self.assertFalse(after["can_register"])
        reregister = self._json("post", self._event_url(f"{event_id}/register/"))
        self.assertEqual(reregister.status_code, 409)
        self.assertEqual(reregister.json()["error"], "lottery_closed")
        self.assertEqual(
            OrganizationEventLotteryEntry.objects.get(
                lottery__event_id=event_id, user=self.student
            ).result,
            result,
        )
        self.client.force_login(self.third)
        stranger_register = self._json(
            "post", self._event_url(f"{event_id}/register/")
        )
        self.assertEqual(stranger_register.status_code, 409)
        self.assertEqual(stranger_register.json()["error"], "lottery_closed")
        stranger_lottery = self.client.get(self._event_url(f"{event_id}/lottery/"))
        self.assertEqual(stranger_lottery.status_code, 403)

    def test_stale_applicant_ids_and_invalid_excluded_are_rejected(self):
        event_id = self._create_published_event()
        self._register(event_id, self.student)
        stale = self._run_lottery(
            event_id,
            winner_count=1,
            applicant_ids=[self.student.pk, self.other.pk],
        )
        self.assertEqual(stale.status_code, 409)
        self.assertEqual(stale.json()["error"], "registrants_changed")
        self.assertFalse(
            OrganizationEventLottery.objects.filter(event_id=event_id).exists()
        )

        missing = self._run_lottery(event_id, winner_count=1, applicant_ids=[])
        self.assertEqual(missing.status_code, 409)
        self.assertEqual(missing.json()["error"], "registrants_changed")

        self.client.force_login(self.owner)
        no_ids = self._json(
            "post", self._event_url(f"{event_id}/lottery/"), winner_count=1
        )
        self.assertEqual(no_ids.status_code, 400)
        self.assertEqual(no_ids.json()["error"], "invalid_payload")

        unknown = self._run_lottery(
            event_id,
            winner_count=1,
            excluded=[{"user_id": self.other.pk, "note": "不正"}],
        )
        self.assertEqual(unknown.status_code, 400)
        self.assertEqual(unknown.json()["error"], "invalid_excluded")

        self.client.force_login(self.owner)
        reopened = self._json(
            "patch", self._event_url(f"{event_id}/"), registration_open=True
        )
        self.assertEqual(reopened.status_code, 200, reopened.content)
        self._register(event_id, self.other)
        current = self._run_lottery(
            event_id, winner_count=1, applicant_ids=[self.student.pk]
        )
        self.assertEqual(current.status_code, 409)
        self.assertEqual(current.json()["error"], "registrants_changed")

    def test_mutating_paths_lock_event_row_first(self):
        from . import organization_event_lottery_services as lottery_services
        from . import organization_event_services as event_services

        with open(
            event_services._lock_event.__code__.co_filename, encoding="utf-8"
        ) as handle:
            event_src = handle.read()
        with open(
            lottery_services.run_organization_event_lottery.__code__.co_filename,
            encoding="utf-8",
        ) as handle:
            lottery_src = handle.read()
        for name in (
            "def update_organization_event",
            "def publish_organization_event",
            "def unpublish_organization_event",
            "def cancel_organization_event",
            "def delete_organization_event",
            "def register_organization_event",
            "def unregister_organization_event",
        ):
            idx = event_src.index(name)
            snippet = event_src[idx : idx + 1600]
            self.assertIn("_lock_event(", snippet, name)
        register_snip = event_src[
            event_src.index("def register_organization_event") : event_src.index(
                "def unregister_organization_event"
            )
        ]
        self.assertLess(
            register_snip.index("_lock_event("),
            register_snip.index("OrganizationEventRegistration.objects.select_for_update"),
        )
        unregister_snip = event_src[event_src.index("def unregister_organization_event") :]
        self.assertLess(
            unregister_snip.index("_lock_event("),
            unregister_snip.index("OrganizationEventRegistration.objects.select_for_update"),
        )
        run_snip = lottery_src[
            lottery_src.index("def run_organization_event_lottery") : lottery_src.index(
                "def share_organization_event_lottery"
            )
        ]
        self.assertIn("_lock_event(", run_snip)
        self.assertLess(
            run_snip.index("_lock_event("),
            run_snip.index("select_for_update"),
        )
        self.assertIn("share_organization_event_to_chat", lottery_src)
        share_src = Path("app/organization_event_services.py").read_text()
        share_snip = share_src[
            share_src.index("def share_organization_event_to_chat") :
        ][:1800]
        self.assertIn("select_for_update", share_snip)
        self.assertIn("applicant_ids", lottery_src)
        self.assertIn("registrants_changed", lottery_src)
        self.assertIn("lottery_closed", event_src)
        self.assertIn("can_reopen_registration", event_src)
        self.assertIn("transaction.on_commit", event_src)

    def test_pending_invitee_cannot_read_lottery_lists_or_share_card(self):
        from .organization_recruiting_invite_services import create_recruiting_invitations

        event_id = self._create_published_event()
        self._register(event_id, self.student)
        chat = create_recruiting_chat(
            organization=self.org, actor=self.owner, name="2026新歓"
        )
        invited = create_recruiting_invitations(
            chat=chat, actor=self.owner, invitee_ids=[self.third.pk]
        )
        self.assertTrue(invited["invited"])
        drawn = self._run_lottery(event_id, winner_count=1)
        self.assertEqual(drawn.status_code, 201, drawn.content)
        self.client.force_login(self.owner)
        shared = self._json("post", self._event_url(f"{event_id}/lottery/share/"))
        self.assertEqual(shared.status_code, 200, shared.content)

        self.client.force_login(self.third)
        lists = self.client.get(self._event_url(f"{event_id}/lottery/"))
        self.assertEqual(lists.status_code, 403)
        messages = self.client.get(f"/api/v1/recruiting-chats/{chat.room_id}/messages/")
        self.assertIn(messages.status_code, {403, 404})
        chat_payload = self.client.get(
            f"/api/v1/organizations/{self.org.slug}/recruiting-chat/"
        )
        self.assertEqual(chat_payload.status_code, 200, chat_payload.content)
        self.assertIsNone(chat_payload.json()["recruiting_chat"].get("room_id"))
