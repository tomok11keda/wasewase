"""Phase 2-A: organization-named timeline posts. Must not leak operator User."""

from __future__ import annotations

import json
from unittest.mock import patch

from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from .models import (
    Comment,
    Follow,
    Notification,
    Organization,
    OrganizationMember,
    TimelinePost,
    User,
    UserProfile,
)
from .organization_post_services import ORG_PROFILE_POSTS_PAGE
from .organization_services import add_organization_member
from .search_api_services import search_home_posts
from .share_dm_services import require_shareable_target, serialize_timeline_share_content

_MINIMAL_GIF = (
    b"GIF89a\x01\x00\x01\x00\x80\x00\x00\xff\xff\xff\x00\x00\x00!\xf9\x04"
    b"\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"
)


def _make_user(email: str, **kwargs) -> User:
    kwargs.setdefault("password", "test-pass-12345")
    user = User.objects.create_user(email=email, **kwargs)
    UserProfile.objects.get_or_create(
        user=user,
        defaults={"name": email.split("@")[0]},
    )
    return user


def _make_org(**kwargs) -> Organization:
    kwargs.setdefault("name", "Circledancers")
    kwargs.setdefault("slug", "circledancers")
    kwargs.setdefault("status", Organization.Status.ACTIVE)
    kwargs.setdefault("is_listed", True)
    kwargs.setdefault("is_verified", True)
    return Organization.objects.create(**kwargs)


