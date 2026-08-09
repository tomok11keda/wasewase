"""Calendar event API tests."""

from __future__ import annotations

from datetime import date, time

from django.test import Client, TestCase, override_settings

from .models import CalendarEvent, TimetableSlot, User


@override_settings(BROWSE_MODE_GATE_ENABLED=False)
class CalendarEventApiTests(TestCase):
    def setUp(self):
        self.alice = User.objects.create_user(
            email="cal-alice@waseda.jp",
            password="test-pass-12345",
            username="calalice",
        )
        self.bob = User.objects.create_user(
            email="cal-bob@waseda.jp",
            password="test-pass-12345",
            username="calbob",
        )
        self.client = Client()

    def test_create_list_update_delete_own_events(self):
        self.client.force_login(self.alice)
        created = self.client.post(
            "/api/v1/calendar/events/create/",
            data={
                "title": "レポート提出",
                "date": "2026-08-10",
                "start_time": "18:00",
                "end_time": "19:00",
                "memo": "Moodle",
                "category": "assignment",
            },
            content_type="application/json",
        )
        self.assertEqual(created.status_code, 201)
        event_id = created.json()["event"]["id"]
        self.assertEqual(created.json()["event"]["category_label"], "課題")

        month = self.client.get(
            "/api/v1/calendar/events/?year=2026&month=8"
        ).json()
        self.assertTrue(month["ok"])
        self.assertEqual(month["dots"]["2026-08-10"]["count"], 1)
        self.assertEqual(len(month["by_date"]["2026-08-10"]), 1)

        updated = self.client.post(
            f"/api/v1/calendar/events/{event_id}/",
            data={"title": "レポート提出（延長）", "date": "2026-08-10"},
            content_type="application/json",
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["event"]["title"], "レポート提出（延長）")

        deleted = self.client.post(
            f"/api/v1/calendar/events/{event_id}/delete/",
            content_type="application/json",
        )
        self.assertEqual(deleted.status_code, 200)
        self.assertFalse(CalendarEvent.objects.filter(pk=event_id).exists())

    def test_cannot_see_other_users_events(self):
        CalendarEvent.objects.create(
            user=self.alice,
            title="秘密の予定",
            date=date(2026, 8, 12),
            start_time=time(10, 0),
            category=CalendarEvent.Category.OTHER,
        )
        self.client.force_login(self.bob)
        month = self.client.get(
            "/api/v1/calendar/events/?year=2026&month=8"
        ).json()
        self.assertEqual(month["events"], [])
        self.assertEqual(month["dots"], {})

    def test_requires_login(self):
        res = self.client.get("/api/v1/calendar/events/?year=2026&month=8")
        self.assertIn(res.status_code, (302, 401, 403))
