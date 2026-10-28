"""Phase 3: public event signup modes and live timeline share cards."""

from __future__ import annotations

import json
from datetime import timedelta

from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.utils import timezone

from .board_services import TIMELINE_INITIAL_SIZE
from .models import (
    Organization,
    OrganizationEvent,
    OrganizationMember,
    TimelinePost,
    User,
    UserProfile,
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
class OrganizationEventPhase34Tests(TestCase):
    def setUp(self):
        cache.clear()
        self.owner = _make_user("p34-owner@waseda.jp", username="p34owner")
        self.student = _make_user("p34-student@waseda.jp", username="p34student")
        self.other = _make_user("p34-other@waseda.jp", username="p34other")
        self.org = Organization.objects.create(
            name="Phase34団体",
            slug="phase34-org",
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

    def _create_published(self, **overrides):
        self.client.force_login(self.owner)
        data = {
            "title": "新歓説明会",
            "description": "紹介",
            "starts_at": self.starts,
            "ends_at": self.ends,
            "venue_name": "大隈講堂",
        }
        data.update(overrides)
        created = self._json("post", self._url(), **data)
        self.assertEqual(created.status_code, 201, created.content)
        event_id = created.json()["event"]["id"]
        published = self._json("post", self._url(f"{event_id}/publish/"))
        self.assertEqual(published.status_code, 200, published.content)
        return event_id

    def test_existing_events_default_to_registration(self):
        event_id = self._create_published()
        event = OrganizationEvent.objects.get(pk=event_id)
        self.assertEqual(event.signup_mode, OrganizationEvent.SignupMode.REGISTRATION)
        self.client.force_login(self.student)
        detail = self.client.get(self._url(f"{event_id}/"))
        body = detail.json()["event"]
        self.assertEqual(body["signup_mode"], "registration")
        self.assertTrue(body["can_register"])

    def test_announcement_event_cannot_register_or_lottery(self):
        event_id = self._create_published(signup_mode="announcement")
        self.client.force_login(self.student)
        detail = self.client.get(self._url(f"{event_id}/"))
        body = detail.json()["event"]
        self.assertEqual(body["signup_mode"], "announcement")
        self.assertFalse(body["can_register"])
        self.assertFalse(body["can_run_lottery"])
        denied = self._json("post", self._url(f"{event_id}/register/"))
        self.assertEqual(denied.status_code, 409)
        self.assertEqual(denied.json()["error"], "announcement_only")
        self.client.force_login(self.owner)
        lottery = self._json(
            "post",
            self._url(f"{event_id}/lottery/"),
            winner_count=1,
            applicant_ids=[],
        )
        self.assertEqual(lottery.status_code, 409)
        self.assertEqual(lottery.json()["error"], "announcement_only")

    def test_registration_can_signup_until_closed_then_lottery_once(self):
        event_id = self._create_published()
        self.client.force_login(self.student)
        registered = self._json("post", self._url(f"{event_id}/register/"))
        self.assertEqual(registered.status_code, 200, registered.content)
        cancelled = self._json("post", self._url(f"{event_id}/unregister/"))
        self.assertEqual(cancelled.status_code, 200, cancelled.content)
        again = self._json("post", self._url(f"{event_id}/register/"))
        self.assertEqual(again.status_code, 200, again.content)

        self.client.force_login(self.owner)
        open_lottery = self._json(
            "post",
            self._url(f"{event_id}/lottery/"),
            winner_count=1,
            applicant_ids=[self.student.pk],
        )
        self.assertEqual(open_lottery.status_code, 409)
        self.assertEqual(open_lottery.json()["error"], "registration_still_open")

        closed = self._json(
            "patch", self._url(f"{event_id}/"), registration_open=False
        )
        self.assertEqual(closed.status_code, 200, closed.content)
        self.client.force_login(self.student)
        late = self._json("post", self._url(f"{event_id}/register/"))
        self.assertEqual(late.status_code, 409)
        self.assertEqual(late.json()["error"], "registration_closed")

        self.client.force_login(self.owner)
        drawn = self._json(
            "post",
            self._url(f"{event_id}/lottery/"),
            winner_count=1,
            applicant_ids=[self.student.pk],
        )
        self.assertEqual(drawn.status_code, 201, drawn.content)
        redraw = self._json(
            "post",
            self._url(f"{event_id}/lottery/"),
            winner_count=1,
            applicant_ids=[self.student.pk],
        )
        self.assertEqual(redraw.status_code, 409)
        self.assertEqual(redraw.json()["error"], "already_drawn")

    def test_timeline_share_is_live_org_post_and_hides_unpublished(self):
        event_id = self._create_published(title="ライブカード")
        self.client.force_login(self.student)
        denied = self._json("post", self._url(f"{event_id}/timeline-share/"), body="宣伝")
        self.assertEqual(denied.status_code, 403)

        self.client.force_login(self.owner)
        shared = self._json(
            "post",
            self._url(f"{event_id}/timeline-share/"),
            body="新歓に来てね",
        )
        self.assertEqual(shared.status_code, 201, shared.content)
        post_id = shared.json()["post_id"]
        self.assertEqual(shared.json()["post_path"], f"/posts/{post_id}")
        post = TimelinePost.objects.get(pk=post_id)
        self.assertEqual(post.organization_id, self.org.pk)
        self.assertEqual(post.body, "新歓に来てね")
        self.assertEqual(post.shared_organization_event_id, event_id)
        self.assertEqual(
            post.organization_visibility, TimelinePost.OrganizationVisibility.PUBLIC
        )
        card = shared.json()["shared_organization_event"]
        self.assertEqual(card["title"], "ライブカード")
        self.assertEqual(card["status_label"], "申込受付中")
        self.assertEqual(shared.json()["post"]["actor_type"], "organization")
        self.assertIsNone(shared.json()["post"]["author"])

        feed = self.client.get("/api/v1/timeline/", {"sort": "latest"})
        self.assertEqual(feed.status_code, 200, feed.content)
        self.assertTrue(any(row["id"] == post_id for row in feed.json()["posts"]))
        org_posts = self.client.get(f"/api/v1/organizations/{self.org.slug}/posts/")
        self.assertEqual(org_posts.status_code, 200, org_posts.content)
        self.assertTrue(any(row["id"] == post_id for row in org_posts.json()["posts"]))

        self.client.force_login(self.student)
        student_feed = self.client.get("/api/v1/timeline/", {"sort": "latest"})
        self.assertEqual(student_feed.status_code, 200, student_feed.content)
        student_row = next(
            row for row in student_feed.json()["posts"] if row["id"] == post_id
        )
        self.assertEqual(student_row["actor_type"], "organization")
        self.assertEqual(student_row["shared_organization_event"]["title"], "ライブカード")
        self.assertEqual(student_row["body"], "新歓に来てね")
        self.client.force_login(self.owner)

        renamed = self._json(
            "patch", self._url(f"{event_id}/"), title="改名後イベント"
        )
        self.assertEqual(renamed.status_code, 200, renamed.content)
        detail = self.client.get(f"/api/v1/timeline/{post_id}/")
        self.assertEqual(detail.status_code, 200, detail.content)
        live = detail.json()["post"]["shared_organization_event"]
        self.assertEqual(live["title"], "改名後イベント")
        self.assertEqual(detail.json()["post"]["actor_type"], "organization")
        self.assertIsNone(detail.json()["post"]["author"])

        unpublished = self._json("post", self._url(f"{event_id}/unpublish/"))
        self.assertEqual(unpublished.status_code, 200, unpublished.content)
        owner_hidden = self.client.get(f"/api/v1/timeline/{post_id}/")
        self.assertEqual(owner_hidden.status_code, 200, owner_hidden.content)
        self.assertIsNone(owner_hidden.json()["post"]["shared_organization_event"])
        self.client.force_login(self.student)
        student_hidden = self.client.get(f"/api/v1/timeline/{post_id}/")
        self.assertEqual(student_hidden.status_code, 404)
        feed = self.client.get("/api/v1/timeline/")
        self.assertEqual(feed.status_code, 200)
        self.assertFalse(any(row["id"] == post_id for row in feed.json()["posts"]))
        org_posts = self.client.get(f"/api/v1/organizations/{self.org.slug}/posts/")
        self.assertFalse(any(row["id"] == post_id for row in org_posts.json()["posts"]))
        search = self.client.get("/api/v1/search/", {"q": "新歓に来てね", "tab": "all"})
        self.assertEqual(search.status_code, 200)
        self.assertNotIn(
            post_id, [item["id"] for item in search.json().get("posts") or []]
        )

        self.client.force_login(self.owner)
        draft_share = self._json("post", self._url(f"{event_id}/timeline-share/"))
        self.assertEqual(draft_share.status_code, 409)
        self.assertEqual(draft_share.json()["error"], "not_published")

    def _search_post_ids(self, q: str, tab: str = "latest") -> set[int]:
        res = self.client.get("/api/v1/search/", {"q": q, "tab": tab})
        self.assertEqual(res.status_code, 200, res.content)
        data = res.json()
        ids = {row["id"] for row in data.get("posts") or []}
        for row in data.get("results") or []:
            if row.get("kind") == "post" and row.get("post"):
                ids.add(row["post"]["id"])
        return ids

    def test_event_share_is_discoverable_in_latest_feed_org_profile_and_search(self):
        for i in range(TIMELINE_INITIAL_SIZE + 5):
            TimelinePost.objects.create(
                author=self.other,
                body=f"埋める用の古い投稿 {i}",
            )
        event_id = self._create_published(title="発見テスト新歓2026")
        self.client.force_login(self.owner)
        shared = self._json(
            "post",
            self._url(f"{event_id}/timeline-share/"),
            body="本文キーワードで探すシェア",
        )
        self.assertEqual(shared.status_code, 201, shared.content)
        post_id = shared.json()["post_id"]

        owner_detail = self.client.get(f"/api/v1/timeline/{post_id}/")
        self.assertEqual(owner_detail.status_code, 200)
        self.assertEqual(
            owner_detail.json()["post"]["shared_organization_event"]["title"],
            "発見テスト新歓2026",
        )
        owner_feed = self.client.get("/api/v1/timeline/", {"sort": "latest"})
        self.assertEqual(owner_feed.status_code, 200)
        owner_ids = [row["id"] for row in owner_feed.json()["posts"]]
        self.assertIn(post_id, owner_ids)
        self.assertEqual(owner_ids[0], post_id)
        self.assertTrue(owner_feed.json()["has_more"])
        self.assertGreater(owner_feed.json()["total_count"], TIMELINE_INITIAL_SIZE)

        org_posts = self.client.get(f"/api/v1/organizations/{self.org.slug}/posts/")
        self.assertTrue(any(row["id"] == post_id for row in org_posts.json()["posts"]))

        self.client.force_login(self.student)
        student_detail = self.client.get(f"/api/v1/timeline/{post_id}/")
        self.assertEqual(student_detail.status_code, 200)
        student_feed = self.client.get("/api/v1/timeline/", {"sort": "latest"})
        student_ids = [row["id"] for row in student_feed.json()["posts"]]
        self.assertIn(post_id, student_ids)
        self.assertEqual(student_ids[0], post_id)
        student_row = next(row for row in student_feed.json()["posts"] if row["id"] == post_id)
        self.assertEqual(student_row["actor_type"], "organization")
        self.assertEqual(
            student_row["shared_organization_event"]["title"], "発見テスト新歓2026"
        )

        self.assertIn(post_id, self._search_post_ids("本文キーワードで探すシェア"))
        self.assertIn(post_id, self._search_post_ids("発見テスト新歓2026"))
        self.assertIn(post_id, self._search_post_ids("発見テスト新歓2026", tab="all"))

        profile = self.student.profile
        profile.department = "政治経済学部"
        profile.save(update_fields=["department"])
        faculty_feed = self.client.get(
            "/api/v1/timeline/", {"sort": "latest", "faculty": "政治経済学部"}
        )
        faculty_ids = [row["id"] for row in faculty_feed.json()["posts"]]
        self.assertNotIn(post_id, faculty_ids)

        self.client.force_login(self.owner)
        unpublished = self._json("post", self._url(f"{event_id}/unpublish/"))
        self.assertEqual(unpublished.status_code, 200)
        self.client.force_login(self.student)
        self.assertEqual(self.client.get(f"/api/v1/timeline/{post_id}/").status_code, 404)
        hidden_feed = self.client.get("/api/v1/timeline/", {"sort": "latest"})
        self.assertNotIn(post_id, [row["id"] for row in hidden_feed.json()["posts"]])
        self.assertNotIn(post_id, self._search_post_ids("本文キーワードで探すシェア"))
        self.assertNotIn(post_id, self._search_post_ids("発見テスト新歓2026"))

    def test_draft_event_title_does_not_leak_through_search(self):
        now = timezone.now()
        draft = OrganizationEvent.objects.create(
            organization=self.org,
            title="秘密の下書きイベント題XYZ",
            starts_at=now + timedelta(days=3),
            ends_at=now + timedelta(days=3, hours=2),
            venue_name="非公開会場",
            status=OrganizationEvent.Status.DRAFT,
            created_by=self.owner,
        )
        leaked = TimelinePost.objects.create(
            author=self.owner,
            organization=self.org,
            organization_visibility=TimelinePost.OrganizationVisibility.PUBLIC,
            body="公開に見える紹介文",
            shared_organization_event=draft,
        )
        self.client.force_login(self.student)
        self.assertNotIn(leaked.pk, self._search_post_ids("秘密の下書きイベント題XYZ"))
        feed = self.client.get("/api/v1/timeline/", {"sort": "latest"})
        self.assertNotIn(leaked.pk, [row["id"] for row in feed.json()["posts"]])

    def test_timeline_share_cooldown_and_deleted_event(self):
        event_id = self._create_published()
        self.client.force_login(self.owner)
        first = self._json("post", self._url(f"{event_id}/timeline-share/"))
        self.assertEqual(first.status_code, 201, first.content)
        self.assertEqual(first.json()["post"]["body"], "イベントをシェアしました")
        second = self._json("post", self._url(f"{event_id}/timeline-share/"))
        self.assertEqual(second.status_code, 429)
        self.assertEqual(second.json()["error"], "share_cooldown")

        post_id = first.json()["post_id"]
        deleted = self._json("post", self._url(f"{event_id}/delete/"))
        self.assertEqual(deleted.status_code, 200, deleted.content)
        post = TimelinePost.objects.get(pk=post_id)
        self.assertEqual(
            post.organization_visibility, TimelinePost.OrganizationVisibility.DRAFT
        )
        owner_hidden = self.client.get(f"/api/v1/timeline/{post_id}/")
        self.assertEqual(owner_hidden.status_code, 200, owner_hidden.content)
        self.assertIsNone(owner_hidden.json()["post"]["shared_organization_event"])
        self.client.force_login(self.student)
        student_hidden = self.client.get(f"/api/v1/timeline/{post_id}/")
        self.assertEqual(student_hidden.status_code, 404)
        TimelinePost.objects.filter(pk=post_id).update(shared_organization_event=None)
        still_hidden = self.client.get(f"/api/v1/timeline/{post_id}/")
        self.assertEqual(still_hidden.status_code, 404)
        self.client.force_login(self.owner)
        share_again = self._json("post", self._url(f"{event_id}/timeline-share/"))
        self.assertEqual(share_again.status_code, 404)

    def test_cancelled_share_stays_listed_and_regular_posts_remain(self):
        event_id = self._create_published(title="中止するイベント")
        self.client.force_login(self.owner)
        shared = self._json(
            "post",
            self._url(f"{event_id}/timeline-share/"),
            body="中止確認シェア",
        )
        self.assertEqual(shared.status_code, 201, shared.content)
        post_id = shared.json()["post_id"]
        regular = TimelinePost.objects.create(
            author=self.owner,
            organization=self.org,
            organization_visibility=TimelinePost.OrganizationVisibility.PUBLIC,
            body="通常の団体投稿です",
        )
        cancelled = self._json("post", self._url(f"{event_id}/cancel/"))
        self.assertEqual(cancelled.status_code, 200, cancelled.content)

        self.client.force_login(self.student)
        detail = self.client.get(f"/api/v1/timeline/{post_id}/")
        self.assertEqual(detail.status_code, 200, detail.content)
        card = detail.json()["post"]["shared_organization_event"]
        self.assertEqual(card["title"], "中止するイベント")
        self.assertEqual(card["status_label"], "中止")
        feed = self.client.get("/api/v1/timeline/")
        feed_ids = [row["id"] for row in feed.json()["posts"]]
        self.assertIn(post_id, feed_ids)
        self.assertIn(regular.pk, feed_ids)
        regular_detail = self.client.get(f"/api/v1/timeline/{regular.pk}/")
        self.assertEqual(regular_detail.status_code, 200)
        self.assertEqual(regular_detail.json()["post"]["body"], "通常の団体投稿です")
        self.assertIsNone(regular_detail.json()["post"].get("shared_organization_event"))
