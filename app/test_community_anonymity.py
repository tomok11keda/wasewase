"""Community anonymous board: API privacy, reports, notifications, admin FK."""

from __future__ import annotations

import json

from django.contrib.admin.sites import site
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from .community_services import notify_community_reply, seed_communities
from .models import (
    Community,
    CommunityThread,
    CommunityThreadReply,
    ContentReport,
    Notification,
    TimelinePost,
    User,
)
from .notification_api_services import serialize_notification

IDENTITY_KEYS = (
    "author",
    "username",
    "display_name",
    "email",
    "first_name",
    "last_name",
    "avatar_url",
    "profile_url",
    "initial",
)


def _assert_no_identity(testcase: TestCase, payload: dict) -> None:
    for key in IDENTITY_KEYS:
        testcase.assertNotIn(key, payload)


@override_settings(BROWSE_MODE_GATE_ENABLED=False)
class CommunityAnonymityApiTests(TestCase):
    def setUp(self):
        seed_communities()
        self.owner = User.objects.create_user(
            email="anon-owner@waseda.jp",
            password="test-pass-12345",
            username="anon_owner",
            first_name="太郎",
            last_name="早稲田",
        )
        self.viewer = User.objects.create_user(
            email="anon-viewer@waseda.jp",
            password="test-pass-12345",
            username="anon_viewer",
        )
        self.community = Community.objects.filter(is_active=True).first()
        self.assertIsNotNone(self.community)
        self.client = Client()

    def _create_thread(self, author, *, title="既存スレ", body="既存本文"):
        return CommunityThread.objects.create(
            community=self.community,
            author=author,
            title=title,
            body=body,
        )

    def test_list_and_detail_omit_author_identity_but_keep_owner_flags(self):
        thread = self._create_thread(self.owner)
        self.client.force_login(self.viewer)
        listed = self.client.get("/api/v1/communities/threads/")
        self.assertEqual(listed.status_code, 200)
        payload = next(t for t in listed.json()["threads"] if t["id"] == thread.pk)
        _assert_no_identity(self, payload)
        blob = json.dumps(payload)
        self.assertNotIn("anon_owner", blob)
        self.assertNotIn("anon-owner@waseda.jp", blob)
        self.assertNotIn("太郎", blob)
        self.assertEqual(payload["anonymous_label"], "匿名")
        self.assertFalse(payload["is_mine"])
        self.assertFalse(payload["can_delete"])
        self.assertTrue(payload["can_report"])

        detail = self.client.get(
            f"/api/v1/communities/{thread.community.slug}/threads/{thread.pk}/"
        )
        self.assertEqual(detail.status_code, 200)
        thread_payload = detail.json()["thread"]
        _assert_no_identity(self, thread_payload)
        self.assertEqual(thread_payload["anonymous_label"], "匿名")
        self.assertTrue(thread_payload["can_report"])
        self.assertFalse(thread_payload["is_mine"])

    def test_owner_keeps_delete_without_author_id(self):
        thread = self._create_thread(self.owner)
        self.client.force_login(self.owner)
        listed = self.client.get("/api/v1/communities/threads/").json()["threads"]
        payload = next(t for t in listed if t["id"] == thread.pk)
        _assert_no_identity(self, payload)
        self.assertTrue(payload["is_mine"])
        self.assertTrue(payload["can_delete"])
        self.assertFalse(payload["can_report"])

        deleted = self.client.delete(
            f"/api/v1/communities/{thread.community.slug}/threads/{thread.pk}/delete/"
        )
        self.assertEqual(deleted.status_code, 200)
        thread.refresh_from_db()
        self.assertTrue(thread.is_removed)
        self.assertEqual(thread.author_id, self.owner.pk)

    def test_comment_and_nested_reply_are_anonymous_with_owner_controls(self):
        thread = self._create_thread(self.owner)
        self.client.force_login(self.viewer)
        top = self.client.post(
            f"/api/v1/communities/{thread.community.slug}/threads/{thread.pk}/replies/",
            data=json.dumps({"body": "トップコメント"}),
            content_type="application/json",
        )
        self.assertEqual(top.status_code, 201)
        top_payload = top.json()["reply"]
        _assert_no_identity(self, top_payload)
        self.assertTrue(top_payload["is_mine"])
        self.assertTrue(top_payload["can_edit"])
        self.assertTrue(top_payload["can_delete"])
        self.assertFalse(top_payload["can_report"])
        self.assertEqual(top_payload["anonymous_label"], "匿名")

        nested = self.client.post(
            f"/api/v1/communities/{thread.community.slug}/threads/{thread.pk}/replies/",
            data=json.dumps(
                {"body": "ネスト返信", "reply_to_id": top_payload["id"]}
            ),
            content_type="application/json",
        )
        self.assertEqual(nested.status_code, 201)
        nested_payload = nested.json()["reply"]
        _assert_no_identity(self, nested_payload)
        self.assertNotIn("display_name", nested_payload.get("reply_to") or {})
        self.assertFalse((nested_payload.get("reply_to") or {}).get("is_unavailable"))

        self.client.force_login(self.owner)
        detail = self.client.get(
            f"/api/v1/communities/{thread.community.slug}/threads/{thread.pk}/"
        ).json()["thread"]
        by_id = {r["id"]: r for r in detail["replies"]}
        viewed = by_id[top_payload["id"]]
        _assert_no_identity(self, viewed)
        self.assertFalse(viewed["is_mine"])
        self.assertFalse(viewed["can_edit"])
        self.assertTrue(viewed["can_report"])
        blob = json.dumps(detail)
        self.assertNotIn("anon_viewer", blob)
        self.assertNotIn("anon-viewer@waseda.jp", blob)

    def test_existing_rows_are_anonymous_without_rewriting_author_fk(self):
        thread = self._create_thread(self.owner, title="昔の投稿", body="昔の本文")
        reply = CommunityThreadReply.objects.create(
            thread=thread,
            author=self.owner,
            body="昔のコメント",
        )
        nested = CommunityThreadReply.objects.create(
            thread=thread,
            author=self.viewer,
            body="昔の返信",
            reply_to=reply,
        )
        self.assertEqual(thread.author_id, self.owner.pk)
        self.assertEqual(reply.author_id, self.owner.pk)
        self.assertEqual(nested.author_id, self.viewer.pk)

        self.client.force_login(self.viewer)
        detail = self.client.get(
            f"/api/v1/communities/{thread.community.slug}/threads/{thread.pk}/"
        ).json()["thread"]
        _assert_no_identity(self, detail)
        self.assertEqual(detail["anonymous_label"], "匿名")
        for item in detail["replies"]:
            _assert_no_identity(self, item)
            self.assertEqual(item["anonymous_label"], "匿名")
        thread.refresh_from_db()
        reply.refresh_from_db()
        self.assertEqual(thread.author_id, self.owner.pk)
        self.assertEqual(reply.author_id, self.owner.pk)

    def test_author_fk_not_nullable_and_admin_lists_author(self):
        thread_field = CommunityThread._meta.get_field("author")
        reply_field = CommunityThreadReply._meta.get_field("author")
        self.assertFalse(thread_field.null)
        self.assertFalse(reply_field.null)
        thread_admin = site._registry[CommunityThread]
        reply_admin = site._registry[CommunityThreadReply]
        self.assertIn("author", thread_admin.list_display)
        self.assertIn("id", thread_admin.list_display)
        self.assertIn("is_removed", thread_admin.list_display)
        self.assertIn("author", reply_admin.list_display)
        self.assertIn("id", reply_admin.list_display)

    def test_timeline_api_still_includes_author_identity(self):
        post = TimelinePost.objects.create(
            author=self.owner,
            body="タイムラインは実名のまま",
        )
        self.client.force_login(self.viewer)
        response = self.client.get("/api/v1/timeline/")
        self.assertEqual(response.status_code, 200)
        found = next(p for p in response.json()["posts"] if p["id"] == post.pk)
        self.assertIn("author", found)
        self.assertEqual(found["author"]["username"], "anon_owner")
        self.assertTrue(found["author"]["display_name"])


