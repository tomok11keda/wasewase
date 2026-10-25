"""GET/PATCH /api/v1/me/profile/ — SPA own-profile edit."""

from __future__ import annotations

import json

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.test.client import BOUNDARY, MULTIPART_CONTENT, encode_multipart
from django.urls import reverse

from .models import User, UserProfile

_MINIMAL_GIF = (
    b"GIF89a\x01\x00\x01\x00\x80\x00\x00\xff\xff\xff\x00\x00\x00!\xf9\x04"
    b"\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"
)


def _make_user(email: str, **kwargs) -> User:
    kwargs.setdefault("password", "test-pass-12345")
    user = User.objects.create_user(email=email, **kwargs)
    UserProfile.objects.get_or_create(
        user=user,
        defaults={"name": kwargs.get("username") or email.split("@")[0]},
    )
    return user


@override_settings(BROWSE_MODE_GATE_ENABLED=False)
class MeProfileApiTests(TestCase):
    def setUp(self):
        self.user = _make_user("me-prof@waseda.jp", username="meprof")
        profile = self.user.profile
        profile.name = "表示名"
        profile.bio = "自己紹介です"
        profile.department = "商学部"
        profile.grade = "3年"
        profile.save()
        self.other = _make_user("me-other@waseda.jp", username="meother")
        self.client = Client()

    def _url(self) -> str:
        return "/api/v1/me/profile/"

    def _patch_json(self, **payload):
        return self.client.patch(
            self._url(),
            data=json.dumps(payload),
            content_type="application/json",
        )

    def test_unauthenticated_get_and_patch_are_401(self):
        guest = Client()
        get_res = guest.get(self._url())
        self.assertEqual(get_res.status_code, 401)
        self.assertEqual(get_res.json()["error"], "unauthorized")
        patch_res = guest.patch(
            self._url(),
            data=json.dumps({"name": "侵入"}),
            content_type="application/json",
        )
        self.assertEqual(patch_res.status_code, 401)
        self.assertEqual(patch_res.json()["error"], "unauthorized")

    def test_get_returns_own_editable_fields_without_email(self):
        self.client.force_login(self.user)
        res = self.client.get(self._url())
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data["ok"])
        profile = data["profile"]
        self.assertEqual(profile["id"], self.user.pk)
        self.assertEqual(profile["username"], "meprof")
        self.assertEqual(profile["name"], "表示名")
        self.assertEqual(profile["bio"], "自己紹介です")
        self.assertEqual(profile["department"], "商学部")
        self.assertEqual(profile["grade"], "3年")
        self.assertIn("avatar_url", profile)
        self.assertIn("department", data["choices"])
        self.assertIn("grade", data["choices"])
        blob = str(data)
        self.assertNotIn("me-prof@waseda.jp", blob)
        self.assertNotIn("email", profile)

    def test_patch_updates_each_text_field(self):
        self.client.force_login(self.user)
        res = self._patch_json(
            name="新しい名前",
            bio="新しい自己紹介",
            user_id="new_handle",
            department="法学部",
            grade="4年",
        )
        self.assertEqual(res.status_code, 200, res.content)
        profile = res.json()["profile"]
        self.assertEqual(profile["name"], "新しい名前")
        self.assertEqual(profile["bio"], "新しい自己紹介")
        self.assertEqual(profile["username"], "new_handle")
        self.assertEqual(profile["department"], "法学部")
        self.assertEqual(profile["grade"], "4年")
        self.user.refresh_from_db()
        self.assertEqual(self.user.username, "new_handle")
        stored = UserProfile.objects.get(user=self.user)
        self.assertEqual(stored.name, "新しい名前")
        self.assertEqual(stored.bio, "新しい自己紹介")

    def test_partial_patch_does_not_clear_omitted_fields(self):
        self.client.force_login(self.user)
        res = self._patch_json(name="名前だけ")
        self.assertEqual(res.status_code, 200)
        profile = res.json()["profile"]
        self.assertEqual(profile["name"], "名前だけ")
        self.assertEqual(profile["bio"], "自己紹介です")
        self.assertEqual(profile["username"], "meprof")
        self.assertEqual(profile["department"], "商学部")
        self.assertEqual(profile["grade"], "3年")

    def test_username_alias_and_duplicate_rejected(self):
        self.client.force_login(self.user)
        ok = self._patch_json(username="alias_ok")
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(ok.json()["profile"]["username"], "alias_ok")
        taken = self._patch_json(user_id="meother")
        self.assertEqual(taken.status_code, 400)
        self.assertEqual(taken.json()["error"], "validation")
        self.assertIn("user_id", taken.json()["errors"])
        self.user.refresh_from_db()
        self.assertEqual(self.user.username, "alias_ok")

    def test_invalid_faculty_and_short_handle(self):
        self.client.force_login(self.user)
        faculty = self._patch_json(department="存在しない学部")
        self.assertEqual(faculty.status_code, 400)
        self.assertIn("department", faculty.json()["errors"])
        handle = self._patch_json(user_id="ab")
        self.assertEqual(handle.status_code, 400)
        self.assertIn("user_id", handle.json()["errors"])
        stored = UserProfile.objects.get(user=self.user)
        self.assertEqual(stored.department, "商学部")

    def test_json_avatar_rejected_and_multipart_accepted(self):
        self.client.force_login(self.user)
        json_avatar = self._patch_json(avatar="https://evil.example/x.png")
        self.assertEqual(json_avatar.status_code, 400)
        self.assertIn("avatar", json_avatar.json()["errors"])
        image = SimpleUploadedFile("me.gif", _MINIMAL_GIF, content_type="image/gif")
        res = self.client.patch(
            self._url(),
            data=encode_multipart(
                BOUNDARY, {"name": "画像付き", "avatar": image}
            ),
            content_type=MULTIPART_CONTENT,
        )
        self.assertEqual(res.status_code, 200, res.content)
        stored = UserProfile.objects.get(user=self.user)
        self.assertEqual(stored.name, "画像付き")
        self.assertTrue(stored.avatar)
        self.assertTrue(res.json()["profile"]["avatar_url"])

    def test_invalid_image_is_rejected_without_clearing_fields(self):
        self.client.force_login(self.user)
        bad = SimpleUploadedFile(
            "notes.txt", b"not-an-image", content_type="text/plain"
        )
        res = self.client.patch(
            self._url(),
            data=encode_multipart(BOUNDARY, {"avatar": bad}),
            content_type=MULTIPART_CONTENT,
        )
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["error"], "validation")
        self.assertIn("avatar", res.json()["errors"])
        stored = UserProfile.objects.get(user=self.user)
        self.assertEqual(stored.bio, "自己紹介です")
        self.assertFalse(stored.avatar)

    def test_csrf_failure_returns_json(self):
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.user)
        res = csrf_client.patch(
            self._url(),
            data=json.dumps({"name": "CSRF欠落"}),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.json()["error"], "csrf_failed")
        stored = UserProfile.objects.get(user=self.user)
        self.assertEqual(stored.name, "表示名")

    def test_forbidden_and_unknown_fields(self):
        self.client.force_login(self.user)
        email = self._patch_json(email="hack@waseda.jp")
        self.assertEqual(email.status_code, 400)
        self.assertEqual(email.json()["error"], "forbidden_field")
        private = self._patch_json(is_private=True)
        self.assertEqual(private.status_code, 400)
        self.assertEqual(private.json()["error"], "forbidden_field")
        unknown = self._patch_json(nickname="nope")
        self.assertEqual(unknown.status_code, 400)
        self.assertEqual(unknown.json()["error"], "unknown_field")
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "me-prof@waseda.jp")
        stored = UserProfile.objects.get(user=self.user)
        self.assertFalse(stored.is_private)

    def test_empty_patch_and_avatar_survive_partial_update(self):
        self.client.force_login(self.user)
        empty = self._patch_json()
        self.assertEqual(empty.status_code, 200)
        stored = UserProfile.objects.get(user=self.user)
        self.assertEqual(stored.name, "表示名")
        self.assertEqual(stored.bio, "自己紹介です")
        image = SimpleUploadedFile("keep.gif", _MINIMAL_GIF, content_type="image/gif")
        uploaded = self.client.patch(
            self._url(),
            data=encode_multipart(BOUNDARY, {"avatar": image}),
            content_type=MULTIPART_CONTENT,
        )
        self.assertEqual(uploaded.status_code, 200, uploaded.content)
        avatar_name = UserProfile.objects.get(user=self.user).avatar.name
        self.assertTrue(avatar_name)
        renamed = self._patch_json(name="画像は残す")
        self.assertEqual(renamed.status_code, 200)
        kept = UserProfile.objects.get(user=self.user)
        self.assertEqual(kept.name, "画像は残す")
        self.assertEqual(kept.avatar.name, avatar_name)
        self.assertEqual(kept.bio, "自己紹介です")

    def test_patch_only_updates_authenticated_user(self):
        self.client.force_login(self.other)
        res = self._patch_json(name="他人名義")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["profile"]["id"], self.other.pk)
        stored = UserProfile.objects.get(user=self.user)
        self.assertEqual(stored.name, "表示名")

    def test_invalid_patch_after_avatar_does_not_partially_save(self):
        self.client.force_login(self.user)
        image = SimpleUploadedFile("keep.gif", _MINIMAL_GIF, content_type="image/gif")
        uploaded = self.client.patch(
            self._url(),
            data=encode_multipart(BOUNDARY, {"avatar": image}),
            content_type=MULTIPART_CONTENT,
        )
        self.assertEqual(uploaded.status_code, 200, uploaded.content)
        avatar_name = UserProfile.objects.get(user=self.user).avatar.name
        failed = self._patch_json(user_id="ab", name="失敗しても残す")
        self.assertEqual(failed.status_code, 400)
        stored = UserProfile.objects.get(user=self.user)
        self.assertEqual(stored.avatar.name, avatar_name)
        self.assertEqual(stored.name, "表示名")
        self.user.refresh_from_db()
        self.assertEqual(self.user.username, "meprof")

    def test_avatar_clear_checkbox_is_rejected_without_deleting(self):
        self.client.force_login(self.user)
        image = SimpleUploadedFile("keep.gif", _MINIMAL_GIF, content_type="image/gif")
        uploaded = self.client.patch(
            self._url(),
            data=encode_multipart(BOUNDARY, {"avatar": image}),
            content_type=MULTIPART_CONTENT,
        )
        self.assertEqual(uploaded.status_code, 200, uploaded.content)
        avatar_name = UserProfile.objects.get(user=self.user).avatar.name
        cleared = self.client.patch(
            self._url(),
            data=encode_multipart(BOUNDARY, {"avatar-clear": "on"}),
            content_type=MULTIPART_CONTENT,
        )
        self.assertEqual(cleared.status_code, 400)
        self.assertEqual(cleared.json()["error"], "unknown_field")
        stored = UserProfile.objects.get(user=self.user)
        self.assertEqual(stored.avatar.name, avatar_name)

    def test_classic_mypage_edit_still_works(self):
        self.client.force_login(self.user)
        res = self.client.post(
            reverse("mypage_edit"),
            {
                "name": "従来フォーム",
                "bio": "HTMLのまま",
                "user_id": "classic_ok",
                "department": "文学部",
                "grade": "2年",
            },
        )
        self.assertIn(res.status_code, (200, 302))
        stored = UserProfile.objects.get(user=self.user)
        self.assertEqual(stored.name, "従来フォーム")
        self.user.refresh_from_db()
        self.assertEqual(self.user.username, "classic_ok")
