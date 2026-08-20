"""グローバル検索タブ（おすすめ / 最新 / 授業 / ユーザー / 商品）の拡張テスト。"""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase

from app.course_services import create_offering, enroll_user_in_offering, upsert_review
from app.models import Product, TimelinePost, UserProfile

User = get_user_model()


class GlobalSearchExpansionTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            email="gsearch-a@ex.com",
            password="pass12345",
            username="sato_taro_gs",
        )
        profile, _ = UserProfile.objects.get_or_create(user=self.user)
        profile.name = "佐藤太郎"
        profile.department = "商学部"
        profile.save(update_fields=["name", "department"])

        self.other = User.objects.create_user(
            email="gsearch-b@ex.com",
            password="pass12345",
            username="other_gs",
        )
        other_profile, _ = UserProfile.objects.get_or_create(user=self.other)
        other_profile.name = "別ユーザー"
        other_profile.save(update_fields=["name"])

        self.client.force_login(self.user)

        self.offering, _ = create_offering(
            user=self.user,
            title="マーケティング論グローバル検索",
            instructor="山田太郎教員",
            academic_year=2026,
            semester="spring",
            day_of_week=0,
            period=2,
            school="商学部",
            force_create=True,
        )
        enroll_user_in_offering(self.user, self.offering)
        upsert_review(
            user=self.user,
            offering=self.offering,
            overall_rating=4,
            difficulty_rating=3,
            workload_rating=2,
            attendance_rating=3,
            exam_rating=3,
            comment="課題はかなり少ないです。テストも普通です。",
        )

        # 人気だが検索語にヒットしない投稿（最新/おすすめに混ざらないこと）
        TimelinePost.objects.create(
            author=self.other,
            body="完全に無関係な人気投稿XYZ",
            like_count=9999,
        )
        TimelinePost.objects.create(
            author=self.other,
            body="佐藤太郎について語る投稿",
            like_count=1,
        )

        Product.objects.create(
            seller=self.user,
            name="マーケティング教科書",
            description="授業用テキスト",
            price=1000,
            category="教科書",
            faculty="商学部",
        )

    def _search(self, q: str, tab: str):
        return self.client.get("/api/v1/search/", {"q": q, "tab": tab})

    def test_course_title_exact_and_partial(self):
        exact = self._search("マーケティング論グローバル検索", "courses")
        self.assertEqual(exact.status_code, 200)
        data = exact.json()
        self.assertGreaterEqual(data["offering_count"], 1)
        self.assertTrue(
            any(o["id"] == self.offering.pk for o in data["offerings"])
        )
        self.assertTrue(all(r["kind"] == "offering" for r in data["results"]))

        partial = self._search("マーケティング", "courses")
        self.assertTrue(
            any(o["id"] == self.offering.pk for o in partial.json()["offerings"])
        )

    def test_instructor_and_school_match(self):
        by_teacher = self._search("山田太郎教員", "courses")
        self.assertTrue(
            any(
                o["id"] == self.offering.pk
                for o in by_teacher.json()["offerings"]
            )
        )
        by_school = self._search("商学部", "courses")
        self.assertTrue(
            any(o["id"] == self.offering.pk for o in by_school.json()["offerings"])
        )

    def test_review_comment_returns_offering_not_review(self):
        res = self._search("課題少ない", "courses")
        data = res.json()
        self.assertGreaterEqual(data["offering_count"], 1)
        self.assertTrue(
            any(o["id"] == self.offering.pk for o in data["offerings"])
        )
        self.assertTrue(all(r["kind"] == "offering" for r in data["results"]))
        self.assertFalse(any("comment" in r and r["kind"] != "offering" for r in data["results"]))

    def test_duplicate_offering_deduped(self):
        # title + instructor + review の複数ルートでも 1 件
        res = self._search("マーケティング論グローバル検索", "courses")
        ids = [o["id"] for o in res.json()["offerings"]]
        self.assertEqual(ids.count(self.offering.pk), 1)
        result_ids = [
            r["offering"]["id"] for r in res.json()["results"] if r["kind"] == "offering"
        ]
        self.assertEqual(result_ids.count(self.offering.pk), 1)

    def test_user_exact_appears_in_recommended(self):
        res = self._search("佐藤太郎", "all")
        data = res.json()
        users = [r for r in data["results"] if r["kind"] == "user"]
        self.assertTrue(
            any(u["user"]["display_name"] == "佐藤太郎" for u in users),
            data["results"][:5],
        )
        # 完全一致ユーザーは無関係人気投稿より前に来る
        first_user_idx = next(
            i
            for i, r in enumerate(data["results"])
            if r["kind"] == "user"
            and r["user"]["display_name"] == "佐藤太郎"
        )
        unrelated_idxs = [
            i
            for i, r in enumerate(data["results"])
            if r["kind"] == "post" and "無関係" in (r["post"].get("body") or "")
        ]
        self.assertEqual(unrelated_idxs, [])
        self.assertGreaterEqual(
            data["results"][first_user_idx]["relevance"], 1_000_000
        )

    def test_user_partial_appears_in_recommended(self):
        res = self._search("佐藤", "all")
        data = res.json()
        self.assertTrue(
            any(
                r["kind"] == "user" and "佐藤" in r["user"]["display_name"]
                for r in data["results"]
            )
        )

    def test_latest_only_hits_no_unrelated_popular(self):
        res = self._search("佐藤太郎", "latest")
        data = res.json()
        kinds = {r["kind"] for r in data["results"]}
        self.assertNotIn("user", kinds)
        self.assertNotIn("offering", kinds)
        self.assertFalse(
            any(
                r["kind"] == "post" and "無関係" in (r["post"].get("body") or "")
                for r in data["results"]
            )
        )
        # ヒットした投稿は含む
        self.assertTrue(
            any(
                r["kind"] == "post" and "佐藤太郎" in (r["post"].get("body") or "")
                for r in data["results"]
            )
        )

    def test_latest_excludes_user_and_offering_all_includes_them(self):
        latest = self._search("マーケティング論グローバル検索", "latest")
        latest_kinds = {r["kind"] for r in latest.json()["results"]}
        self.assertNotIn("user", latest_kinds)
        self.assertNotIn("offering", latest_kinds)

        recommended = self._search("マーケティング論グローバル検索", "all")
        rec_kinds = {r["kind"] for r in recommended.json()["results"]}
        self.assertIn("offering", rec_kinds)

        user_all = self._search("佐藤太郎", "all")
        self.assertTrue(
            any(r["kind"] == "user" for r in user_all.json()["results"])
        )
        user_latest = self._search("佐藤太郎", "latest")
        self.assertFalse(
            any(r["kind"] == "user" for r in user_latest.json()["results"])
        )

    def test_existing_product_and_user_tabs(self):
        products = self._search("マーケティング教科書", "products")
        self.assertGreaterEqual(products.json()["product_count"], 1)
        users = self._search("佐藤太郎", "users")
        self.assertGreaterEqual(users.json()["user_count"], 1)
        self.assertTrue(
            any(u["display_name"] == "佐藤太郎" for u in users.json()["users"])
        )

    def test_offering_card_has_review_stats(self):
        res = self._search("マーケティング論グローバル検索", "courses")
        offering = next(
            o for o in res.json()["offerings"] if o["id"] == self.offering.pk
        )
        self.assertIn("review_count", offering)
        self.assertGreaterEqual(offering["review_count"], 1)
        self.assertIn("review_overall", offering)
        self.assertIn("enrollment_count", offering)
        self.assertIn("day_label", offering)
        self.assertIn("period_label", offering)