@override_settings(BROWSE_MODE_GATE_ENABLED=False)
class CommunityReportTests(TestCase):
    def setUp(self):
        seed_communities()
        self.owner = User.objects.create_user(
            email="rpt-owner@waseda.jp",
            password="test-pass-12345",
            username="rpt_owner",
        )
        self.reporter = User.objects.create_user(
            email="rpt-user@waseda.jp",
            password="test-pass-12345",
            username="rpt_user",
        )
        self.community = Community.objects.filter(is_active=True).first()
        self.thread = CommunityThread.objects.create(
            community=self.community,
            author=self.owner,
            title="通報対象スレ",
            body="本文",
        )
        self.comment = CommunityThreadReply.objects.create(
            thread=self.thread,
            author=self.owner,
            body="トップコメント",
        )
        self.reply = CommunityThreadReply.objects.create(
            thread=self.thread,
            author=self.owner,
            body="ネスト返信",
            reply_to=self.comment,
        )
        self.client = Client()

    def _report(self, target_type, target_id, *, client=None, reason=None):
        c = client or self.client
        return c.post(
            reverse(
                "submit_report",
                kwargs={"target_type": target_type, "target_id": target_id},
            ),
            {"reason": reason or ContentReport.Reason.HARASSMENT},
            HTTP_ACCEPT="application/json",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

    def test_report_thread_comment_and_nested_reply(self):
        self.client.force_login(self.reporter)
        for target_type, target_id in (
            (ContentReport.TargetType.COMMUNITY_THREAD, self.thread.pk),
            (ContentReport.TargetType.COMMUNITY_REPLY, self.comment.pk),
            (ContentReport.TargetType.COMMUNITY_REPLY, self.reply.pk),
        ):
            response = self._report(target_type, target_id)
            self.assertEqual(response.status_code, 200, response.content)
            self.assertTrue(response.json().get("ok"))
            self.assertTrue(
                ContentReport.objects.filter(
                    reporter=self.reporter,
                    target_type=target_type,
                    target_id=target_id,
                ).exists()
            )

    def test_self_report_rejected(self):
        self.client.force_login(self.owner)
        response = self._report(
            ContentReport.TargetType.COMMUNITY_THREAD, self.thread.pk
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(
            ContentReport.objects.filter(
                reporter=self.owner,
                target_type=ContentReport.TargetType.COMMUNITY_THREAD,
                target_id=self.thread.pk,
            ).exists()
        )

    def test_invalid_target_rejected(self):
        self.client.force_login(self.reporter)
        missing = self._report(ContentReport.TargetType.COMMUNITY_THREAD, 999999)
        self.assertEqual(missing.status_code, 404)
        bogus = self._report("not_a_type", self.thread.pk)
        self.assertEqual(bogus.status_code, 400)

    def test_duplicate_report_is_idempotent(self):
        self.client.force_login(self.reporter)
        first = self._report(
            ContentReport.TargetType.COMMUNITY_REPLY, self.comment.pk
        )
        self.assertEqual(first.status_code, 200)
        dup = self._report(
            ContentReport.TargetType.COMMUNITY_REPLY,
            self.comment.pk,
            reason=ContentReport.Reason.SPAM,
        )
        self.assertEqual(dup.status_code, 200)
        self.assertTrue(dup.json().get("ok"))
        self.assertEqual(
            ContentReport.objects.filter(
                reporter=self.reporter,
                target_type=ContentReport.TargetType.COMMUNITY_REPLY,
                target_id=self.comment.pk,
            ).count(),
            1,
        )

    def test_unauthenticated_report_requires_login(self):
        response = self._report(
            ContentReport.TargetType.COMMUNITY_THREAD, self.thread.pk
        )
        self.assertIn(response.status_code, (302, 401, 403))

    def test_removed_target_cannot_be_reported(self):
        self.thread.is_removed = True
        self.thread.save(update_fields=["is_removed"])
        self.client.force_login(self.reporter)
        response = self._report(
            ContentReport.TargetType.COMMUNITY_THREAD, self.thread.pk
        )
        self.assertEqual(response.status_code, 404)


@override_settings(BROWSE_MODE_GATE_ENABLED=False)
class CommunityNotificationAnonymityTests(TestCase):
    def setUp(self):
        seed_communities()
        self.owner = User.objects.create_user(
            email="note-owner@waseda.jp",
            password="test-pass-12345",
            username="note_owner",
        )
        self.replier = User.objects.create_user(
            email="note-replier@waseda.jp",
            password="test-pass-12345",
            username="note_replier",
        )
        self.community = Community.objects.filter(is_active=True).first()
        self.thread = CommunityThread.objects.create(
            community=self.community,
            author=self.owner,
            title="通知スレ",
            body="本文",
        )

    def test_community_notification_has_no_actor_identity(self):
        reply = CommunityThreadReply.objects.create(
            thread=self.thread,
            author=self.replier,
            body="返信です",
        )
        notify_community_reply(reply=reply, thread=self.thread)
        note = Notification.objects.get(recipient=self.owner)
        self.assertEqual(note.message, "コミュニティの投稿に返信がありました")
        self.assertNotIn("note_replier", note.message)
        self.assertNotIn("note-replier@waseda.jp", note.message)
        payload = serialize_notification(note)
        self.assertEqual(payload["message"], note.message)
        self.assertNotIn("author", payload)
        self.assertNotIn("actor", payload)
        blob = json.dumps(payload)
        self.assertNotIn("note_replier", blob)

    def test_unrelated_like_notification_still_uses_name(self):
        from .notification_services import create_notification, notification_actor_label

        create_notification(
            recipient=self.owner,
            message=f"{notification_actor_label(self.replier)}さんがあなたの投稿にいいねしました",
            link="/#post-1",
            actor=self.replier,
            push_kind="like",
        )
        note = Notification.objects.get(recipient=self.owner)
        self.assertIn("さんがあなたの投稿にいいねしました", note.message)
        self.assertNotEqual(note.message, "コミュニティの投稿に返信がありました")
