"""Cursor pagination for DM / Group / Course Talk / Trade chat history."""

from __future__ import annotations

import json

from django.test import Client, TestCase, override_settings

from app.chat_pagination import CHAT_HISTORY_PAGE_SIZE, slice_chat_history
from app.course_services import create_offering
from app.dm_services import get_or_create_dm_room
from app.models import (
    ChatMessage,
    ChatRoom,
    Follow,
    Message,
    Product,
    User,
    UserDirectMessage,
    UserProfile,
)


@override_settings(BROWSE_MODE_GATE_ENABLED=False)
class ChatHistoryPaginationHelperTests(TestCase):
    def test_slice_returns_newest_page_oldest_first(self):
        a = User.objects.create_user(email="pg-a@waseda.jp", password="x")
        b = User.objects.create_user(email="pg-b@waseda.jp", password="x")
        room, _ = get_or_create_dm_room(a, b)
        msgs = [
            UserDirectMessage.objects.create(room=room, sender=a, body=f"m{i}")
            for i in range(CHAT_HISTORY_PAGE_SIZE + 25)
        ]
        page, has_more, next_before = slice_chat_history(room.messages.all())
        self.assertTrue(has_more)
        self.assertEqual(len(page), CHAT_HISTORY_PAGE_SIZE)
        self.assertEqual(page[0].pk, msgs[-CHAT_HISTORY_PAGE_SIZE].pk)
        self.assertEqual(page[-1].pk, msgs[-1].pk)
        self.assertEqual(next_before, page[0].pk)

        older, has_more2, next_before2 = slice_chat_history(
            room.messages.all(), before=next_before
        )
        self.assertFalse(has_more2)
        self.assertEqual(len(older), 25)
        self.assertEqual(older[-1].pk, page[0].pk - 1)
        self.assertLess(older[-1].pk, page[0].pk)
        # No overlap with first page
        self.assertFalse({m.pk for m in older} & {m.pk for m in page})
        self.assertIsNone(next_before2)
        self.assertEqual(len({m.pk for m in page} | {m.pk for m in older}), len(msgs))


