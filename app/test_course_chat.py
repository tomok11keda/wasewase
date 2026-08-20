"""授業トーク（Course Talk）API / membership / merge テスト。"""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase

from app.course_chat_services import (
    get_or_create_course_talk_room,
    join_course_talk,
    leave_course_talk,
)
from app.course_services import create_offering, enroll_user_in_offering, merge_offerings
from app.models import (
    ChatMessage,
    ChatRoom,
    ChatRoomMembership,
    CourseEnrollment,
    CourseOffering,
)

User = get_user_model()


class CourseTalkApiTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            email="talk-a@ex.com", password="pass12345"
        )
        self.other = User.objects.create_user(
            email="talk-b@ex.com", password="pass12345"
        )
        self.guest = User.objects.create_user(
            email="talk-c@ex.com", password="pass12345"
        )
        self.client.force_login(self.user)
        offering, _ = create_offering(
            user=self.user,
            title="授業トーク対象",
            instructor="教員A",
            academic_year=2026,
            semester="spring",
            day_of_week=1,
            period=2,
            force_create=True,
        )
        self.offering = offering

    def _open(self, offering_id=None, client=None):
        c = client or self.client
        oid = offering_id or self.offering.pk
        return c.post(
            f"/api/v1/courses/offerings/{oid}/talk/",
            data={},
            content_type="application/json",
        )

    def test_unauthenticated_gets_401(self):
        guest = Client()
        res = guest.post(
            f"/api/v1/courses/offerings/{self.offering.pk}/talk/",
            data={},
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 401)
        self.assertEqual(res.json().get("error"), "unauthorized")

    def test_unenrolled_user_can_open_and_send(self):
        res = self._open()
        self.assertEqual(res.status_code, 200, res.content)
        data = res.json()
        self.assertTrue(data["ok"])
        self.assertTrue(data["joined"])
        room_id = data["room"]["id"]
        self.assertEqual(data["room"]["kind"], "course")
        self.assertEqual(
            ChatRoom.objects.filter(
                kind=ChatRoom.Kind.COURSE, course_offering=self.offering
            ).count(),
            1,
        )
        send = self.client.post(
            f"/api/v1/courses/talk/{room_id}/messages/send/",
            data={"body": "履修前ですが質問です"},
            content_type="application/json",
        )
        self.assertEqual(send.status_code, 200, send.content)
        self.assertEqual(ChatMessage.objects.filter(room_id=room_id).count(), 1)

    def test_current_and_past_enrollment_labels(self):
        enroll_user_in_offering(self.user, self.offering)
        opened = self._open()
        room_id = opened.json()["room"]["id"]
        self.client.post(
            f"/api/v1/courses/talk/{room_id}/messages/send/",
            data={"body": "履修中です"},
            content_type="application/json",
        )
        other_client = Client()
        other_client.force_login(self.other)
        enroll_user_in_offering(self.other, self.offering)
        CourseEnrollment.objects.filter(user=self.other, offering=self.offering).update(
            role=CourseEnrollment.Role.PAST
        )
        other_client.post(
            f"/api/v1/courses/offerings/{self.offering.pk}/talk/",
            data={},
            content_type="application/json",
        )
        other_client.post(
            f"/api/v1/courses/talk/{room_id}/messages/send/",
            data={"body": "去年取りました"},
            content_type="application/json",
        )
        payload = self.client.get(f"/api/v1/courses/talk/{room_id}/")
        self.assertEqual(payload.status_code, 200)
        msgs = {m["body"]: m for m in payload.json()["messages"]}
        self.assertEqual(msgs["履修中です"]["enrollment_label"], "履修中")
        self.assertEqual(msgs["去年取りました"]["enrollment_label"], "履修済み")

    def test_leave_and_rejoin(self):
        opened = self._open()
        room_id = opened.json()["room"]["id"]
        leave = self.client.post(
            f"/api/v1/courses/offerings/{self.offering.pk}/talk/leave/",
            data={},
            content_type="application/json",
        )
        self.assertEqual(leave.status_code, 200)
        self.assertFalse(
            ChatRoomMembership.objects.filter(
                room_id=room_id, user=self.user
            ).exists()
        )
        ChatMessage.objects.create(
            room_id=room_id, sender=self.user, body="残る"
        )
        again = self._open()
        self.assertEqual(again.status_code, 200)
        self.assertTrue(
            ChatRoomMembership.objects.filter(room_id=room_id, user=self.user).exists()
        )
        self.assertEqual(
            ChatMessage.objects.filter(room_id=room_id, body="残る").count(), 1
        )

    def test_unenroll_keeps_membership(self):
        enroll_user_in_offering(self.user, self.offering)
        self._open()
        self.offering.refresh_from_db()
        self.assertTrue(
            ChatRoomMembership.objects.filter(
                user=self.user, room_id=self.offering.chat_room_id
            ).exists()
        )
        self.client.post(
            f"/api/v1/courses/offerings/{self.offering.pk}/unenroll/",
            data={},
            content_type="application/json",
        )
        self.assertTrue(
            ChatRoomMembership.objects.filter(
                user=self.user, room_id=self.offering.chat_room_id
            ).exists()
        )
        send = self.client.post(
            f"/api/v1/courses/talk/{self.offering.chat_room_id}/messages/send/",
            data={"body": "解除後も投稿"},
            content_type="application/json",
        )
        self.assertEqual(send.status_code, 200, send.content)

    def test_one_room_per_offering(self):
        a = self._open()
        b = self._open()
        self.assertEqual(a.json()["room"]["id"], b.json()["room"]["id"])
        self.assertEqual(
            ChatRoom.objects.filter(kind=ChatRoom.Kind.COURSE).count(), 1
        )

    def test_hidden_offering_404(self):
        CourseOffering.objects.filter(pk=self.offering.pk).update(
            status=CourseOffering.Status.HIDDEN
        )
        res = self._open()
        self.assertEqual(res.status_code, 404)

    def test_review_still_requires_enrollment(self):
        bad = self.client.post(
            f"/api/v1/courses/offerings/{self.offering.pk}/reviews/",
            data={
                "overall_rating": 5,
                "difficulty_rating": 2,
                "workload_rating": 3,
                "attendance_rating": 4,
                "exam_rating": 3,
                "comment": "x",
            },
            content_type="application/json",
        )
        self.assertEqual(bad.status_code, 403)
        self.assertEqual(self._open().status_code, 200)

    def test_inbox_lists_joined_course_talk_only(self):
        self._open()
        other_client = Client()
        other_client.force_login(self.other)
        inbox = other_client.get("/api/v1/dm/inbox/?tab=course")
        self.assertEqual(inbox.status_code, 200)
        self.assertEqual(inbox.json()["tab_counts"]["course"], 0)

        mine = self.client.get("/api/v1/dm/inbox/?tab=course")
        self.assertEqual(mine.status_code, 200)
        data = mine.json()
        self.assertEqual(data["tab_counts"]["course"], 1)
        self.assertEqual(data["conversations"][0]["kind"], "course")
        self.assertIn("/talk", data["conversations"][0]["spa_path"])

    def test_enroll_auto_joins_existing_room_only(self):
        enroll_user_in_offering(self.other, self.offering)
        self.offering.refresh_from_db()
        self.assertIsNone(self.offering.chat_room_id)
        self._open()
        self.offering.refresh_from_db()
        enroll_user_in_offering(self.guest, self.offering)
        self.assertTrue(
            ChatRoomMembership.objects.filter(
                user=self.guest, room_id=self.offering.chat_room_id
            ).exists()
        )

    def test_merge_moves_course_talk(self):
        target, _ = create_offering(
            user=self.user,
            title="統合先授業",
            instructor="教員B",
            academic_year=2026,
            semester="spring",
            day_of_week=2,
            period=3,
            force_create=True,
        )
        opened = self._open()
        room_id = opened.json()["room"]["id"]
        self.client.post(
            f"/api/v1/courses/talk/{room_id}/messages/send/",
            data={"body": "merge前"},
            content_type="application/json",
        )
        merge_offerings(self.offering, target)
        target.refresh_from_db()
        self.assertEqual(target.chat_room_id, room_id)
        self.assertEqual(
            ChatMessage.objects.filter(room_id=room_id, body="merge前").count(), 1
        )
        source = CourseOffering.objects.get(pk=self.offering.pk)
        self.assertEqual(source.status, CourseOffering.Status.MERGED)
        res = self._open(offering_id=source.pk)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["offering"]["id"], target.pk)


