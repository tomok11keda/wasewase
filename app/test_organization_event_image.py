"""Public event image upload, access control, and live timeline cards."""

from __future__ import annotations

import json

from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.test.client import BOUNDARY, MULTIPART_CONTENT, encode_multipart
from django.utils import timezone
from datetime import timedelta

from .models import (
    Organization,
    OrganizationEvent,
    OrganizationMember,
    TimelinePost,
    User,
    UserProfile,
)
from .organization_services import add_organization_member

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


def _gif(name: str = "event.gif") -> SimpleUploadedFile:
    return SimpleUploadedFile(name, _MINIMAL_GIF, content_type="image/gif")


@override_settings(BROWSE_MODE_GATE_ENABLED=False)
class OrganizationEventImageTests(TestCase):
    def setUp(self):
        cache.clear()
        self.owner = _make_user("img-owner@waseda.jp", username="imgowner")
        self.student = _make_user("img-student@waseda.jp", username="imgstudent")
        self.org = Organization.objects.create(
            name="画像団体",
            slug="image-org",
            status=Organization.Status.ACTIVE,
            is_listed=True,
        )
        add_organization_member(
            self.org, self.owner, role=OrganizationMember.Role.OWNER
        )
        self.client = Client()
        now = timezone.now()
        self.starts = (now + timedelta(days=7)).isoformat()
        self.ends = (now + timedelta(days=7, hours=2)).isoformat()

    def tearDown(self):
        cache.clear()

    def _url(self, suffix: str = "") -> str:
        return f"/api/v1/organizations/{self.org.slug}/events/{suffix}"

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

    def _event_fields(self, **overrides) -> dict:
        data = {
            "title": "画像イベント",
            "description": "紹介",
            "starts_at": self.starts,
            "ends_at": self.ends,
            "venue_name": "大隈講堂",
        }
        data.update(overrides)
        return data

    def test_create_without_image_still_works(self):
        self.client.force_login(self.owner)
        created = self._json("post", self._url(), **self._event_fields())
        self.assertEqual(created.status_code, 201, created.content)
        self.assertEqual(created.json()["event"]["image_url"], "")
        event = OrganizationEvent.objects.get(pk=created.json()["event"]["id"])
        self.assertFalse(event.image)

    def test_multipart_create_and_edit_and_clear_image(self):
        self.client.force_login(self.owner)
        created = self.client.post(
            self._url(),
            data={**self._event_fields(), "image": _gif("first.gif")},
        )
        self.assertEqual(created.status_code, 201, created.content)
        event_id = created.json()["event"]["id"]
        first_url = created.json()["event"]["image_url"]
        self.assertTrue(first_url)
        event = OrganizationEvent.objects.get(pk=event_id)
        self.assertTrue(event.image)

        updated = self.client.patch(
            self._url(f"{event_id}/"),
            data=encode_multipart(BOUNDARY, {"image": _gif("second.gif")}),
            content_type=MULTIPART_CONTENT,
        )
        self.assertEqual(updated.status_code, 200, updated.content)
        second_url = updated.json()["event"]["image_url"]
        self.assertTrue(second_url)
        self.assertNotEqual(second_url, first_url)

        cleared = self.client.patch(
            self._url(f"{event_id}/"),
            data=encode_multipart(BOUNDARY, {"clear_image": "true"}),
            content_type=MULTIPART_CONTENT,
        )
        self.assertEqual(cleared.status_code, 200, cleared.content)
        self.assertEqual(cleared.json()["event"]["image_url"], "")
        event.refresh_from_db()
        self.assertFalse(event.image)

    def test_invalid_and_huge_files_are_rejected_without_losing_old_image(self):
        self.client.force_login(self.owner)
        created = self.client.post(
            self._url(),
            data={**self._event_fields(), "image": _gif("keep.gif")},
        )
        self.assertEqual(created.status_code, 201, created.content)
        event_id = created.json()["event"]["id"]
        kept = created.json()["event"]["image_url"]

        bad = self.client.patch(
            self._url(f"{event_id}/"),
            data=encode_multipart(
                BOUNDARY,
                {
                    "image": SimpleUploadedFile(
                        "notes.txt", b"not-an-image", content_type="text/plain"
                    )
                },
            ),
            content_type=MULTIPART_CONTENT,
        )
        self.assertEqual(bad.status_code, 400)
        self.assertEqual(bad.json()["error"], "invalid_payload")
        self.assertIn("image", bad.json()["errors"])
        event = OrganizationEvent.objects.get(pk=event_id)
        self.assertTrue(event.image)
        self.assertEqual(event.image.url, kept)

        huge = self.client.patch(
            self._url(f"{event_id}/"),
            data=encode_multipart(
                BOUNDARY,
                {
                    "image": SimpleUploadedFile(
                        "huge.jpg",
                        b"x" * (5 * 1024 * 1024 + 10),
                        content_type="image/jpeg",
                    )
                },
            ),
            content_type=MULTIPART_CONTENT,
        )
        self.assertEqual(huge.status_code, 400)
        self.assertIn("image", huge.json()["errors"])
        event.refresh_from_db()
        self.assertTrue(event.image)

        json_image = self._json("patch", self._url(f"{event_id}/"), image="https://evil")
        self.assertEqual(json_image.status_code, 400)
        event.refresh_from_db()
        self.assertTrue(event.image)

    def test_draft_image_is_not_leaked_and_live_card_shows_it(self):
        self.client.force_login(self.owner)
        created = self.client.post(
            self._url(),
            data={**self._event_fields(), "image": _gif()},
        )
        self.assertEqual(created.status_code, 201, created.content)
        event_id = created.json()["event"]["id"]
        image_url = created.json()["event"]["image_url"]
        self.assertTrue(image_url)

        self.client.force_login(self.student)
        hidden = self.client.get(self._url(f"{event_id}/"))
        self.assertEqual(hidden.status_code, 404)
        self.assertNotIn(image_url, hidden.content.decode("utf-8", "replace"))

        self.client.force_login(self.owner)
        published = self._json("post", self._url(f"{event_id}/publish/"))
        self.assertEqual(published.status_code, 200, published.content)
        shared = self._json("post", self._url(f"{event_id}/timeline-share/"), body="告知")
        self.assertEqual(shared.status_code, 201, shared.content)
        post_id = shared.json()["post_id"]
        self.assertEqual(
            shared.json()["shared_organization_event"]["image_url"], image_url
        )

        self.client.force_login(self.student)
        detail = self.client.get(self._url(f"{event_id}/"))
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()["event"]["image_url"], image_url)
        feed = self.client.get("/api/v1/timeline/", {"sort": "latest"})
        row = next(item for item in feed.json()["posts"] if item["id"] == post_id)
        self.assertEqual(row["shared_organization_event"]["image_url"], image_url)

        self.client.force_login(self.owner)
        unpublished = self._json("post", self._url(f"{event_id}/unpublish/"))
        self.assertEqual(unpublished.status_code, 200, unpublished.content)
        self.client.force_login(self.student)
        student_hidden = self.client.get(f"/api/v1/timeline/{post_id}/")
        self.assertEqual(student_hidden.status_code, 404)
        feed_hidden = self.client.get("/api/v1/timeline/", {"sort": "latest"})
        self.assertFalse(
            any(item["id"] == post_id for item in feed_hidden.json()["posts"])
        )

    def test_student_cannot_upload_or_share(self):
        self.client.force_login(self.owner)
        created = self._json("post", self._url(), **self._event_fields())
        event_id = created.json()["event"]["id"]
        self._json("post", self._url(f"{event_id}/publish/"))
        self.client.force_login(self.student)
        upload = self.client.patch(
            self._url(f"{event_id}/"),
            data=encode_multipart(BOUNDARY, {"image": _gif()}),
            content_type=MULTIPART_CONTENT,
        )
        self.assertEqual(upload.status_code, 403)
        share = self._json("post", self._url(f"{event_id}/timeline-share/"))
        self.assertEqual(share.status_code, 403)
        self.assertFalse(TimelinePost.objects.filter(shared_organization_event_id=event_id).exists())