@override_settings(BROWSE_MODE_GATE_ENABLED=False)
class DmHistoryPaginationApiTests(TestCase):
    def setUp(self):
        self.a = User.objects.create_user(
            email="dm-pg-a@waseda.jp", password="test-pass-12345", username="dmpga"
        )
        self.b = User.objects.create_user(
            email="dm-pg-b@waseda.jp", password="test-pass-12345", username="dmpgb"
        )
        self.stranger = User.objects.create_user(
            email="dm-pg-x@waseda.jp", password="test-pass-12345", username="dmpgx"
        )
        UserProfile.objects.update_or_create(user=self.a, defaults={"name": "A"})
        UserProfile.objects.update_or_create(user=self.b, defaults={"name": "B"})
        Follow.objects.create(follower=self.a, following=self.b)
        self.room, _ = get_or_create_dm_room(self.a, self.b)
        self.client = Client()
        for i in range(120):
            UserDirectMessage.objects.create(
                room=self.room,
                sender=self.a if i % 2 == 0 else self.b,
                body=f"dm-{i}",
            )

    def test_room_open_returns_latest_page_only(self):
        self.client.force_login(self.a)
        res = self.client.get(f"/api/v1/dm/rooms/{self.room.pk}/")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(len(data["messages"]), CHAT_HISTORY_PAGE_SIZE)
        self.assertTrue(data["has_more"])
        self.assertIsNotNone(data["next_before"])
        bodies = [m["body"] for m in data["messages"]]
        self.assertEqual(bodies[-1], "dm-119")
        self.assertEqual(bodies[0], f"dm-{120 - CHAT_HISTORY_PAGE_SIZE}")

    def test_before_loads_older_without_overlap_or_gap(self):
        self.client.force_login(self.a)
        first = self.client.get(f"/api/v1/dm/rooms/{self.room.pk}/").json()
        cursor = first["next_before"]
        second = self.client.get(
            f"/api/v1/dm/rooms/{self.room.pk}/messages/?before={cursor}"
        ).json()
        self.assertEqual(len(second["messages"]), CHAT_HISTORY_PAGE_SIZE)
        self.assertTrue(second["has_more"])
        ids1 = [m["id"] for m in first["messages"]]
        ids2 = [m["id"] for m in second["messages"]]
        self.assertFalse(set(ids1) & set(ids2))
        self.assertEqual(ids2[-1] + 1, ids1[0])

        third = self.client.get(
            f"/api/v1/dm/rooms/{self.room.pk}/messages/?before={second['next_before']}"
        ).json()
        self.assertEqual(len(third["messages"]), 20)
        self.assertFalse(third["has_more"])
        self.assertIsNone(third["next_before"])
        all_ids = sorted(
            [m["id"] for m in first["messages"]]
            + [m["id"] for m in second["messages"]]
            + [m["id"] for m in third["messages"]]
        )
        self.assertEqual(len(all_ids), 120)
        self.assertEqual(len(set(all_ids)), 120)
        self.assertEqual(all_ids, list(range(all_ids[0], all_ids[0] + 120)))

    def test_poll_after_still_returns_newer_only(self):
        self.client.force_login(self.a)
        open_data = self.client.get(f"/api/v1/dm/rooms/{self.room.pk}/").json()
        latest = open_data["room"]["latest_id"]
        newer = UserDirectMessage.objects.create(
            room=self.room, sender=self.b, body="brand-new"
        )
        poll = self.client.get(
            f"/api/v1/dm/rooms/{self.room.pk}/messages/?after={latest}"
        ).json()
        self.assertEqual(len(poll["messages"]), 1)
        self.assertEqual(poll["messages"][0]["id"], newer.pk)
        self.assertFalse(poll["has_more"])

    def test_stranger_cannot_read_history(self):
        self.client.force_login(self.stranger)
        res = self.client.get(f"/api/v1/dm/rooms/{self.room.pk}/")
        self.assertEqual(res.status_code, 403)
        res2 = self.client.get(
            f"/api/v1/dm/rooms/{self.room.pk}/messages/?before=999999"
        )
        self.assertEqual(res2.status_code, 403)

    def test_opening_still_marks_unread(self):
        unread = UserDirectMessage.objects.create(
            room=self.room, sender=self.b, body="to-read", is_read=False
        )
        self.client.force_login(self.a)
        self.client.get(f"/api/v1/dm/rooms/{self.room.pk}/")
        unread.refresh_from_db()
        self.assertTrue(unread.is_read)


@override_settings(BROWSE_MODE_GATE_ENABLED=False)
class GroupHistoryPaginationApiTests(TestCase):
    def setUp(self):
        self.a = User.objects.create_user(
            email="grp-pg-a@waseda.jp", password="test-pass-12345"
        )
        self.b = User.objects.create_user(
            email="grp-pg-b@waseda.jp", password="test-pass-12345"
        )
        self.outsider = User.objects.create_user(
            email="grp-pg-x@waseda.jp", password="test-pass-12345"
        )
        Follow.objects.create(follower=self.a, following=self.b)
        self.client = Client()
        self.client.force_login(self.a)
        created = self.client.post(
            "/api/v1/dm/groups/",
            data=json.dumps({"name": "履修", "member_ids": [self.b.pk]}),
            content_type="application/json",
        )
        self.assertEqual(created.status_code, 201)
        self.room_id = created.json()["room_id"]
        room = ChatRoom.objects.get(pk=self.room_id)
        for i in range(110):
            ChatMessage.objects.create(
                room=room,
                sender=self.a if i % 2 == 0 else self.b,
                body=f"g-{i}",
            )

    def test_group_room_paginates(self):
        res = self.client.get(f"/api/v1/dm/groups/{self.room_id}/")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        # May include system join messages — still capped
        self.assertLessEqual(len(data["messages"]), CHAT_HISTORY_PAGE_SIZE)
        self.assertTrue(data["has_more"])
        cursor = data["next_before"]
        older = self.client.get(
            f"/api/v1/dm/groups/{self.room_id}/messages/?before={cursor}"
        ).json()
        self.assertTrue(len(older["messages"]) > 0)
        ids = {m["id"] for m in data["messages"]}
        older_ids = {m["id"] for m in older["messages"]}
        self.assertFalse(ids & older_ids)

    def test_outsider_forbidden(self):
        self.client.force_login(self.outsider)
        res = self.client.get(f"/api/v1/dm/groups/{self.room_id}/")
        self.assertIn(res.status_code, (403, 404))
        res2 = self.client.get(
            f"/api/v1/dm/groups/{self.room_id}/messages/?before=1"
        )
        self.assertIn(res2.status_code, (403, 404))