class CourseTalkRaceTests(TestCase):
    def test_repeated_get_or_create_single_room(self):
        """SQLite では並列ロックが脆いため、逐次の競合相当を検証する。"""
        user = User.objects.create_user(email="race@ex.com", password="pass12345")
        offering, _ = create_offering(
            user=user,
            title="レース授業",
            instructor="教員",
            academic_year=2026,
            semester="spring",
            day_of_week=0,
            period=1,
            force_create=True,
        )
        rooms = []
        for _ in range(5):
            room, _created = get_or_create_course_talk_room(offering, actor=user)
            rooms.append(room.pk)
            join_course_talk(user, offering)
        self.assertEqual(len(set(rooms)), 1)
        self.assertEqual(
            ChatRoom.objects.filter(kind=ChatRoom.Kind.COURSE).count(), 1
        )
        offering.refresh_from_db()
        self.assertIsNotNone(offering.chat_room_id)
        leave_course_talk(user, offering)


class CourseTalkSchemaGapTests(TestCase):
    """reply_to / deleted_at 欠落時に open が save_failed 相当で落ちないこと。"""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            email="schema-talk@ex.com", password="pass12345"
        )
        self.client.force_login(self.user)
        offering, _ = create_offering(
            user=self.user,
            title="スキーマ欠落授業",
            instructor="教員",
            academic_year=2026,
            semester="spring",
            day_of_week=1,
            period=1,
            force_create=True,
        )
        self.offering = offering

    def test_ensure_repairs_reply_columns_and_open_succeeds(self):
        from django.db import connection

        from app.chat_schema_services import ensure_course_talk_schema

        # 実害再現: ORM モデルにはあるが DB 列が無い状態は migrate 後では作れないため、
        # ensure が冪等であることと open が 200 になることを確認する。
        ensure_course_talk_schema()
        with connection.cursor() as cursor:
            cols = {
                column.name
                for column in connection.introspection.get_table_description(
                    cursor, "app_chatmessage"
                )
            }
        self.assertIn("reply_to_id", cols)
        self.assertIn("deleted_at", cols)

        res = self.client.post(
            f"/api/v1/courses/offerings/{self.offering.pk}/talk/",
            data={},
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 200, res.content)
        data = res.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["room"]["kind"], "course")

        # 2回目は同一 Room
        again = self.client.post(
            f"/api/v1/courses/offerings/{self.offering.pk}/talk/",
            data={},
            content_type="application/json",
        )
        self.assertEqual(again.status_code, 200)
        self.assertEqual(again.json()["room"]["id"], data["room"]["id"])

    def test_unenrolled_and_leave_rejoin(self):
        guest = User.objects.create_user(
            email="schema-guest@ex.com", password="pass12345"
        )
        guest_client = Client()
        guest_client.force_login(guest)
        opened = guest_client.post(
            f"/api/v1/courses/offerings/{self.offering.pk}/talk/",
            data={},
            content_type="application/json",
        )
        self.assertEqual(opened.status_code, 200, opened.content)
        room_id = opened.json()["room"]["id"]

        leave = guest_client.post(
            f"/api/v1/courses/offerings/{self.offering.pk}/talk/leave/",
            data={},
            content_type="application/json",
        )
        self.assertEqual(leave.status_code, 200)
        self.assertFalse(
            ChatRoomMembership.objects.filter(room_id=room_id, user=guest).exists()
        )

        rejoin = guest_client.post(
            f"/api/v1/courses/offerings/{self.offering.pk}/talk/",
            data={},
            content_type="application/json",
        )
        self.assertEqual(rejoin.status_code, 200)
        self.assertEqual(rejoin.json()["room"]["id"], room_id)
        self.assertTrue(
            ChatRoomMembership.objects.filter(room_id=room_id, user=guest).exists()
        )


