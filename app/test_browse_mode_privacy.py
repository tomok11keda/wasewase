"""Browse Mode はプロダクトプレビューのみ。学生データ API は 401。"""

from __future__ import annotations

import json

from django.test import Client, SimpleTestCase, TestCase, override_settings

from .browse_mode_services import (
    path_allows_browse_mode_api,
    path_allows_without_browse_mode,
    path_denies_student_data_in_browse_mode,
)
from .community_services import seed_communities
from .course_services import create_offering, current_academic_year
from .models import (
    Community,
    CommunityThread,
    CourseReview,
    Product,
    TimelinePost,
    User,
    UserProfile,
)
from .timetable_services import upsert_timetable_slot


class BrowseModePathHelperTests(SimpleTestCase):
    def test_shell_and_auth_paths_allowed_without_browse(self):
        self.assertTrue(path_allows_without_browse_mode("/app/login"))
        self.assertTrue(path_allows_without_browse_mode("/api/v1/me/"))
        self.assertTrue(path_allows_without_browse_mode("/api/v1/auth/browse/"))
        self.assertFalse(path_allows_without_browse_mode("/api/v1/timeline/"))
        self.assertFalse(path_allows_without_browse_mode("/app/"))

    def test_browse_mode_allows_only_preview_apis(self):
        self.assertTrue(path_allows_browse_mode_api("/api/v1/me/"))
        self.assertTrue(path_allows_browse_mode_api("/api/v1/auth/browse/"))
        self.assertTrue(path_allows_browse_mode_api("/api/v1/courses/meta/"))
        self.assertFalse(path_allows_browse_mode_api("/api/v1/courses/discover/"))
        self.assertFalse(path_allows_browse_mode_api("/api/v1/timeline/"))
        self.assertFalse(path_allows_browse_mode_api("/api/timetable/user/1/"))

    def test_student_data_apis_denied_in_browse_mode(self):
        self.assertTrue(path_denies_student_data_in_browse_mode("/api/v1/timeline/"))
        self.assertTrue(
            path_denies_student_data_in_browse_mode("/api/v1/timeline/1/")
        )
        self.assertTrue(
            path_denies_student_data_in_browse_mode("/api/v1/timeline/1/likers/")
        )
        self.assertTrue(
            path_denies_student_data_in_browse_mode("/api/v1/timeline/impressions/")
        )
        self.assertTrue(path_denies_student_data_in_browse_mode("/api/v1/profile/1/"))
        self.assertTrue(path_denies_student_data_in_browse_mode("/api/v1/search/"))
        self.assertTrue(
            path_denies_student_data_in_browse_mode("/api/v1/communities/threads/")
        )
        self.assertTrue(path_denies_student_data_in_browse_mode("/api/v1/flea/"))
        self.assertTrue(
            path_denies_student_data_in_browse_mode("/api/v1/flea/products/1/")
        )
        self.assertTrue(
            path_denies_student_data_in_browse_mode("/api/v1/courses/discover/")
        )
        self.assertTrue(
            path_denies_student_data_in_browse_mode(
                "/api/v1/courses/offerings/1/"
            )
        )
        self.assertTrue(
            path_denies_student_data_in_browse_mode("/api/timetable/user/1/")
        )
        self.assertFalse(path_denies_student_data_in_browse_mode("/app/"))
        self.assertFalse(path_denies_student_data_in_browse_mode("/app/users/1"))
        self.assertFalse(path_denies_student_data_in_browse_mode("/api/v1/me/"))
        self.assertFalse(
            path_denies_student_data_in_browse_mode("/api/v1/courses/meta/")
        )