@override_settings(BROWSE_MODE_GATE_ENABLED=False)
class CourseTalkHistoryPaginationApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="course-pg@waseda.jp", password="test-pass-12345"
        )
        self.client = Client()
        self.client.force_login(self.user)
        offering, _ = create_offering(
            user=self.user,
            title="Pagination授業",
            instructor="教員",
            academic_year=2026,
            semester="spring",
            day_of_week=1,
            period=2,
            force_create=True,
        )
        self.offering = offering
        open_res = self.client.post(
            f"/api/v1/courses/offerings/{offering.pk}/talk/",
            data={},
            content_type="application/json",
        )
        self.assertEqual(open_res.status_code, 200)
        self.room_id = open_res.json()["room"]["id"]
        room = ChatRoom.objects.get(pk=self.room_id)
        for i in range(105):
            ChatMessage.objects.create(
                room=room, sender=self.user, body=f"c-{i}"
            )

    def test_open_and_before_paginate(self):
        open_res = self.client.post(
            f"/api/v1/courses/offerings/{self.offering.pk}/talk/",
            data={},
            content_type="application/json",
        )
        data = open_res.json()
        self.assertLessEqual(len(data["messages"]), CHAT_HISTORY_PAGE_SIZE)
        self.assertTrue(data["has_more"])
        cursor = data["next_before"]
        older = self.client.get(
            f"/api/v1/courses/talk/{self.room_id}/messages/?before={cursor}"
        ).json()
        self.assertTrue(len(older["messages"]) > 0)
        self.assertFalse(
            {m["id"] for m in data["messages"]}
            & {m["id"] for m in older["messages"]}
        )


@override_settings(BROWSE_MODE_GATE_ENABLED=False)
class TradeChatHistoryPaginationApiTests(TestCase):
    def setUp(self):
        self.seller = User.objects.create_user(
            email="trade-pg-s@waseda.jp", password="test-pass-12345"
        )
        self.buyer = User.objects.create_user(
            email="trade-pg-b@waseda.jp", password="test-pass-12345"
        )
        self.stranger = User.objects.create_user(
            email="trade-pg-x@waseda.jp", password="test-pass-12345"
        )
        self.product = Product.objects.create(
            seller=self.seller,
            name="ページネーション教科書",
            price=1000,
            description="desc",
            category="未分類",
            faculty="政治経済学部",
            handover_campus="waseda",
            status=Product.Status.AVAILABLE,
        )
        self.client = Client()
        self.client.force_login(self.buyer)
        purchase = self.client.post(
            f"/api/v1/flea/products/{self.product.pk}/purchase/",
            data=json.dumps({}),
            content_type="application/json",
        )
        self.assertEqual(purchase.status_code, 200)
        self.room_id = purchase.json()["room_id"]
        room = ChatRoom.objects.get(pk=self.room_id)
        for i in range(100):
            Message.objects.create(
                chat_room=room,
                sender=self.buyer if i % 2 == 0 else self.seller,
                body=f"t-{i}",
            )

    def test_trade_messages_paginated(self):
        res = self.client.get(f"/api/v1/flea/chats/{self.room_id}/messages/")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(len(data["messages"]), CHAT_HISTORY_PAGE_SIZE)
        self.assertTrue(data["has_more"])
        cursor = data["next_before"]
        older = self.client.get(
            f"/api/v1/flea/chats/{self.room_id}/messages/?before={cursor}"
        ).json()
        self.assertTrue(len(older["messages"]) > 0)
        self.assertFalse(
            {m["id"] for m in data["messages"]}
            & {m["id"] for m in older["messages"]}
        )

    def test_stranger_cannot_read(self):
        self.client.force_login(self.stranger)
        res = self.client.get(f"/api/v1/flea/chats/{self.room_id}/messages/")
        self.assertIn(res.status_code, (403, 404))
