"""仮名称で作った団体を owner が改名し、公開面へ新しい名前が載る流れ。"""

from __future__ import annotations

import json
from datetime import timedelta

from django.contrib.admin.models import CHANGE, LogEntry
from django.contrib.contenttypes.models import ContentType
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.test.client import BOUNDARY, MULTIPART_CONTENT, encode_multipart
from django.urls import reverse
from django.utils import timezone

from .models import Organization, OrganizationMember, ProfileLink, TimelinePost
from .organization_services import (
    ORGANIZATION_NAME_TAKEN_MESSAGE,
    organization_name_change_message,
)
from .test_organization import _make_user, _org_staff, is_organization_owner

_MINIMAL_GIF = (
    b"GIF89a\x01\x00\x01\x00\x80\x00\x00\xff\xff\xff\x00\x00\x00!\xf9\x04"
    b"\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"
)

PROVISIONAL_NAME = "仮称アルファ"
SLUG = "alpha-club"
NEW_NAME = "正式名称ベータ"
TAKEN_NAME = "衝突する団体名"


@override_settings(
    BROWSE_MODE_GATE_ENABLED=False,
    MEDIA_ROOT="/tmp/wasewase-org-name-test-media",
)
class OrganizationNameEditFlowTests(TestCase):
    def test_operator_creates_with_provisional_name_and_owner_finishes_profile(self):
        staff = _org_staff("flow-staff@waseda.jp")
        owner = _make_user("flow-owner@waseda.jp")
        admin = Client()
        admin.force_login(staff)

        add_page = admin.get(reverse("admin:app_organization_add"))
        self.assertEqual(add_page.status_code, 200)
        html = add_page.content.decode()
        self.assertIn('name="name"', html)
        self.assertIn('name="slug"', html)
        self.assertIn('name="status"', html)
        self.assertNotIn('name="description"', html)
        self.assertNotIn('name="category"', html)
        self.assertNotIn('name="is_listed"', html)
        self.assertNotIn('name="is_verified"', html)
        self.assertNotIn("profile_links-TOTAL_FORMS", html)

        created = admin.post(
            reverse("admin:app_organization_add"),
            {
                "name": PROVISIONAL_NAME,
                "slug": SLUG,
                "status": Organization.Status.DRAFT,
                "memberships-TOTAL_FORMS": "1",
                "memberships-INITIAL_FORMS": "0",
                "memberships-MIN_NUM_FORMS": "0",
                "memberships-MAX_NUM_FORMS": "1000",
                "memberships-0-user": str(owner.pk),
                "memberships-0-role": OrganizationMember.Role.OWNER,
                "_save": "保存",
            },
        )
        self.assertEqual(created.status_code, 302, created.content[:500])
        org = Organization.objects.get(slug=SLUG)
        self.assertEqual(org.name, PROVISIONAL_NAME)
        self.assertEqual(org.description, "")
        self.assertEqual(org.category, Organization.Category.OTHER)
        self.assertFalse(org.avatar)
        self.assertEqual(org.status, Organization.Status.ACTIVE)
        self.assertTrue(org.is_listed)
        self.assertFalse(org.is_verified)
        self.assertTrue(is_organization_owner(owner, org))
        self.assertFalse(ProfileLink.objects.filter(organization=org).exists())

        other = Organization.objects.create(
            name=TAKEN_NAME,
            slug="taken-club",
            status=Organization.Status.ACTIVE,
            is_listed=True,
        )

        owner_client = Client()
        owner_client.force_login(owner)
        image = SimpleUploadedFile("icon.gif", _MINIMAL_GIF, content_type="image/gif")
        saved = owner_client.patch(
            f"/api/v1/organizations/{SLUG}/",
            data=encode_multipart(
                BOUNDARY,
                {
                    "name": NEW_NAME,
                    "description": "紹介文です",
                    "category": Organization.Category.CIRCLE,
                    "links": json.dumps(
                        [{"title": "公式サイト", "url": "https://alpha.example/"}]
                    ),
                    "avatar": image,
                },
            ),
            content_type=MULTIPART_CONTENT,
        )
        self.assertEqual(saved.status_code, 200, saved.content)
        body = saved.json()["organization"]
        self.assertEqual(body["name"], NEW_NAME)
        self.assertEqual(body["slug"], SLUG)
        self.assertEqual(body["description"], "紹介文です")
        self.assertTrue(body["avatar_url"])
        self.assertEqual(body["links"][0]["url"], "https://alpha.example/")
        org.refresh_from_db()
        self.assertEqual(org.slug, SLUG)
        self.assertEqual(org.name, NEW_NAME)
        profile = owner_client.get(f"/api/v1/organizations/{SLUG}/")
        self.assertEqual(profile.status_code, 200)
        self.assertEqual(profile.json()["organization"]["name"], NEW_NAME)
        self.assertEqual(profile.json()["organization"]["slug"], SLUG)

        duplicate = owner_client.patch(
            f"/api/v1/organizations/{SLUG}/",
            data=json.dumps({"name": f"  {TAKEN_NAME}  "}),
            content_type="application/json",
        )
        self.assertEqual(duplicate.status_code, 400, duplicate.content)
        self.assertEqual(
            duplicate.json()["errors"]["name"],
            [ORGANIZATION_NAME_TAKEN_MESSAGE],
        )
        org.refresh_from_db()
        self.assertEqual(org.name, NEW_NAME)
        self.assertEqual(org.slug, SLUG)
        self.assertFalse(
            LogEntry.objects.filter(
                object_id=str(org.pk),
                change_message__contains=TAKEN_NAME,
            ).exists()
        )

        content_type = ContentType.objects.get_for_model(Organization)
        entry = LogEntry.objects.get(
            content_type=content_type,
            object_id=str(org.pk),
            action_flag=CHANGE,
            user_id=owner.pk,
        )
        self.assertEqual(
            entry.change_message,
            organization_name_change_message(PROVISIONAL_NAME, NEW_NAME),
        )
        history = admin.get(reverse("admin:app_organization_history", args=[org.pk]))
        self.assertEqual(history.status_code, 200)
        self.assertContains(history, PROVISIONAL_NAME)
        self.assertContains(history, NEW_NAME)

        post = owner_client.post(
            "/api/v1/timeline/",
            {
                "body": "本日の練習メニュー",
                "organization_id": str(org.pk),
                "visibility": "public",
            },
        )
        self.assertEqual(post.status_code, 201, post.content)
        post_id = post.json()["post"]["id"]
        starts = timezone.now() + timedelta(days=3)
        event = owner_client.post(
            f"/api/v1/organizations/{SLUG}/events/",
            data=json.dumps(
                {
                    "title": "新歓説明会",
                    "description": "サークル紹介",
                    "starts_at": starts.isoformat(),
                    "ends_at": (starts + timedelta(hours=2)).isoformat(),
                    "venue_name": "大隈講堂",
                    "venue_address": "早稲田",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(event.status_code, 201, event.content)
        event_id = event.json()["event"]["id"]
        published = owner_client.post(
            f"/api/v1/organizations/{SLUG}/events/{event_id}/publish/"
        )
        self.assertEqual(published.status_code, 200, published.content)
        chat = owner_client.post(
            f"/api/v1/organizations/{SLUG}/recruiting-chat/",
            data=json.dumps({"name": "新歓チャット", "description": "質問はこちら"}),
            content_type="application/json",
        )
        self.assertEqual(chat.status_code, 201, chat.content)
        room_id = chat.json()["recruiting_chat"]["room_id"]

        renamed_again = "公開後の名前ガンマ"
        renamed = owner_client.patch(
            f"/api/v1/organizations/{SLUG}/",
            data=json.dumps({"name": renamed_again}),
            content_type="application/json",
        )
        self.assertEqual(renamed.status_code, 200, renamed.content)
        org.refresh_from_db()
        self.assertEqual(org.name, renamed_again)
        self.assertEqual(org.slug, SLUG)

        search = owner_client.get(
            "/api/v1/search/", {"q": renamed_again, "tab": "all"}
        )
        self.assertEqual(search.status_code, 200)
        org_rows = search.json()["organizations"]
        self.assertTrue(any(row["slug"] == SLUG and row["name"] == renamed_again for row in org_rows))
        old_search = owner_client.get(
            "/api/v1/search/", {"q": PROVISIONAL_NAME, "tab": "all"}
        )
        self.assertFalse(
            any(row["slug"] == SLUG for row in old_search.json()["organizations"])
        )
        post_search = owner_client.get(
            "/api/v1/search/", {"q": "本日の練習メニュー", "tab": "posts"}
        )
        posts = post_search.json()["posts"]
        matched = next(item for item in posts if item["id"] == post_id)
        self.assertEqual(matched["organization"]["name"], renamed_again)
        self.assertEqual(matched["organization"]["slug"], SLUG)

        timeline = owner_client.get("/api/v1/timeline/")
        listed = next(
            item for item in timeline.json()["posts"] if item["id"] == post_id
        )
        self.assertEqual(listed["organization"]["name"], renamed_again)
        self.assertEqual(listed["organization"]["slug"], SLUG)

        event_detail = owner_client.get(
            f"/api/v1/organizations/{SLUG}/events/{event_id}/"
        )
        self.assertEqual(event_detail.status_code, 200)
        self.assertEqual(event_detail.json()["event"]["organization_name"], renamed_again)
        self.assertEqual(event_detail.json()["event"]["organization_slug"], SLUG)

        room = owner_client.get(f"/api/v1/recruiting-chats/{room_id}/")
        self.assertEqual(room.status_code, 200, room.content)
        self.assertEqual(room.json()["room"]["organization_name"], renamed_again)
        self.assertEqual(room.json()["room"]["organization_slug"], SLUG)

        self.assertTrue(other.pk)
        self.assertEqual(
            TimelinePost.objects.get(pk=post_id).organization.slug,
            SLUG,
        )