@override_settings(BROWSE_MODE_GATE_ENABLED=True, WASE_REACT_SPA=True)
class BrowseModePrivacyApiTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            email="browse-owner@waseda.jp",
            password="test-pass-12345",
            username="browseowner",
        )
        UserProfile.objects.update_or_create(
            user=self.user,
            defaults={
                "name": "閲覧対象",
                "bio": "秘密の自己紹介",
                "department": "政治経済学部",
                "grade": "3年",
                "is_timetable_public": True,
            },
        )
        self.post = TimelinePost.objects.create(
            author=self.user,
            body="キャンパスの投稿本文",
            like_count=0,
            view_count=3,
        )
        self.product = Product.objects.create(
            seller=self.user,
            name="ミクロ経済学の教科書",
            price=1200,
            description="出品説明",
            category="未分類",
            faculty="政治経済学部",
            handover_campus="waseda",
            status=Product.Status.AVAILABLE,
        )
        seed_communities()
        self.community = Community.objects.filter(is_active=True).first()
        self.assertIsNotNone(self.community)
        self.thread = CommunityThread.objects.create(
            community=self.community,
            author=self.user,
            title="履修の相談",
            body="スレッド本文です",
        )
        offering, _dups = create_offering(
            user=self.user,
            title="ミクロ経済学",
            instructor="テスト教員",
            academic_year=current_academic_year(),
            semester="spring",
            day_of_week=0,
            period=2,
            force_create=True,
        )
        self.offering = offering
        CourseReview.objects.create(
            user=self.user,
            offering=self.offering,
            overall_rating=4,
            difficulty_rating=3,
            workload_rating=3,
            attendance_rating=3,
            exam_rating=3,
            comment="課題が多いです",
        )
        upsert_timetable_slot(
            self.user,
            slot_key="p2-d0",
            name="ミクロ経済学",
            room="3-201",
            credits="2",
            memo="非公開メモ",
            offering=self.offering,
        )

    def _enter_browse(self):
        res = self.client.post(
            "/api/v1/auth/browse/",
            data=json.dumps({"next": "/app/"}),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 200)
        me = res.json()["me"]
        self.assertFalse(me["authenticated"])
        self.assertTrue(me["is_browse_mode"])
        return res

    def _assert_denied(self, response, *, leak: str | None = None):
        self.assertEqual(response.status_code, 401)
        data = response.json()
        self.assertFalse(data.get("ok", True))
        self.assertEqual(data.get("error"), "unauthorized")
        blob = json.dumps(data)
        self.assertNotIn("@waseda.jp", blob)
        if leak:
            self.assertNotIn(leak, blob)

    def test_enter_browse_me_and_spa_shell(self):
        self._enter_browse()
        me = self.client.get("/api/v1/me/")
        self.assertEqual(me.status_code, 200)
        payload = me.json()
        self.assertFalse(payload["authenticated"])
        self.assertTrue(payload["is_browse_mode"])
        self.assertIsNone(payload.get("user"))

        shell = self.client.get("/app/")
        self.assertEqual(shell.status_code, 200)
        users = self.client.get("/app/users/1")
        self.assertEqual(users.status_code, 200)

    def test_browse_mode_denies_student_content_apis(self):
        self._enter_browse()
        self._assert_denied(
            self.client.get("/api/v1/timeline/"), leak="キャンパスの投稿本文"
        )
        self._assert_denied(
            self.client.get(f"/api/v1/timeline/{self.post.pk}/likers/"),
            leak="閲覧対象",
        )
        self._assert_denied(
            self.client.get(f"/api/v1/profile/{self.user.pk}/"),
            leak="秘密の自己紹介",
        )
        self._assert_denied(
            self.client.get(f"/api/v1/profile/{self.user.pk}/posts/"),
            leak="キャンパスの投稿本文",
        )
        self._assert_denied(
            self.client.get(f"/api/v1/profile/{self.user.pk}/products/"),
            leak="ミクロ経済学の教科書",
        )
        self._assert_denied(
            self.client.get(f"/api/v1/profile/{self.user.pk}/followers/")
        )
        self._assert_denied(
            self.client.get(f"/api/v1/profile/{self.user.pk}/following/")
        )
        self._assert_denied(
            self.client.get("/api/v1/search/?q=ミクロ"), leak="閲覧対象"
        )
        self._assert_denied(
            self.client.get("/api/v1/communities/threads/"), leak="履修の相談"
        )
        self._assert_denied(
            self.client.get(
                f"/api/v1/communities/{self.community.slug}/threads/{self.thread.pk}/"
            ),
            leak="スレッド本文です",
        )
        self._assert_denied(
            self.client.get("/api/v1/flea/"), leak="ミクロ経済学の教科書"
        )
        self._assert_denied(
            self.client.get(f"/api/v1/flea/products/{self.product.pk}/"),
            leak="出品説明",
        )
        self._assert_denied(
            self.client.get("/api/v1/courses/discover/"), leak="ミクロ経済学"
        )
        self._assert_denied(
            self.client.get("/api/v1/courses/search/?q=ミクロ"),
            leak="ミクロ経済学",
        )
        self._assert_denied(
            self.client.get(f"/api/v1/courses/offerings/{self.offering.pk}/"),
            leak="テスト教員",
        )
        self._assert_denied(
            self.client.get(
                f"/api/v1/courses/offerings/{self.offering.pk}/reviews/"
            ),
            leak="課題が多いです",
        )
        self._assert_denied(
            self.client.get(f"/api/timetable/user/{self.user.pk}/"),
            leak="3-201",
        )

    def test_browse_mode_denies_already_private_surfaces(self):
        self._enter_browse()
        self._assert_denied(self.client.get("/api/v1/dm/inbox/"))
        self._assert_denied(self.client.get("/api/v1/notifications/"))
        self._assert_denied(self.client.get("/api/v1/calendar/events/"))
        self._assert_denied(
            self.client.get(
                f"/api/v1/courses/offerings/{self.offering.pk}/talk/"
            )
        )

    def test_browse_mode_impressions_do_not_mutate(self):
        self._enter_browse()
        before = self.post.view_count
        res = self.client.post(
            "/api/v1/timeline/impressions/",
            data=json.dumps({"post_ids": [self.post.pk]}),
            content_type="application/json",
        )
        self._assert_denied(res)
        self.post.refresh_from_db()
        self.assertEqual(self.post.view_count, before)

    def test_browse_mode_course_meta_allowed(self):
        self._enter_browse()
        res = self.client.get("/api/v1/courses/meta/")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data.get("ok"))
        self.assertIn("faculties", data)
        blob = json.dumps(data)
        self.assertNotIn("閲覧対象", blob)
        self.assertNotIn("課題が多いです", blob)

    def test_authenticated_student_data_still_works(self):
        self.client.force_login(self.user)
        timeline = self.client.get("/api/v1/timeline/")
        self.assertEqual(timeline.status_code, 200)
        self.assertTrue(
            any(p["id"] == self.post.pk for p in timeline.json()["posts"])
        )

        profile = self.client.get(f"/api/v1/profile/{self.user.pk}/")
        self.assertEqual(profile.status_code, 200)
        self.assertEqual(profile.json()["user"]["id"], self.user.pk)
        self.assertIn("秘密の自己紹介", profile.json()["user"]["bio"])

        search = self.client.get("/api/v1/search/?q=ミクロ")
        self.assertEqual(search.status_code, 200)
        self.assertTrue(search.json().get("ok"))

        threads = self.client.get("/api/v1/communities/threads/")
        self.assertEqual(threads.status_code, 200)
        self.assertTrue(
            any(t["id"] == self.thread.pk for t in threads.json()["threads"])
        )

        flea = self.client.get("/api/v1/flea/")
        self.assertEqual(flea.status_code, 200)
        self.assertTrue(
            any(p["id"] == self.product.pk for p in flea.json()["products"])
        )

        courses = self.client.get("/api/v1/courses/discover/")
        self.assertEqual(courses.status_code, 200)
        detail = self.client.get(
            f"/api/v1/courses/offerings/{self.offering.pk}/"
        )
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()["offering"]["id"], self.offering.pk)

        slots = self.client.get(f"/api/timetable/user/{self.user.pk}/")
        self.assertEqual(slots.status_code, 200)
        self.assertEqual(slots.json()["owner"]["id"], self.user.pk)
        self.assertIn("p2-d0", slots.json()["slots"])

        impressions = self.client.post(
            "/api/v1/timeline/impressions/",
            data=json.dumps({"post_ids": [self.post.pk]}),
            content_type="application/json",
        )
        self.assertEqual(impressions.status_code, 200)
        self.assertTrue(impressions.json()["ok"])
        self.post.refresh_from_db()
        self.assertEqual(self.post.view_count, 4)
