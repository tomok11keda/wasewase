"""Phase 4 community JSON API tests."""

from __future__ import annotations

import json

from django.test import Client, TestCase, override_settings
from django.urls import reverse

from .community_services import notify_community_reply, seed_communities
from .models import (
    Community,
    CommunityThread,
    CommunityThreadReply,
    Notification,
    User,
)
from .ugc_services import block_user, unblock_user


@override_settings(BROWSE_MODE_GATE_ENABLED=False)
class CommunityApiTests(TestCase):
    def setUp(self):
        seed_communities()
        self.user = User.objects.create_user(
            email="comm-api@waseda.jp",
            password="test-pass-12345",
        )
        self.other = User.objects.create_user(
            email="comm-other@waseda.jp",
            password="test-pass-12345",
        )
        self.community = Community.objects.filter(is_active=True).first()
        self.assertIsNotNone(self.community)
        self.client = Client()

    def test_list_threads(self):
        CommunityThread.objects.create(
            community=self.community,
            author=self.other,
            title="履修相談",
            body="おすすめ科目ありますか",
        )
        response = self.client.get("/api/v1/communities/threads/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(any(t["title"] == "履修相談" for t in data["threads"]))
        self.assertIn("faculty_tabs", data)

    def test_create_reply_edit_delete(self):
        self.client.force_login(self.user)
        created = self.client.post(
            "/api/v1/communities/threads/",
            data=json.dumps(
                {
                    "title": "API thread",
                    "body": "hello community",
                    "tag": self.community.faculty or "",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(created.status_code, 201)
        thread = created.json()["thread"]
        slug = thread["community"]["slug"]
        pk = thread["id"]

        detail = self.client.get(
            f"/api/v1/communities/{slug}/threads/{pk}/"
        )
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()["thread"]["title"], "API thread")

        reply = self.client.post(
            f"/api/v1/communities/{slug}/threads/{pk}/replies/",
            data=json.dumps({"body": "first reply"}),
            content_type="application/json",
        )
        self.assertEqual(reply.status_code, 201)
        reply_id = reply.json()["reply"]["id"]

        edited = self.client.post(
            f"/api/v1/communities/{slug}/threads/{pk}/replies/{reply_id}/",
            data=json.dumps({"body": "edited reply"}),
            content_type="application/json",
        )
        self.assertEqual(edited.status_code, 200)
        self.assertEqual(edited.json()["reply"]["body"], "edited reply")

        deleted_reply = self.client.delete(
            f"/api/v1/communities/{slug}/threads/{pk}/replies/{reply_id}/delete/"
        )
        self.assertEqual(deleted_reply.status_code, 200)

        deleted = self.client.delete(
            f"/api/v1/communities/{slug}/threads/{pk}/delete/"
        )
        self.assertEqual(deleted.status_code, 200)
        self.assertTrue(
            CommunityThread.objects.get(pk=pk).is_removed
        )

    def test_nested_reply_one_level_display_payload(self):
        self.client.force_login(self.user)
        created = self.client.post(
            "/api/v1/communities/threads/",
            data=json.dumps(
                {
                    "title": "楽単教えて",
                    "body": "秋学期のおすすめは？",
                    "tag": self.community.faculty or "",
                }
            ),
            content_type="application/json",
        )
        thread = created.json()["thread"]
        slug = thread["community"]["slug"]
        pk = thread["id"]

        a = self.client.post(
            f"/api/v1/communities/{slug}/threads/{pk}/replies/",
            data=json.dumps({"body": "マーケティング論おすすめ"}),
            content_type="application/json",
        )
        self.assertEqual(a.status_code, 201)
        a_payload = a.json()["reply"]
        self.assertEqual(a_payload["reply_number"], 1)
        self.assertIsNone(a_payload["reply_to"])
        self.assertIn("avatar_url", a_payload["author"])
        self.assertIn("initial", a_payload["author"])

        self.client.force_login(self.other)
        b = self.client.post(
            f"/api/v1/communities/{slug}/threads/{pk}/replies/",
            data=json.dumps(
                {
                    "body": "テスト難しかった？",
                    "reply_to_id": a_payload["id"],
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(b.status_code, 201)
        b_payload = b.json()["reply"]
        self.assertEqual(b_payload["reply_number"], 2)
        self.assertEqual(b_payload["reply_to"]["id"], a_payload["id"])
        self.assertEqual(b_payload["reply_to"]["reply_number"], 1)
        self.assertFalse(b_payload["reply_to"]["is_unavailable"])

        self.client.force_login(self.user)
        c = self.client.post(
            f"/api/v1/communities/{slug}/threads/{pk}/replies/",
            data=json.dumps(
                {
                    "body": "去年は簡単だったよ",
                    "reply_to_id": b_payload["id"],
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(c.status_code, 201)
        c_payload = c.json()["reply"]
        self.assertEqual(c_payload["reply_number"], 3)
        self.assertEqual(c_payload["reply_to"]["id"], b_payload["id"])

        # Cross-thread reply_to must be rejected
        other_thread = self.client.post(
            "/api/v1/communities/threads/",
            data=json.dumps(
                {
                    "title": "別スレ",
                    "body": "別",
                    "tag": self.community.faculty or "",
                }
            ),
            content_type="application/json",
        ).json()["thread"]
        rejected = self.client.post(
            f"/api/v1/communities/{slug}/threads/{pk}/replies/",
            data=json.dumps(
                {
                    "body": "横取り",
                    "reply_to_id": 999999,
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(rejected.status_code, 400)
        self.assertEqual(rejected.json()["error"], "invalid_reply_to")

        # Soft-delete parent keeps child and marks unavailable
        self.client.delete(
            f"/api/v1/communities/{slug}/threads/{pk}/replies/{a_payload['id']}/delete/"
        )
        detail = self.client.get(
            f"/api/v1/communities/{slug}/threads/{pk}/"
        ).json()["thread"]
        by_id = {r["id"]: r for r in detail["replies"]}
        self.assertTrue(by_id[a_payload["id"]]["is_removed"])
        self.assertEqual(by_id[a_payload["id"]]["reply_number"], 1)
        self.assertTrue(by_id[b_payload["id"]]["reply_to"]["is_unavailable"])
        self.assertEqual(by_id[c_payload["id"]]["reply_to"]["id"], b_payload["id"])
        # Numbers stay stable after soft-delete
        self.assertEqual(by_id[b_payload["id"]]["reply_number"], 2)
        self.assertEqual(by_id[c_payload["id"]]["reply_number"], 3)
        self.assertNotEqual(other_thread["id"], pk)

    def test_create_requires_login(self):
        response = self.client.post(
            "/api/v1/communities/threads/",
            data=json.dumps({"title": "x", "body": "y"}),
            content_type="application/json",
        )
        self.assertIn(response.status_code, (302, 401, 403))


@override_settings(BROWSE_MODE_GATE_ENABLED=False, WASE_REACT_SPA=False)
class CommunityBilateralBlockTests(TestCase):
    def setUp(self):
        seed_communities()
        self.community = Community.objects.filter(is_active=True).first()
        self.assertIsNotNone(self.community)
        self.a = User.objects.create_user(
            email="cblk-a@waseda.jp",
            password="test-pass-12345",
            username="cblka",
        )
        self.b = User.objects.create_user(
            email="cblk-b@waseda.jp",
            password="test-pass-12345",
            username="cblkb",
        )
        self.c = User.objects.create_user(
            email="cblk-c@waseda.jp",
            password="test-pass-12345",
            username="cblkc",
        )
        self.d = User.objects.create_user(
            email="cblk-d@waseda.jp",
            password="test-pass-12345",
            username="cblkd",
        )
        self.client = Client()

    def _login(self, user):
        self.client.force_login(user)

    def _thread_ids(self):
        response = self.client.get("/api/v1/communities/threads/")
        self.assertEqual(response.status_code, 200)
        return {t["id"] for t in response.json()["threads"]}

    def _thread_by_id(self, thread_id):
        for thread in self.client.get("/api/v1/communities/threads/").json()[
            "threads"
        ]:
            if thread["id"] == thread_id:
                return thread
        return None

    def _detail(self, thread):
        slug = thread.community.slug
        return self.client.get(
            f"/api/v1/communities/{slug}/threads/{thread.pk}/"
        )

    def _reply(self, thread, body, *, reply_to_id=None):
        payload = {"body": body}
        if reply_to_id is not None:
            payload["reply_to_id"] = reply_to_id
        return self.client.post(
            f"/api/v1/communities/{thread.community.slug}/threads/{thread.pk}/replies/",
            data=json.dumps(payload),
            content_type="application/json",
        )

    def test_list_hides_blocked_author_thread_both_directions(self):
        b_thread = CommunityThread.objects.create(
            community=self.community,
            author=self.b,
            title="B authored community thread",
            body="visible only without block",
        )
        c_thread = CommunityThread.objects.create(
            community=self.community,
            author=self.c,
            title="C authored community thread",
            body="should remain visible",
        )
        self._login(self.a)
        self.assertIn(b_thread.pk, self._thread_ids())

        block_user(self.a, self.b)
        ids = self._thread_ids()
        self.assertNotIn(b_thread.pk, ids)
        self.assertIn(c_thread.pk, ids)

        unblock_user(self.a, self.b)
        block_user(self.b, self.a)
        ids = self._thread_ids()
        self.assertNotIn(b_thread.pk, ids)
        self.assertIn(c_thread.pk, ids)

        unblock_user(self.b, self.a)
        self.assertIn(b_thread.pk, self._thread_ids())

    def test_direct_detail_is_404_when_either_blocked(self):
        thread = CommunityThread.objects.create(
            community=self.community,
            author=self.b,
            title="blocked detail thread",
            body="secret body",
        )
        self._login(self.a)
        self.assertEqual(self._detail(thread).status_code, 200)

        block_user(self.a, self.b)
        hidden = self._detail(thread)
        self.assertEqual(hidden.status_code, 404)
        self.assertNotIn("secret body", hidden.content.decode("utf-8"))

        unblock_user(self.a, self.b)
        block_user(self.b, self.a)
        self.assertEqual(self._detail(thread).status_code, 404)

    def test_blocked_replies_hidden_and_reply_to_preview_unavailable(self):
        thread = CommunityThread.objects.create(
            community=self.community,
            author=self.c,
            title="open thread",
            body="owner C",
        )
        b_reply = CommunityThreadReply.objects.create(
            thread=thread,
            author=self.b,
            body="blocked counterpart body",
        )
        d_reply = CommunityThreadReply.objects.create(
            thread=thread,
            author=self.d,
            body="visible nested reply",
            reply_to=b_reply,
        )
        block_user(self.a, self.b)
        self._login(self.a)
        detail = self._detail(thread)
        self.assertEqual(detail.status_code, 200)
        payload = detail.json()["thread"]
        reply_ids = {r["id"] for r in payload["replies"]}
        self.assertNotIn(b_reply.pk, reply_ids)
        self.assertIn(d_reply.pk, reply_ids)
        self.assertEqual(payload["visible_reply_count"], 1)
        listed = self._thread_by_id(thread.pk)
        self.assertIsNotNone(listed)
        self.assertEqual(listed["replies_count"], 1)

        blob = json.dumps(payload)
        self.assertNotIn("blocked counterpart body", blob)
        self.assertNotIn("cblkb", blob)
        d_payload = next(r for r in payload["replies"] if r["id"] == d_reply.pk)
        self.assertEqual(d_payload["reply_number"], 2)
        self.assertTrue(d_payload["reply_to"]["is_unavailable"])
        self.assertEqual(d_payload["reply_to"]["display_name"], "")
        self.assertNotIn("username", d_payload["reply_to"])
        self.assertNotIn("avatar_url", d_payload["reply_to"])
        self.assertNotIn("body", d_payload["reply_to"])

    def test_blocked_user_cannot_reply_to_counterpart_thread(self):
        thread = CommunityThread.objects.create(
            community=self.community,
            author=self.a,
            title="A thread",
            body="owner A",
        )
        block_user(self.a, self.b)
        self._login(self.b)
        before = CommunityThreadReply.objects.filter(thread=thread).count()
        notes_before = Notification.objects.filter(recipient=self.a).count()
        response = self._reply(thread, "should not land")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(
            CommunityThreadReply.objects.filter(thread=thread).count(), before
        )
        self.assertEqual(
            Notification.objects.filter(recipient=self.a).count(), notes_before
        )

        unblock_user(self.a, self.b)
        block_user(self.b, self.a)
        response = self._reply(thread, "still should not land")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(
            CommunityThreadReply.objects.filter(thread=thread).count(), before
        )
        self.assertEqual(
            Notification.objects.filter(recipient=self.a).count(), notes_before
        )

    def test_blocked_reply_to_target_rejected(self):
        thread = CommunityThread.objects.create(
            community=self.community,
            author=self.c,
            title="third party thread",
            body="owner C",
        )
        b_reply = CommunityThreadReply.objects.create(
            thread=thread,
            author=self.b,
            body="target reply",
        )
        block_user(self.a, self.b)
        self._login(self.a)
        before = CommunityThreadReply.objects.filter(thread=thread).count()
        notes_before = Notification.objects.filter(recipient=self.b).count()
        response = self._reply(
            thread, "targeting blocked user", reply_to_id=b_reply.pk
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "invalid_reply_to")
        self.assertEqual(
            CommunityThreadReply.objects.filter(thread=thread).count(), before
        )
        self.assertEqual(
            Notification.objects.filter(recipient=self.b).count(), notes_before
        )

    def test_search_excludes_blocked_thread_and_blocked_reply_body(self):
        thread_keyword = "zxqvblkthread9173"
        reply_keyword = "zxqvblkreply9173"
        b_thread = CommunityThread.objects.create(
            community=self.community,
            author=self.b,
            title=f"B {thread_keyword}",
            body="B body only",
        )
        c_thread = CommunityThread.objects.create(
            community=self.community,
            author=self.c,
            title="C thread without keyword",
            body="C body has no unique token",
        )
        CommunityThreadReply.objects.create(
            thread=c_thread,
            author=self.b,
            body=f"secret {reply_keyword}",
        )
        block_user(self.a, self.b)
        self._login(self.a)

        community_list = self.client.get(
            "/api/v1/communities/threads/", {"q": thread_keyword}
        )
        self.assertEqual(community_list.status_code, 200)
        self.assertFalse(
            any(t["id"] == b_thread.pk for t in community_list.json()["threads"])
        )

        scoped = self.client.get(
            "/api/search/", {"q": thread_keyword, "scope": "communities"}
        )
        self.assertEqual(scoped.status_code, 200)
        self.assertFalse(
            any(r["id"] == b_thread.pk for r in scoped.json()["results"])
        )

        global_search = self.client.get(
            "/api/v1/search/", {"q": thread_keyword}
        )
        self.assertEqual(global_search.status_code, 200)
        self.assertFalse(
            any(t["id"] == b_thread.pk for t in global_search.json()["threads"])
        )

        reply_hits = self.client.get(
            "/api/v1/communities/threads/", {"q": reply_keyword}
        )
        self.assertFalse(
            any(t["id"] == c_thread.pk for t in reply_hits.json()["threads"])
        )
        scoped_reply = self.client.get(
            "/api/search/", {"q": reply_keyword, "scope": "communities"}
        )
        self.assertFalse(
            any(r["id"] == c_thread.pk for r in scoped_reply.json()["results"])
        )
        global_reply = self.client.get(
            "/api/v1/search/", {"q": reply_keyword}
        )
        self.assertFalse(
            any(t["id"] == c_thread.pk for t in global_reply.json()["threads"])
        )

    def test_discover_excludes_blocked_authored_thread(self):
        thread = CommunityThread.objects.create(
            community=self.community,
            author=self.b,
            title="blocked discover thread",
            body="should not recommend",
        )
        block_user(self.a, self.b)
        self._login(self.a)
        discover = self.client.get("/api/v1/search/")
        self.assertEqual(discover.status_code, 200)
        payload = discover.json()["discover"]
        thread_ids = set()
        sections = list(payload.get("trending") or [])
        sections.extend(payload.get("communities") or [])
        faculty = payload.get("faculty") or {}
        sections.extend(faculty.get("results") or [])
        for row in sections:
            if row.get("kind") != "thread":
                continue
            thread_ids.add((row.get("thread") or {}).get("id"))
        self.assertNotIn(thread.pk, thread_ids)

    def test_notify_community_reply_skips_cross_block(self):
        thread = CommunityThread.objects.create(
            community=self.community,
            author=self.a,
            title="notify thread",
            body="owner A",
        )
        block_user(self.a, self.b)
        reply = CommunityThreadReply.objects.create(
            thread=thread,
            author=self.b,
            body="direct service reply",
        )
        notify_community_reply(reply=reply, thread=thread)
        self.assertEqual(Notification.objects.filter(recipient=self.a).count(), 0)

        unblock_user(self.a, self.b)
        notify_community_reply(reply=reply, thread=thread)
        self.assertEqual(Notification.objects.filter(recipient=self.a).count(), 1)

    def test_unblocked_reply_and_notification_still_work(self):
        thread = CommunityThread.objects.create(
            community=self.community,
            author=self.a,
            title="normal thread",
            body="owner A",
        )
        self._login(self.b)
        response = self._reply(thread, "hello from B")
        self.assertEqual(response.status_code, 201)
        self.assertTrue(
            CommunityThreadReply.objects.filter(
                thread=thread, author=self.b, is_removed=False
            ).exists()
        )
        self.assertEqual(Notification.objects.filter(recipient=self.a).count(), 1)

    def test_classic_list_detail_and_reply_honor_block(self):
        thread = CommunityThread.objects.create(
            community=self.community,
            author=self.b,
            title="classic blocked thread title",
            body="classic blocked body",
        )
        block_user(self.a, self.b)
        self._login(self.a)
        index = self.client.get(reverse("communities_index"))
        self.assertEqual(index.status_code, 200)
        self.assertNotContains(index, "classic blocked thread title")

        detail = self.client.get(
            reverse(
                "community_thread_detail",
                kwargs={"slug": thread.community.slug, "thread_pk": thread.pk},
            )
        )
        self.assertEqual(detail.status_code, 404)

        a_thread = CommunityThread.objects.create(
            community=self.community,
            author=self.a,
            title="classic A thread",
            body="owner A",
        )
        self._login(self.b)
        before = CommunityThreadReply.objects.filter(thread=a_thread).count()
        reply_post = self.client.post(
            reverse(
                "create_community_thread_reply",
                kwargs={
                    "slug": a_thread.community.slug,
                    "thread_pk": a_thread.pk,
                },
            ),
            {"body": "classic should fail"},
        )
        self.assertEqual(reply_post.status_code, 404)
        self.assertEqual(
            CommunityThreadReply.objects.filter(thread=a_thread).count(),
            before,
        )
