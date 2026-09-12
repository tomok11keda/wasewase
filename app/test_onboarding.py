"""Post-OTP onboarding API tests."""

from __future__ import annotations

import json

from django.test import Client, TestCase, override_settings
from django.utils import timezone

from .models import Follow, User, UserProfile
from .ugc_services import block_user


def _json(payload: dict) -> dict:
    return {
        "data": json.dumps(payload),
        "content_type": "application/json",
    }


@override_settings(BROWSE_MODE_GATE_ENABLED=False)
class OnboardingApiTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            email="onboard@waseda.jp",
            password="test-pass-12345",
            username="user_abcd1234",
        )
        self.profile = UserProfile.objects.create(user=self.user, name="", department="")
        self.client.force_login(self.user)

        self.same = User.objects.create_user(
            email="same-fac@waseda.jp",
            password="test-pass-12345",
            username="same_fac",
        )
        UserProfile.objects.create(
            user=self.same,
            name="同学部",
            department="商学部",
            onboarding_completed_at=timezone.now(),
        )
        self.other = User.objects.create_user(
            email="other-fac@waseda.jp",
            password="test-pass-12345",
            username="other_fac",
        )
        UserProfile.objects.create(
            user=self.other,
            name="他学部",
            department="法学部",
            onboarding_completed_at=timezone.now(),
        )
        self.private = User.objects.create_user(
            email="priv@waseda.jp",
            password="test-pass-12345",
            username="priv_user",
        )
        UserProfile.objects.create(
            user=self.private,
            name="非公開",
            department="商学部",
            is_private=True,
            onboarding_completed_at=timezone.now(),
        )
        self.staff = User.objects.create_user(
            email="staff@waseda.jp",
            password="test-pass-12345",
            username="staff_user",
            is_staff=True,
        )
        UserProfile.objects.create(
            user=self.staff,
            name="スタッフ",
            department="商学部",
            onboarding_completed_at=timezone.now(),
        )
        self.blocked = User.objects.create_user(
            email="blocked@waseda.jp",
            password="test-pass-12345",
            username="blocked_u",
        )
        UserProfile.objects.create(
            user=self.blocked,
            name="ブロック",
            department="商学部",
            onboarding_completed_at=timezone.now(),
        )
        block_user(self.user, self.blocked)

    def test_me_requires_onboarding_and_hides_placeholder_username(self):
        res = self.client.get("/api/v1/me/")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data["onboarding_required"])
        self.assertEqual(data["onboarding_step"], "profile")
        self.assertEqual(data["user"]["username"], "")
        self.assertNotIn("user_abcd1234", json.dumps(data["user"]))

    def test_staff_skips_onboarding(self):
        staff_client = Client()
        staff_client.force_login(self.staff)
        res = staff_client.get("/api/v1/me/")
        self.assertFalse(res.json()["onboarding_required"])

    def test_profile_validation(self):
        res = self.client.post("/api/v1/onboarding/profile/", **_json({}))
        self.assertEqual(res.status_code, 400)
        self.assertIn("name", res.json()["errors"])
        keep = self.client.post(
            "/api/v1/onboarding/profile/",
            **_json(
                {
                    "name": "太郎",
                    "username": "user_abcd1234",
                    "department": "商学部",
                }
            ),
        )
        self.assertEqual(keep.status_code, 400)
        self.assertIn("username", keep.json()["errors"])

    def test_profile_rejects_duplicate_and_placeholder_then_saves(self):
        taken = self.client.post(
            "/api/v1/onboarding/profile/",
            **_json(
                {
                    "name": "太郎",
                    "username": "same_fac",
                    "department": "商学部",
                }
            ),
        )
        self.assertEqual(taken.status_code, 400)
        ok = self.client.post(
            "/api/v1/onboarding/profile/",
            **_json(
                {
                    "name": "太郎",
                    "username": "taro_onboard",
                    "department": "商学部",
                }
            ),
        )
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(ok.json()["step"], "follow")
        self.user.refresh_from_db()
        self.profile.refresh_from_db()
        self.assertEqual(self.user.username, "taro_onboard")
        self.assertEqual(self.profile.name, "太郎")
        self.assertEqual(self.profile.department, "商学部")

    def test_complete_before_profile_rejected(self):
        res = self.client.post("/api/v1/onboarding/complete/", **_json({}))
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["error"], "not_ready")

    def _make_candidate(
        self,
        *,
        email: str,
        username: str,
        name: str,
        department: str = "商学部",
        step: str = UserProfile.ONBOARDING_STEP_PROFILE,
        completed: bool = False,
        is_private: bool = False,
    ) -> User:
        user = User.objects.create_user(
            email=email,
            password="test-pass-12345",
            username=username,
        )
        UserProfile.objects.create(
            user=user,
            name=name,
            department=department,
            is_private=is_private,
            onboarding_step=step,
            onboarding_completed_at=timezone.now() if completed else None,
        )
        return user

    def _suggestion_ids(self) -> list[int]:
        self.client.post(
            "/api/v1/onboarding/profile/",
            **_json(
                {
                    "name": "太郎",
                    "username": "taro_onboard",
                    "department": "商学部",
                }
            ),
        )
        res = self.client.get("/api/v1/onboarding/suggestions/")
        self.assertEqual(res.status_code, 200)
        return [row["id"] for row in res.json()["users"]]

    def test_suggestions_exclude_self_staff_private_blocked(self):
        self.client.post(
            "/api/v1/onboarding/profile/",
            **_json(
                {
                    "name": "太郎",
                    "username": "taro_onboard",
                    "department": "商学部",
                }
            ),
        )
        res = self.client.get("/api/v1/onboarding/suggestions/")
        self.assertEqual(res.status_code, 200)
        ids = [row["id"] for row in res.json()["users"]]
        self.assertNotIn(self.user.pk, ids)
        self.assertNotIn(self.staff.pk, ids)
        self.assertNotIn(self.private.pk, ids)
        self.assertNotIn(self.blocked.pk, ids)
        self.assertIn(self.same.pk, ids)
        blob = json.dumps(res.json())
        self.assertNotIn("@waseda.jp", blob)
        self.assertNotIn("email", res.json()["users"][0])

    def test_suggestions_require_profile_step_not_full_onboarding(self):
        profile_incomplete = self._make_candidate(
            email="profile-open@waseda.jp",
            username="still_profile",
            name="プロフィール未完了",
            step=UserProfile.ONBOARDING_STEP_PROFILE,
        )
        follow_step = self._make_candidate(
            email="follow-step@waseda.jp",
            username="in_follow",
            name="フォロー中",
            step=UserProfile.ONBOARDING_STEP_FOLLOW,
        )
        welcome_step = self._make_candidate(
            email="welcome-step@waseda.jp",
            username="in_welcome",
            name="歓迎中",
            step=UserProfile.ONBOARDING_STEP_WELCOME,
        )
        placeholder = self._make_candidate(
            email="placeholder@waseda.jp",
            username="user_deadbeef",
            name="仮ユーザー名",
            step=UserProfile.ONBOARDING_STEP_FOLLOW,
        )
        ids = self._suggestion_ids()
        self.assertNotIn(profile_incomplete.pk, ids)
        self.assertIn(follow_step.pk, ids)
        self.assertIn(welcome_step.pk, ids)
        self.assertIn(self.same.pk, ids)
        self.assertIn(self.other.pk, ids)
        self.assertNotIn(placeholder.pk, ids)

    def test_existing_user_prefill_and_skip_follow(self):
        existing = User.objects.create_user(
            email="existing@waseda.jp",
            password="test-pass-12345",
            username="existing_h",
        )
        UserProfile.objects.create(
            user=existing, name="既存", department="法学部"
        )
        c = Client()
        c.force_login(existing)
        status = c.get("/api/v1/onboarding/")
        self.assertEqual(status.status_code, 200)
        self.assertTrue(status.json()["required"])
        self.assertEqual(status.json()["profile"]["name"], "既存")
        self.assertEqual(status.json()["profile"]["username"], "existing_h")
        self.assertEqual(status.json()["profile"]["department"], "法学部")
        saved = c.post(
            "/api/v1/onboarding/profile/",
            **_json(
                {
                    "name": "既存",
                    "username": "existing_h",
                    "department": "法学部",
                }
            ),
        )
        self.assertEqual(saved.status_code, 200)
        skipped = c.post("/api/v1/onboarding/follow-step/", **_json({}))
        self.assertEqual(skipped.status_code, 200)
        self.assertEqual(skipped.json()["step"], "welcome")
        done = c.post("/api/v1/onboarding/complete/", **_json({}))
        self.assertEqual(done.status_code, 200)
        existing.profile.refresh_from_db()
        self.assertIsNotNone(existing.profile.onboarding_completed_at)
        me = c.get("/api/v1/me/")
        self.assertFalse(me.json()["onboarding_required"])

    def test_follow_toggle_reuses_existing_api(self):
        self.client.post(
            "/api/v1/onboarding/profile/",
            **_json(
                {
                    "name": "太郎",
                    "username": "taro_onboard",
                    "department": "商学部",
                }
            ),
        )
        follow = self.client.post(f"/api/v1/profile/{self.same.pk}/follow/")
        self.assertEqual(follow.status_code, 200)
        self.assertTrue(follow.json()["is_following"])
        self.assertTrue(
            Follow.objects.filter(follower=self.user, following=self.same).exists()
        )
        suggestions = self.client.get("/api/v1/onboarding/suggestions/")
        row = next(
            item
            for item in suggestions.json()["users"]
            if item["id"] == self.same.pk
        )
        self.assertTrue(row["is_following"])

    def test_anonymous_rejected(self):
        guest = Client()
        res = guest.get("/api/v1/onboarding/suggestions/")
        self.assertEqual(res.status_code, 401)