@override_settings(BROWSE_MODE_GATE_ENABLED=False, WASE_ORG_TIMELINE_POSTS_PUBLIC=False)
class OrganizationTimelinePostApiTests(TestCase):
    def setUp(self):
        self.owner = _make_user("org-owner@waseda.jp")
        self.admin = _make_user("org-admin@waseda.jp")
        self.member = _make_user("org-member@waseda.jp")
        self.outsider = _make_user("org-outsider@waseda.jp")
        self.other_owner = _make_user("other-owner@waseda.jp")
        self.org = _make_org(name="Circledancers", slug="circledancers")
        self.other_org = _make_org(name="Other Club", slug="other-club")
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
        self.personal = TimelinePost.objects.create(
            author=self.outsider,
            body="personal hello",
        )
        self.client = Client()
        cache.clear()

    def _create(self, user, body="org named post", **extra):
        self.client.force_login(user)
        return self.client.post("/api/v1/timeline/", {"body": body, **extra})

    def test_personal_post_json_stays_compatible(self):
        response = self._create(self.owner, body="just me", organization_id="")
        self.assertEqual(response.status_code, 201)
        post = response.json()["post"]
        self.assertNotIn("actor_type", post)
        self.assertNotIn("organization", post)
        self.assertEqual(post["author"]["id"], self.owner.pk)
        self.assertIn("is_operator_verified", post["author"])
        row = TimelinePost.objects.get(pk=post["id"])
        self.assertIsNone(row.organization_id)
        self.assertEqual(row.author_id, self.owner.pk)
        listed = self.client.get("/api/v1/timeline/").json()["posts"]
        self.assertTrue(any(item["id"] == post["id"] for item in listed))
        self.assertTrue(any(item["id"] == self.personal.pk for item in listed))

    def test_owner_can_create_organization_post(self):
        response = self._create(
            self.owner, organization_id=str(self.org.pk)
        )
        self.assertEqual(response.status_code, 201)
        payload = response.json()["post"]
        row = TimelinePost.objects.get(pk=payload["id"])
        self.assertEqual(row.author_id, self.owner.pk)
        self.assertEqual(row.organization_id, self.org.pk)
        self.assertEqual(payload["actor_type"], "organization")
        self.assertIsNone(payload["author"])
        self.assertEqual(payload["organization"]["id"], self.org.pk)
        self.assertEqual(payload["organization"]["name"], self.org.name)
        self.assertEqual(payload["organization"]["slug"], self.org.slug)
        self.assertTrue(payload["organization"]["is_verified"])
        self.assertNotIn("is_operator_verified", payload["organization"])
        self.assertEqual(payload["visibility"], "draft")
        self.assertEqual(
            row.organization_visibility, TimelinePost.OrganizationVisibility.DRAFT
        )

    def test_admin_can_create_organization_post(self):
        response = self._create(
            self.admin, body="admin org post", organization_id=str(self.org.pk)
        )
        self.assertEqual(response.status_code, 201)
        row = TimelinePost.objects.get(pk=response.json()["post"]["id"])
        self.assertEqual(row.author_id, self.admin.pk)
        self.assertEqual(row.organization_id, self.org.pk)

    def test_member_cannot_create_organization_post(self):
        response = self._create(self.member, organization_id=str(self.org.pk))
        self.assertEqual(response.status_code, 403)
        self.assertFalse(
            TimelinePost.objects.filter(organization=self.org, author=self.member).exists()
        )

    def test_other_organization_admin_cannot_post(self):
        response = self._create(
            self.other_owner, organization_id=str(self.org.pk)
        )
        self.assertEqual(response.status_code, 403)

    def test_suspended_organization_cannot_post(self):
        self.org.status = Organization.Status.SUSPENDED
        self.org.save(update_fields=["status"])
        response = self._create(self.owner, organization_id=str(self.org.pk))
        self.assertEqual(response.status_code, 403)

    def test_organization_post_does_not_leak_operator(self):
        self.owner.profile.name = "Secret Operator"
        self.owner.profile.save(update_fields=["name"])
        response = self._create(
            self.owner, body="secret org body", organization_id=str(self.org.pk)
        )
        payload = response.json()["post"]
        raw = json.dumps(payload)
        self.assertNotIn(self.owner.email, raw)
        self.assertNotIn(self.owner.username, raw)
        self.assertNotIn("Secret Operator", raw)
        self.assertIsNone(payload["author"])
        self.assertNotEqual(payload["organization"]["is_verified"], None)
        self.assertTrue(
            TimelinePost.objects.filter(
                pk=payload["id"], author_id=self.owner.pk
            ).exists()
        )

    def test_organization_post_hidden_from_public_surfaces(self):
        created = self._create(
            self.owner, organization_id=str(self.org.pk)
        ).json()["post"]["id"]
        self.client.logout()
        listed = self.client.get("/api/v1/timeline/").json()["posts"]
        self.assertFalse(any(item["id"] == created for item in listed))
        self.assertTrue(any(item["id"] == self.personal.pk for item in listed))
        public_detail = self.client.get(f"/api/v1/timeline/{created}/")
        self.assertEqual(public_detail.status_code, 404)
        self.client.force_login(self.outsider)
        like = self.client.post(f"/api/v1/timeline/{created}/like/")
        self.assertEqual(like.status_code, 404)
        quote = self.client.get(
            reverse("api_v1_timeline_quote", kwargs={"pk": created})
        )
        self.assertEqual(quote.status_code, 404)
        profile = self.client.get(f"/api/v1/profile/{self.owner.pk}/posts/")
        self.assertEqual(profile.status_code, 200)
        profile_ids = [item["id"] for item in profile.json().get("posts", [])]
        self.assertNotIn(created, profile_ids)

    def test_manager_can_fetch_own_organization_post_detail(self):
        created = self._create(
            self.owner, organization_id=str(self.org.pk)
        ).json()["post"]["id"]
        detail = self.client.get(f"/api/v1/timeline/{created}/")
        self.assertEqual(detail.status_code, 200)
        payload = detail.json()["post"]
        self.assertIsNone(payload["author"])
        self.assertEqual(payload["actor_type"], "organization")
        self.assertTrue(payload["can_delete"])

    def test_owner_and_admin_can_delete_organization_post(self):
        created = self._create(
            self.owner, organization_id=str(self.org.pk)
        ).json()["post"]["id"]
        self.client.force_login(self.outsider)
        denied = self.client.delete(f"/api/v1/timeline/{created}/")
        self.assertEqual(denied.status_code, 404)
        self.assertTrue(TimelinePost.objects.filter(pk=created).exists())
        self.client.force_login(self.member)
        member_denied = self.client.delete(f"/api/v1/timeline/{created}/")
        self.assertEqual(member_denied.status_code, 404)
        self.client.force_login(self.admin)
        allowed = self.client.delete(f"/api/v1/timeline/{created}/")
        self.assertEqual(allowed.status_code, 200)
        self.assertFalse(TimelinePost.objects.filter(pk=created).exists())

    def test_suspended_org_admin_can_still_delete(self):
        created = self._create(
            self.owner, organization_id=str(self.org.pk)
        ).json()["post"]["id"]
        self.org.status = Organization.Status.SUSPENDED
        self.org.save(update_fields=["status"])
        self.client.force_login(self.owner)
        blocked_create = self._create(
            self.owner, organization_id=str(self.org.pk)
        )
        self.assertEqual(blocked_create.status_code, 403)
        deleted = self.client.delete(f"/api/v1/timeline/{created}/")
        self.assertEqual(deleted.status_code, 200)

    def test_personal_delete_rules_unchanged(self):
        self.client.force_login(self.owner)
        created = self._create(self.owner, body="mine only").json()["post"]["id"]
        self.client.force_login(self.outsider)
        denied = self.client.delete(f"/api/v1/timeline/{created}/")
        self.assertEqual(denied.status_code, 403)
        self.client.force_login(self.owner)
        allowed = self.client.delete(f"/api/v1/timeline/{created}/")
        self.assertEqual(allowed.status_code, 200)

    def test_null_author_personal_post_cannot_be_deleted(self):
        orphan = TimelinePost.objects.create(author=None, body="orphan personal")
        self.client.force_login(self.owner)
        response = self.client.delete(f"/api/v1/timeline/{orphan.pk}/")
        self.assertEqual(response.status_code, 403)
        self.assertTrue(TimelinePost.objects.filter(pk=orphan.pk).exists())

    def test_likes_comments_quotes_still_work_on_personal_posts(self):
        self.client.force_login(self.owner)
        like = self.client.post(f"/api/v1/timeline/{self.personal.pk}/like/")
        self.assertEqual(like.status_code, 200)
        comment = self.client.post(
            f"/api/v1/timeline/{self.personal.pk}/comments/",
            data=json.dumps({"body": "hi"}),
            content_type="application/json",
        )
        self.assertEqual(comment.status_code, 201)
        quote = self.client.get(
            reverse("api_v1_timeline_quote", kwargs={"pk": self.personal.pk})
        )
        self.assertEqual(quote.status_code, 200)
        self.assertEqual(quote.json()["quoted_post"]["id"], self.personal.pk)

    def test_unauthenticated_csrf_and_invalid_ids(self):
        guest = Client()
        unauth = guest.post(
            "/api/v1/timeline/",
            {"body": "nope", "organization_id": str(self.org.pk)},
        )
        self.assertIn(unauth.status_code, (302, 401, 403))
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.owner)
        csrf = csrf_client.post(
            "/api/v1/timeline/",
            {"body": "csrf", "organization_id": str(self.org.pk)},
        )
        self.assertEqual(csrf.status_code, 403)
        self.client.force_login(self.owner)
        bad = self.client.post(
            "/api/v1/timeline/",
            {"body": "bad", "organization_id": "abc"},
        )
        self.assertEqual(bad.status_code, 400)
        missing = self.client.post(
            "/api/v1/timeline/",
            {"body": "missing", "organization_id": "999999"},
        )
        self.assertEqual(missing.status_code, 404)

    def test_personal_and_organization_badges_are_separate(self):
        self.owner.is_operator_verified = True
        self.owner.save(update_fields=["is_operator_verified"])
        personal = self._create(self.owner, body="badge personal").json()["post"]
        self.assertTrue(personal["author"]["is_operator_verified"])
        org_post = self._create(
            self.owner, organization_id=str(self.org.pk)
        ).json()["post"]
        self.assertIsNone(org_post["author"])
        self.assertTrue(org_post["organization"]["is_verified"])
        self.assertNotIn("is_operator_verified", org_post["organization"])

    def test_share_and_quote_hidden_when_not_public(self):
        created = self._create(
            self.owner, organization_id=str(self.org.pk)
        ).json()["post"]["id"]
        with self.assertRaises(ValueError) as ctx:
            require_shareable_target(self.outsider, "timeline", created)
        self.assertEqual(str(ctx.exception), "invalid_target")
        self.client.force_login(self.outsider)
        quote = self.client.get(
            reverse("api_v1_timeline_quote", kwargs={"pk": created})
        )
        self.assertEqual(quote.status_code, 404)
        bookmark = self.client.post(f"/api/v1/timeline/{created}/bookmark/")
        self.assertEqual(bookmark.status_code, 404)
        search = self.client.get(
            "/api/v1/search/", {"q": "org named post", "tab": "all"}
        )
        self.assertEqual(search.status_code, 200)
        post_ids = [item["id"] for item in search.json().get("posts") or []]
        self.assertNotIn(created, post_ids)

    def test_org_profile_posts_are_manager_preview_when_not_public(self):
        created = self._create(
            self.owner, organization_id=str(self.org.pk)
        ).json()["post"]
        self.assertEqual(created["visibility"], "draft")
        self.client.force_login(self.outsider)
        hidden = self.client.get(
            f"/api/v1/organizations/{self.org.slug}/posts/"
        )
        self.assertEqual(hidden.status_code, 200)
        hidden_data = hidden.json()
        self.assertTrue(hidden_data["unpublished"])
        self.assertFalse(hidden_data["preview"])
        self.assertEqual(hidden_data["posts"], [])
        self.assertNotIn("unpublished_count", hidden_data)
        self.client.force_login(self.owner)
        public_tab = self.client.get(
            f"/api/v1/organizations/{self.org.slug}/posts/"
        )
        self.assertEqual(public_tab.status_code, 200)
        public_data = public_tab.json()
        self.assertFalse(public_data["preview"])
        self.assertEqual(public_data["posts"], [])
        self.assertEqual(public_data["unpublished_count"], 1)
        self.assertEqual(public_data["public_count"], 0)
        preview = self.client.get(
            f"/api/v1/organizations/{self.org.slug}/posts/",
            {"scope": "unpublished"},
        )
        self.assertEqual(preview.status_code, 200)
        data = preview.json()
        self.assertTrue(data["preview"])
        self.assertEqual(data["scope"], "unpublished")
        self.assertEqual(data["posts"][0]["id"], created["id"])
        self.assertEqual(data["posts"][0]["visibility"], "draft")
        self.assertIsNone(data["posts"][0]["author"])
        self.assertNotIn("Secret Operator", json.dumps(data))

    def test_like_on_organization_post_does_not_notify_operator(self):
        created = self._create(
            self.owner, organization_id=str(self.org.pk)
        ).json()["post"]["id"]
        before = Notification.objects.filter(recipient=self.owner).count()
        self.client.force_login(self.outsider)
        like = self.client.post(f"/api/v1/timeline/{created}/like/")
        self.assertEqual(like.status_code, 404)
        self.assertEqual(
            Notification.objects.filter(recipient=self.owner).count(), before
        )

    def test_organization_post_does_not_copy_operator_faculty(self):
        self.owner.profile.department = "政治経済学部"
        self.owner.profile.save(update_fields=["department"])
        created = self._create(
            self.owner, organization_id=str(self.org.pk)
        ).json()["post"]
        self.assertEqual(created["faculty"], "")
        row = TimelinePost.objects.get(pk=created["id"])
        self.assertEqual(row.faculty, "")

    def test_forbidden_org_create_does_not_fall_back_to_personal(self):
        before = TimelinePost.objects.filter(author=self.member).count()
        response = self._create(self.member, organization_id=str(self.org.pk))
        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            TimelinePost.objects.filter(author=self.member).count(), before
        )
        self.assertFalse(
            TimelinePost.objects.filter(
                author=self.member, organization=self.org
            ).exists()
        )

    def test_hidden_org_post_matches_missing_error_payload(self):
        self.owner.profile.name = "Secret Operator"
        self.owner.profile.save(update_fields=["name"])
        created = self._create(
            self.owner,
            body="hidden-org-secret-body",
            organization_id=str(self.org.pk),
        ).json()["post"]["id"]
        missing_pk = 9_999_999
        self.client.logout()
        guest_hidden = self.client.get(f"/api/v1/timeline/{created}/")
        guest_missing = self.client.get(f"/api/v1/timeline/{missing_pk}/")
        self.assertEqual(guest_hidden.status_code, 404)
        self.assertEqual(guest_hidden.json(), guest_missing.json())
        self.assertNotIn("hidden-org-secret-body", json.dumps(guest_hidden.json()))

        self.client.force_login(self.outsider)
        probes = (
            self.client.get(f"/api/v1/timeline/{created}/"),
            self.client.post(f"/api/v1/timeline/{created}/like/"),
            self.client.get(f"/api/v1/timeline/{created}/likers/"),
            self.client.post(f"/api/v1/timeline/{created}/bookmark/"),
        )
        for response in probes:
            self.assertEqual(response.status_code, 404)
            raw = json.dumps(response.json())
            self.assertNotIn("hidden-org-secret-body", raw)
            self.assertNotIn("Secret Operator", raw)
            self.assertNotIn(self.owner.email, raw)

        comment = self.client.post(
            f"/api/v1/timeline/{created}/comments/",
            data=json.dumps({"body": "probe"}),
            content_type="application/json",
        )
        self.assertEqual(comment.status_code, 404)
        self.assertNotIn("hidden-org-secret-body", json.dumps(comment.json()))

        quote = self.client.post(
            "/api/v1/timeline/",
            {"body": "quoting hidden", "quoted_post_id": str(created)},
        )
        self.assertEqual(quote.status_code, 400)
        self.assertFalse(
            TimelinePost.objects.filter(
                author=self.outsider, quoted_post_id=created
            ).exists()
        )

        impressions = self.client.post(
            "/api/v1/timeline/impressions/",
            data=json.dumps({"post_ids": [created, missing_pk]}),
            content_type="application/json",
        )
        self.assertEqual(impressions.status_code, 200)
        self.assertEqual(impressions.json()["counts"], {})
        self.assertEqual(TimelinePost.objects.get(pk=created).view_count, 0)

        self.client.force_login(self.member)
        member_posts = self.client.get(
            f"/api/v1/organizations/{self.org.slug}/posts/"
        ).json()
        self.assertTrue(member_posts["unpublished"])
        self.assertEqual(member_posts["posts"], [])
        self.client.force_login(self.other_owner)
        other_posts = self.client.get(
            f"/api/v1/organizations/{self.org.slug}/posts/"
        ).json()
        self.assertEqual(other_posts["posts"], [])

    def test_image_org_post_stays_off_operator_profile(self):
        image = SimpleUploadedFile(
            "org.gif", _MINIMAL_GIF, content_type="image/gif"
        )
        self.client.force_login(self.owner)
        response = self.client.post(
            "/api/v1/timeline/",
            {
                "body": "org with image",
                "organization_id": str(self.org.pk),
                "image": image,
            },
        )
        self.assertEqual(response.status_code, 201)
        payload = response.json()["post"]
        self.assertIsNone(payload["author"])
        self.assertTrue(payload["image_url"])
        self.client.force_login(self.outsider)
        profile = self.client.get(f"/api/v1/profile/{self.owner.pk}/posts/")
        self.assertNotIn(
            payload["id"], [item["id"] for item in profile.json().get("posts", [])]
        )

    def test_org_profile_posts_paginate(self):
        for index in range(ORG_PROFILE_POSTS_PAGE + 1):
            TimelinePost.objects.create(
                author=self.owner,
                organization=self.org,
                body=f"paged org post {index}",
            )
        self.client.force_login(self.owner)
        first = self.client.get(
            f"/api/v1/organizations/{self.org.slug}/posts/",
            {"scope": "unpublished"},
        ).json()
        self.assertTrue(first["preview"])
        self.assertTrue(first["has_more"])
        self.assertEqual(len(first["posts"]), ORG_PROFILE_POSTS_PAGE)
        second = self.client.get(
            f"/api/v1/organizations/{self.org.slug}/posts/",
            {"offset": first["next_offset"], "scope": "unpublished"},
        ).json()
        self.assertEqual(len(second["posts"]), 1)
        self.assertFalse(second["has_more"])
        self.assertNotEqual(first["posts"][0]["id"], second["posts"][0]["id"])

    def test_demoted_admin_cannot_fallback_to_personal(self):
        OrganizationMember.objects.filter(
            organization=self.org, user=self.admin
        ).update(role=OrganizationMember.Role.MEMBER)
        before = TimelinePost.objects.filter(author=self.admin).count()
        response = self._create(self.admin, organization_id=str(self.org.pk))
        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            TimelinePost.objects.filter(author=self.admin).count(), before
        )
        self.assertNotIn("post", response.json())

    def test_legacy_unlisted_org_posts_stay_off_public_surfaces(self):
        row = TimelinePost.objects.create(
            author=self.owner,
            organization=self.org,
            body="legacy unpublished org post",
        )
        self.assertEqual(
            row.organization_visibility,
            TimelinePost.OrganizationVisibility.UNLISTED,
        )
        self.client.force_login(self.outsider)
        listed = self.client.get("/api/v1/timeline/").json()["posts"]
        self.assertFalse(any(item["id"] == row.pk for item in listed))
        detail = self.client.get(f"/api/v1/timeline/{row.pk}/")
        self.assertEqual(detail.status_code, 404)
        search = self.client.get(
            "/api/v1/search/", {"q": "legacy unpublished org post", "tab": "all"}
        )
        self.assertNotIn(
            row.pk, [item["id"] for item in search.json().get("posts") or []]
        )
        profile = self.client.get(
            f"/api/v1/organizations/{self.org.slug}/posts/"
        ).json()
        self.assertEqual(profile["posts"], [])
        self.assertTrue(profile["unpublished"])

    def test_explicit_public_org_post_is_listed_while_flag_is_off(self):
        created = self._create(
            self.owner,
            body="safe public org promo",
            organization_id=str(self.org.pk),
            visibility="public",
        ).json()["post"]
        self.assertEqual(created["visibility"], "public")
        self.assertIsNone(created["author"])
        self.client.logout()
        listed = self.client.get("/api/v1/timeline/").json()["posts"]
        self.assertTrue(any(item["id"] == created["id"] for item in listed))
        self.assertTrue(any(item["id"] == self.personal.pk for item in listed))
        detail = self.client.get(f"/api/v1/timeline/{created['id']}/")
        self.assertEqual(detail.status_code, 200)
        self.assertIsNone(detail.json()["post"]["author"])
        self.client.force_login(self.outsider)
        search = self.client.get(
            "/api/v1/search/", {"q": "safe public org promo", "tab": "all"}
        )
        hit = next(
            item
            for item in search.json().get("posts") or []
            if item["id"] == created["id"]
        )
        self.assertIsNone(hit["author"])
        profile = self.client.get(
            f"/api/v1/organizations/{self.org.slug}/posts/"
        ).json()
        self.assertFalse(profile["unpublished"])
        self.assertEqual(profile["posts"][0]["id"], created["id"])

    def test_draft_org_post_stays_manager_only(self):
        created = self._create(
            self.owner,
            body="org draft only",
            organization_id=str(self.org.pk),
            visibility="draft",
        ).json()["post"]
        self.assertEqual(created["visibility"], "draft")
        self.client.force_login(self.outsider)
        listed = self.client.get("/api/v1/timeline/").json()["posts"]
        self.assertFalse(any(item["id"] == created["id"] for item in listed))
        self.assertEqual(
            self.client.get(f"/api/v1/timeline/{created['id']}/").status_code,
            404,
        )
        self.client.force_login(self.owner)
        detail = self.client.get(f"/api/v1/timeline/{created['id']}/")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()["post"]["visibility"], "draft")
        self.assertIsNone(detail.json()["post"]["author"])

    def test_invalid_visibility_does_not_create(self):
        before = TimelinePost.objects.count()
        response = self._create(
            self.owner,
            organization_id=str(self.org.pk),
            visibility="unlisted",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "invalid_visibility")
        self.assertEqual(TimelinePost.objects.count(), before)

    def test_personal_post_ignores_visibility(self):
        response = self._create(
            self.owner, body="just me vis", visibility="draft"
        )
        self.assertEqual(response.status_code, 201)
        post = response.json()["post"]
        self.assertNotIn("visibility", post)
        self.assertEqual(post["author"]["id"], self.owner.pk)
        listed = self.client.get("/api/v1/timeline/").json()["posts"]
        self.assertTrue(any(item["id"] == post["id"] for item in listed))

    def test_manager_can_publish_and_unpublish(self):
        created = self._create(
            self.owner,
            body="toggle org visibility",
            organization_id=str(self.org.pk),
            visibility="draft",
        ).json()["post"]
        self.client.force_login(self.outsider)
        self.assertEqual(
            self.client.get(f"/api/v1/timeline/{created['id']}/").status_code,
            404,
        )
        self.client.force_login(self.owner)
        published = self.client.patch(
            f"/api/v1/timeline/{created['id']}/visibility/",
            data=json.dumps({"visibility": "public"}),
            content_type="application/json",
        )
        self.assertEqual(published.status_code, 200)
        self.assertEqual(published.json()["post"]["visibility"], "public")
        self.client.force_login(self.outsider)
        self.assertEqual(
            self.client.get(f"/api/v1/timeline/{created['id']}/").status_code,
            200,
        )
        self.client.force_login(self.member)
        denied = self.client.patch(
            f"/api/v1/timeline/{created['id']}/visibility/",
            data=json.dumps({"visibility": "draft"}),
            content_type="application/json",
        )
        self.assertEqual(denied.status_code, 403)
        self.client.force_login(self.outsider)
        outsider_denied = self.client.patch(
            f"/api/v1/timeline/{created['id']}/visibility/",
            data=json.dumps({"visibility": "draft"}),
            content_type="application/json",
        )
        self.assertEqual(outsider_denied.status_code, 403)
        self.client.force_login(self.owner)
        unpublished = self.client.patch(
            f"/api/v1/timeline/{created['id']}/visibility/",
            data=json.dumps({"visibility": "draft"}),
            content_type="application/json",
        )
        self.assertEqual(unpublished.status_code, 200)
        self.assertEqual(unpublished.json()["post"]["visibility"], "draft")
        self.client.force_login(self.outsider)
        self.assertEqual(
            self.client.get(f"/api/v1/timeline/{created['id']}/").status_code,
            404,
        )

    def test_legacy_unlisted_can_be_published_without_bulk_change(self):
        legacy = TimelinePost.objects.create(
            author=self.owner,
            organization=self.org,
            body="one legacy to publish",
        )
        other = TimelinePost.objects.create(
            author=self.owner,
            organization=self.org,
            body="other legacy stays unpublished",
        )
        self.client.force_login(self.owner)
        published = self.client.patch(
            f"/api/v1/timeline/{legacy.pk}/visibility/",
            data=json.dumps({"visibility": "public"}),
            content_type="application/json",
        )
        self.assertEqual(published.status_code, 200)
        legacy.refresh_from_db()
        other.refresh_from_db()
        self.assertEqual(
            legacy.organization_visibility,
            TimelinePost.OrganizationVisibility.PUBLIC,
        )
        self.assertEqual(
            other.organization_visibility,
            TimelinePost.OrganizationVisibility.UNLISTED,
        )
        self.client.force_login(self.outsider)
        listed = self.client.get("/api/v1/timeline/").json()["posts"]
        self.assertTrue(any(item["id"] == legacy.pk for item in listed))
        self.assertFalse(any(item["id"] == other.pk for item in listed))

    def test_public_post_of_draft_org_stays_off_feed(self):
        draft = _make_org(
            name="Draft Promo",
            slug="draft-promo-org",
            status=Organization.Status.DRAFT,
            is_listed=False,
        )
        add_organization_member(
            draft, self.owner, role=OrganizationMember.Role.OWNER
        )
        created = self._create(
            self.owner,
            body="draft org public attempt",
            organization_id=str(draft.pk),
            visibility="public",
        ).json()["post"]
        self.assertEqual(created["visibility"], "public")
        self.client.force_login(self.outsider)
        listed = self.client.get("/api/v1/timeline/").json()["posts"]
        self.assertFalse(any(item["id"] == created["id"] for item in listed))
        self.assertEqual(
            self.client.get(f"/api/v1/timeline/{created['id']}/").status_code,
            404,
        )

    def test_organization_id_snapshot_is_not_overridden_by_other_org(self):
        created = self._create(
            self.owner,
            body="circledancers only",
            organization_id=str(self.org.pk),
            visibility="public",
        )
        self.assertEqual(created.status_code, 201)
        post = created.json()["post"]
        self.assertEqual(post["organization"]["id"], self.org.pk)
        self.assertNotEqual(post["organization"]["id"], self.other_org.pk)
        row = TimelinePost.objects.get(pk=post["id"])
        self.assertEqual(row.organization_id, self.org.pk)

    def test_public_org_post_can_be_reported_without_operator_name(self):
        created = self._create(
            self.owner,
            body="reportable org promo",
            organization_id=str(self.org.pk),
            visibility="public",
        ).json()["post"]["id"]
        self.owner.profile.name = "Secret Operator"
        self.owner.profile.save(update_fields=["name"])
        self.client.force_login(self.outsider)
        report = self.client.post(
            f"/report/post/{created}/",
            {"reason": "spam"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(report.status_code, 200)
        raw = json.dumps(report.json())
        self.assertNotIn("Secret Operator", raw)
        draft = self._create(
            self.owner,
            body="hidden draft report",
            organization_id=str(self.org.pk),
            visibility="draft",
        ).json()["post"]["id"]
        self.client.force_login(self.outsider)
        self.assertEqual(
            self.client.get(f"/api/v1/timeline/{draft}/").status_code, 404
        )

    def test_report_of_unpublished_org_post_matches_missing(self):
        created = self._create(
            self.owner,
            body="hidden draft report-secret",
            organization_id=str(self.org.pk),
            visibility="draft",
        ).json()["post"]["id"]
        missing_pk = 9_888_777
        self.client.force_login(self.outsider)
        hidden = self.client.post(
            f"/report/post/{created}/",
            {"reason": "spam"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        missing = self.client.post(
            f"/report/post/{missing_pk}/",
            {"reason": "spam"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(hidden.status_code, 404)
        self.assertEqual(hidden.json(), missing.json())
        raw = json.dumps(hidden.json())
        self.assertNotIn("hidden draft report-secret", raw)
        self.assertNotIn("Secret Operator", raw)
        comment = Comment.objects.create(
            timeline_post_id=created,
            author=self.owner,
            body="draft comment secret",
        )
        hidden_comment = self.client.post(
            f"/report/comment/{comment.pk}/",
            {"reason": "spam"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(hidden_comment.status_code, 404)
        self.assertNotIn(
            "draft comment secret", json.dumps(hidden_comment.json())
        )

    def test_visibility_patch_csrf_and_rate_limit(self):
        created = self._create(
            self.owner,
            body="csrf vis",
            organization_id=str(self.org.pk),
            visibility="draft",
        ).json()["post"]["id"]
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.owner)
        csrf = csrf_client.patch(
            f"/api/v1/timeline/{created}/visibility/",
            data=json.dumps({"visibility": "public"}),
            content_type="application/json",
        )
        self.assertEqual(csrf.status_code, 403)
        self.client.force_login(self.owner)
        with patch(
            "app.timeline_api_views.allow_timeline_visibility",
            return_value=False,
        ):
            limited = self.client.patch(
                f"/api/v1/timeline/{created}/visibility/",
                data=json.dumps({"visibility": "public"}),
                content_type="application/json",
            )
        self.assertEqual(limited.status_code, 429)
        row = TimelinePost.objects.get(pk=created)
        self.assertEqual(
            row.organization_visibility, TimelinePost.OrganizationVisibility.DRAFT
        )

    def test_unlisting_or_suspending_org_hides_public_posts_until_restored(self):
        created = self._create(
            self.owner,
            body="listed public then hidden",
            organization_id=str(self.org.pk),
            visibility="public",
        ).json()["post"]["id"]
        draft = self._create(
            self.owner,
            body="stays draft",
            organization_id=str(self.org.pk),
            visibility="draft",
        ).json()["post"]["id"]
        self.client.force_login(self.outsider)
        self.assertEqual(
            self.client.get(f"/api/v1/timeline/{created}/").status_code, 200
        )
        self.org.is_listed = False
        self.org.save(update_fields=["is_listed"])
        self.assertEqual(
            self.client.get(f"/api/v1/timeline/{created}/").status_code, 404
        )
        self.org.is_listed = True
        self.org.save(update_fields=["is_listed"])
        self.assertEqual(
            self.client.get(f"/api/v1/timeline/{created}/").status_code, 200
        )
        self.org.status = Organization.Status.SUSPENDED
        self.org.save(update_fields=["status"])
        self.assertEqual(
            self.client.get(f"/api/v1/timeline/{created}/").status_code, 404
        )
        self.client.force_login(self.owner)
        denied = self.client.patch(
            f"/api/v1/timeline/{created}/visibility/",
            data=json.dumps({"visibility": "draft"}),
            content_type="application/json",
        )
        self.assertEqual(denied.status_code, 403)
        self.org.status = Organization.Status.ACTIVE
        self.org.save(update_fields=["status"])
        self.client.force_login(self.outsider)
        self.assertEqual(
            self.client.get(f"/api/v1/timeline/{created}/").status_code, 200
        )
        listed = self.client.get("/api/v1/timeline/").json()["posts"]
        self.assertTrue(any(item["id"] == created for item in listed))
        self.assertFalse(any(item["id"] == draft for item in listed))


@override_settings(
    BROWSE_MODE_GATE_ENABLED=False,
    WASE_ORG_TIMELINE_POSTS_PUBLIC=True,
)
class OrganizationTimelinePostPublicApiTests(TestCase):
    """Explicit public posts. Flag ON still does not bulk-publish unlisted rows."""

    def setUp(self):
        self.owner = _make_user("org-pub-owner@waseda.jp")
        self.admin = _make_user("org-pub-admin@waseda.jp")
        self.outsider = _make_user("org-pub-outsider@waseda.jp")
        self.other_owner = _make_user("org-pub-other@waseda.jp")
        self.owner.profile.name = "Secret Operator"
        self.owner.profile.save(update_fields=["name"])
        self.org = _make_org(name="Circledancers", slug="circledancers-public")
        self.other_org = _make_org(name="Other Club", slug="other-club-public")
        add_organization_member(
            self.org, self.owner, role=OrganizationMember.Role.OWNER
        )
        add_organization_member(
            self.org, self.admin, role=OrganizationMember.Role.ADMIN
        )
        add_organization_member(
            self.other_org, self.other_owner, role=OrganizationMember.Role.OWNER
        )
        self.personal = TimelinePost.objects.create(
            author=self.outsider,
            body="personal public-flag hello",
        )
        self.client = Client()
        cache.clear()

    def _create(self, user, body="org public unique body", **extra):
        self.client.force_login(user)
        if extra.get("organization_id") and "visibility" not in extra:
            extra = {**extra, "visibility": "public"}
        return self.client.post("/api/v1/timeline/", {"body": body, **extra})

    def test_flag_on_does_not_publish_default_or_legacy(self):
        self.client.force_login(self.owner)
        default = self.client.post(
            "/api/v1/timeline/",
            {
                "body": "flag on still draft",
                "organization_id": str(self.org.pk),
            },
        )
        self.assertEqual(default.status_code, 201)
        post = default.json()["post"]
        self.assertEqual(post["visibility"], "draft")
        legacy = TimelinePost.objects.create(
            author=self.owner,
            organization=self.org,
            body="flag on legacy unlisted",
        )
        self.client.force_login(self.outsider)
        listed = self.client.get("/api/v1/timeline/").json()["posts"]
        self.assertFalse(any(item["id"] == post["id"] for item in listed))
        self.assertFalse(any(item["id"] == legacy.pk for item in listed))

    def test_personal_post_json_stays_compatible_when_public(self):
        response = self._create(self.owner, body="just me public")
        self.assertEqual(response.status_code, 201)
        post = response.json()["post"]
        self.assertNotIn("actor_type", post)
        self.assertNotIn("organization", post)
        self.assertEqual(post["author"]["id"], self.owner.pk)
        listed = self.client.get("/api/v1/timeline/").json()["posts"]
        self.assertTrue(any(item["id"] == post["id"] for item in listed))
        self.assertTrue(any(item["id"] == self.personal.pk for item in listed))

    def test_organization_posts_appear_with_org_actor_not_operator(self):
        created = self._create(
            self.owner, organization_id=str(self.org.pk)
        ).json()["post"]
        self.assertEqual(created["actor_type"], "organization")
        self.assertIsNone(created["author"])
        self.assertEqual(created["organization"]["name"], self.org.name)
        self.assertTrue(created["organization"]["is_verified"])
        self.assertNotIn("is_operator_verified", created["organization"])
        raw = json.dumps(created)
        self.assertNotIn(self.owner.email, raw)
        self.assertNotIn("Secret Operator", raw)

        self.client.logout()
        listed = self.client.get("/api/v1/timeline/").json()["posts"]
        match = next(item for item in listed if item["id"] == created["id"])
        self.assertIsNone(match["author"])
        self.assertEqual(match["organization"]["slug"], self.org.slug)
        self.assertFalse(match["can_delete"])
        self.assertNotIn("Secret Operator", json.dumps(match))

        self.client.force_login(self.owner)
        owned = self.client.get("/api/v1/timeline/").json()["posts"]
        owner_row = next(item for item in owned if item["id"] == created["id"])
        self.assertTrue(owner_row["can_delete"])

        self.client.force_login(self.other_owner)
        other = self.client.get("/api/v1/timeline/").json()["posts"]
        other_row = next(item for item in other if item["id"] == created["id"])
        self.assertFalse(other_row["can_delete"])

    def test_detail_like_comment_quote_search_share_when_public(self):
        created = self._create(
            self.owner, organization_id=str(self.org.pk)
        ).json()["post"]["id"]
        self.client.force_login(self.outsider)
        detail = self.client.get(f"/api/v1/timeline/{created}/")
        self.assertEqual(detail.status_code, 200)
        payload = detail.json()["post"]
        self.assertIsNone(payload["author"])
        self.assertEqual(payload["actor_type"], "organization")
        self.assertFalse(payload["can_delete"])

        like = self.client.post(f"/api/v1/timeline/{created}/like/")
        self.assertEqual(like.status_code, 200)
        likers = self.client.get(f"/api/v1/timeline/{created}/likers/")
        self.assertEqual(likers.status_code, 200)
        liker_blob = json.dumps(likers.json())
        self.assertNotIn(self.owner.email, liker_blob)
        self.assertNotIn("Secret Operator", liker_blob)

        comment = self.client.post(
            f"/api/v1/timeline/{created}/comments/",
            data=json.dumps({"body": "hello org"}),
            content_type="application/json",
        )
        self.assertEqual(comment.status_code, 201)
        self.assertIsNotNone(comment.json()["comment"]["author"])
        self.assertEqual(
            comment.json()["comment"]["author"]["id"], self.outsider.pk
        )

        quote = self.client.get(
            reverse("api_v1_timeline_quote", kwargs={"pk": created})
        )
        self.assertEqual(quote.status_code, 200)
        quoted = quote.json()["quoted_post"]
        self.assertIsNone(quoted["author"])
        self.assertEqual(quoted["actor_type"], "organization")
        self.assertEqual(quoted["organization"]["name"], self.org.name)

        quoted_create = self._create(
            self.outsider,
            body="quoting the org post",
            quoted_post_id=str(created),
        )
        self.assertEqual(quoted_create.status_code, 201)
        nested = quoted_create.json()["post"]["quoted_post"]
        self.assertIsNone(nested["author"])
        self.assertEqual(nested["actor_type"], "organization")
        self.assertNotIn("Secret Operator", json.dumps(nested))

        search = self.client.get(
            "/api/v1/search/", {"q": "org public unique body", "tab": "all"}
        )
        self.assertEqual(search.status_code, 200)
        posts = search.json().get("posts") or []
        hit = next(item for item in posts if item["id"] == created)
        self.assertIsNone(hit["author"])
        self.assertEqual(hit["organization"]["slug"], self.org.slug)

        classic = search_home_posts("org public unique body", viewer=self.outsider)
        classic_hit = next(item for item in classic if item["id"] == created)
        self.assertEqual(classic_hit["subtitle"], self.org.name)
        self.assertNotIn(self.owner.username, classic_hit["subtitle"])

        post = TimelinePost.objects.select_related("organization").get(pk=created)
        share = serialize_timeline_share_content(post)
        self.assertIsNone(share["author"])
        self.assertEqual(share["actor_type"], "organization")
        self.assertEqual(share["organization"]["name"], self.org.name)
        self.assertNotIn("Secret Operator", json.dumps(share))
        require_shareable_target(self.outsider, "timeline", created)

        bookmark = self.client.post(f"/api/v1/timeline/{created}/bookmark/")
        self.assertIn(bookmark.status_code, (200, 503))

        profile = self.client.get(f"/api/v1/profile/{self.owner.pk}/posts/")
        self.assertEqual(profile.status_code, 200)
        profile_ids = [item["id"] for item in profile.json().get("posts", [])]
        self.assertNotIn(created, profile_ids)

    def test_following_feed_does_not_use_operator_follow(self):
        created = self._create(
            self.owner, organization_id=str(self.org.pk)
        ).json()["post"]["id"]
        Follow.objects.create(follower=self.outsider, following=self.owner)
        self.client.force_login(self.outsider)
        following = self.client.get("/api/v1/timeline/?feed=following").json()["posts"]
        self.assertFalse(any(item["id"] == created for item in following))
        all_feed = self.client.get("/api/v1/timeline/?feed=all").json()["posts"]
        self.assertTrue(any(item["id"] == created for item in all_feed))

    def test_private_operator_does_not_hide_organization_post(self):
        self.owner.profile.is_private = True
        self.owner.profile.save(update_fields=["is_private"])
        created = self._create(
            self.owner, organization_id=str(self.org.pk)
        ).json()["post"]["id"]
        self.client.force_login(self.outsider)
        listed = self.client.get("/api/v1/timeline/").json()["posts"]
        self.assertTrue(any(item["id"] == created for item in listed))
        quote = self.client.get(
            reverse("api_v1_timeline_quote", kwargs={"pk": created})
        )
        self.assertEqual(quote.status_code, 200)

    def test_org_profile_posts_are_public_when_flag_on(self):
        created = self._create(
            self.owner, organization_id=str(self.org.pk)
        ).json()["post"]
        self.assertEqual(created["visibility"], "public")
        self.client.force_login(self.outsider)
        listed = self.client.get(
            f"/api/v1/organizations/{self.org.slug}/posts/"
        )
        self.assertEqual(listed.status_code, 200)
        data = listed.json()
        self.assertFalse(data["unpublished"])
        self.assertFalse(data["preview"])
        self.assertEqual(data["posts"][0]["id"], created["id"])
        self.assertIsNone(data["posts"][0]["author"])

    def test_faculty_filter_excludes_organization_posts(self):
        self.owner.profile.department = "政治経済学部"
        self.owner.profile.save(update_fields=["department"])
        created = self._create(
            self.owner, organization_id=str(self.org.pk)
        ).json()["post"]["id"]
        self.client.force_login(self.outsider)
        faculty_feed = self.client.get(
            "/api/v1/timeline/", {"faculty": "政治経済学部"}
        ).json()["posts"]
        self.assertFalse(any(item["id"] == created for item in faculty_feed))
        all_feed = self.client.get("/api/v1/timeline/").json()["posts"]
        self.assertTrue(any(item["id"] == created for item in all_feed))

    def test_recommend_score_ignores_operator_follow_and_faculty(self):
        from django.utils import timezone

        from .feed_ranking import timeline_recommend_score

        created = self._create(
            self.owner, organization_id=str(self.org.pk)
        ).json()["post"]["id"]
        post = TimelinePost.objects.get(pk=created)
        now = timezone.now()
        base = timeline_recommend_score(
            post,
            now=now,
            following_ids=set(),
            viewer_dept="政治経済学部",
            viewer_grade="2年",
            seen_ids=set(),
        )
        boosted = timeline_recommend_score(
            post,
            now=now,
            following_ids={self.owner.pk},
            viewer_dept="政治経済学部",
            viewer_grade="2年",
            seen_ids=set(),
        )
        self.assertEqual(base, boosted)

    def test_like_on_public_org_post_does_not_notify_operator(self):
        created = self._create(
            self.owner, organization_id=str(self.org.pk)
        ).json()["post"]["id"]
        before = Notification.objects.filter(recipient=self.owner).count()
        self.client.force_login(self.outsider)
        like = self.client.post(f"/api/v1/timeline/{created}/like/")
        self.assertEqual(like.status_code, 200)
        self.assertEqual(
            Notification.objects.filter(recipient=self.owner).count(), before
        )

    def test_draft_and_unlisted_org_posts_stay_off_public_feed(self):
        draft = _make_org(
            name="Draft Club",
            slug="draft-club-public",
            status=Organization.Status.DRAFT,
            is_listed=False,
        )
        add_organization_member(
            draft, self.owner, role=OrganizationMember.Role.OWNER
        )
        created = self._create(
            self.owner,
            body="draft org hidden",
            organization_id=str(draft.pk),
        ).json()["post"]["id"]
        self.client.force_login(self.owner)
        preview = self.client.get(f"/api/v1/organizations/{draft.slug}/posts/")
        self.assertEqual(preview.status_code, 200)
        preview_data = preview.json()
        self.assertTrue(any(item["id"] == created for item in preview_data["posts"]))
        self.client.force_login(self.outsider)
        listed = self.client.get("/api/v1/timeline/").json()["posts"]
        self.assertFalse(any(item["id"] == created for item in listed))
        profile = self.client.get(f"/api/v1/organizations/{draft.slug}/posts/")
        self.assertEqual(profile.status_code, 404)

        unlisted = _make_org(
            name="Unlisted Club",
            slug="unlisted-club-public",
            status=Organization.Status.ACTIVE,
            is_listed=False,
        )
        add_organization_member(
            unlisted, self.owner, role=OrganizationMember.Role.OWNER
        )
        hidden = self._create(
            self.owner,
            body="unlisted org hidden",
            organization_id=str(unlisted.pk),
        ).json()["post"]["id"]
        self.client.force_login(self.outsider)
        public_feed = self.client.get("/api/v1/timeline/").json()["posts"]
        self.assertFalse(any(item["id"] == hidden for item in public_feed))
        outsider_profile = self.client.get(
            f"/api/v1/organizations/{unlisted.slug}/posts/"
        )
        self.assertEqual(outsider_profile.status_code, 200)
        outsider_data = outsider_profile.json()
        self.assertTrue(outsider_data["unpublished"])
        self.assertEqual(outsider_data["posts"], [])
        self.client.force_login(self.owner)
        manager_preview = self.client.get(
            f"/api/v1/organizations/{unlisted.slug}/posts/"
        ).json()
        self.assertTrue(
            any(item["id"] == hidden for item in manager_preview["posts"])
        )

    def test_delete_removes_organization_profile_post(self):
        created = self._create(
            self.owner, organization_id=str(self.org.pk)
        ).json()["post"]["id"]
        self.client.force_login(self.owner)
        deleted = self.client.delete(f"/api/v1/timeline/{created}/")
        self.assertEqual(deleted.status_code, 200)
        listed = self.client.get(
            f"/api/v1/organizations/{self.org.slug}/posts/"
        ).json()
        self.assertFalse(any(item["id"] == created for item in listed["posts"]))
        self.client.force_login(self.outsider)
        feed = self.client.get("/api/v1/timeline/").json()["posts"]
        self.assertFalse(any(item["id"] == created for item in feed))

    def test_outsider_delete_is_forbidden_when_public(self):
        created = self._create(
            self.owner, organization_id=str(self.org.pk)
        ).json()["post"]["id"]
        self.client.force_login(self.outsider)
        denied = self.client.delete(f"/api/v1/timeline/{created}/")
        self.assertEqual(denied.status_code, 403)
        self.assertTrue(TimelinePost.objects.filter(pk=created).exists())
        missing = self.client.delete("/api/v1/timeline/9999999/")
        self.assertEqual(missing.status_code, 404)

    def test_unlisted_quoted_org_post_does_not_leak_body(self):
        created = self._create(
            self.owner,
            body="listed-then-unlisted-secret",
            organization_id=str(self.org.pk),
        ).json()["post"]["id"]
        quoted = self._create(
            self.outsider,
            body="quoting org",
            quoted_post_id=str(created),
        )
        self.assertEqual(quoted.status_code, 201)
        self.org.is_listed = False
        self.org.save(update_fields=["is_listed"])
        self.client.force_login(self.outsider)
        nested = self.client.get(
            f"/api/v1/timeline/{quoted.json()['post']['id']}/"
        ).json()["post"]["quoted_post"]
        self.assertTrue(nested["is_removed"])
        self.assertEqual(nested["body"], "")
        self.assertIsNone(nested["author"])
        self.assertNotIn("organization", nested)
        raw = json.dumps(nested)
        self.assertNotIn("listed-then-unlisted-secret", raw)
        self.assertNotIn("Secret Operator", raw)
