"""Phase 6 timetable JSON API tests (reuse /api/timetable/*)."""

from __future__ import annotations

import json

from django.test import Client, TestCase, override_settings

from .models import User, UserProfile


@override_settings(BROWSE_MODE_GATE_ENABLED=False)
class TimetableApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="tt-api@waseda.jp",
            password="test-pass-12345",
        )
        self.other = User.objects.create_user(
            email="tt-other@waseda.jp",
            password="test-pass-12345",
        )
        UserProfile.objects.update_or_create(
            user=self.user,
            defaults={"name": "本人", "is_timetable_public": False},
        )
        UserProfile.objects.update_or_create(
            user=self.other,
            defaults={"name": "他人", "is_timetable_public": False},
        )
        self.client = Client()

    def test_slots_includes_visibility_and_upsert(self):
        self.client.force_login(self.user)
        listed = self.client.get("/api/timetable/slots/")
        self.assertEqual(listed.status_code, 200)
        data = listed.json()
        self.assertIn("slots", data)
        self.assertFalse(data["is_timetable_public"])

        saved = self.client.post(
            "/api/timetable/slot/",
            data=json.dumps(
                {
                    "slot_key": "p2-d1",
                    "name": "ミクロ経済学",
                    "room": "3-201",
                    "credits": "2",
                    "memo": "予習",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(saved.status_code, 200)
        self.assertTrue(saved.json()["ok"])
        self.assertEqual(saved.json()["entry"]["name"], "ミクロ経済学")

        listed2 = self.client.get("/api/timetable/slots/")
        self.assertEqual(listed2.json()["slots"]["p2-d1"]["room"], "3-201")

        cleared = self.client.post(
            "/api/timetable/slot/",
            data=json.dumps(
                {
                    "slot_key": "p2-d1",
                    "name": "",
                    "room": "",
                    "credits": "",
                    "memo": "",
                }
            ),
            content_type="application/json",
        )
        self.assertTrue(cleared.json()["deleted"])
        self.assertNotIn("p2-d1", self.client.get("/api/timetable/slots/").json()["slots"])

    def test_visibility_and_public_user_slots(self):
        self.client.force_login(self.other)
        private = self.client.get(f"/api/timetable/user/{self.other.pk}/")
        # owner can always read own
        self.assertEqual(private.status_code, 200)

        self.client.force_login(self.user)
        forbidden = self.client.get(f"/api/timetable/user/{self.other.pk}/")
        self.assertEqual(forbidden.status_code, 404)

        self.client.force_login(self.other)
        toggled = self.client.post(
            "/api/timetable/visibility/",
            data=json.dumps({"is_public": True}),
            content_type="application/json",
        )
        self.assertTrue(toggled.json()["is_timetable_public"])

        self.client.force_login(self.user)
        public = self.client.get(f"/api/timetable/user/{self.other.pk}/")
        self.assertEqual(public.status_code, 200)
        payload = public.json()
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["read_only"])
        self.assertEqual(payload["owner"]["id"], self.other.pk)