class CourseTalkStaleFkTests(TestCase):
    """chat_room_id が欠落 Room を指すと save_failed になっていた回帰。"""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            email="stale-talk@ex.com", password="pass12345"
        )
        self.client.force_login(self.user)
        offering, _ = create_offering(
            user=self.user,
            title="孤児FK授業",
            instructor="教員",
            academic_year=2026,
            semester="spring",
            day_of_week=2,
            period=2,
            force_create=True,
        )
        self.offering = offering

    def test_stale_chat_room_id_open_recreates_room(self):
        from django.db import connection

        room = ChatRoom.objects.create(
            kind=ChatRoom.Kind.COURSE,
            name="ghost",
            created_by=self.user,
        )
        CourseOffering.objects.filter(pk=self.offering.pk).update(
            chat_room_id=room.pk
        )
        stale_id = room.pk
        with connection.cursor() as cursor:
            cursor.execute("PRAGMA foreign_keys=OFF")
            cursor.execute("DELETE FROM app_chatroom WHERE id=%s", [stale_id])
            cursor.execute("PRAGMA foreign_keys=ON")

        self.offering.refresh_from_db()
        self.assertEqual(self.offering.chat_room_id, stale_id)
        self.assertFalse(ChatRoom.objects.filter(pk=stale_id).exists())

        # select_related 経由だと chat_room が None になり、旧実装はここで死ぬ
        cached = CourseOffering.objects.select_related("chat_room").get(
            pk=self.offering.pk
        )
        self.assertIsNone(cached.chat_room)
        self.assertEqual(cached.chat_room_id, stale_id)

        room_obj, created = get_or_create_course_talk_room(
            cached, actor=self.user
        )
        self.assertTrue(created)
        self.assertNotEqual(room_obj.pk, stale_id)

        res = self.client.post(
            f"/api/v1/courses/offerings/{self.offering.pk}/talk/",
            data={},
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 200, res.content)
        data = res.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["room"]["id"], room_obj.pk)
        self.offering.refresh_from_db()
        self.assertEqual(self.offering.chat_room_id, room_obj.pk)
