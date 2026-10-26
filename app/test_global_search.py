"""グローバル検索タブ（おすすめ / 最新 / 授業 / ユーザー / 商品）の拡張テスト。"""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase

from app.course_services import create_offering, enroll_user_in_offering, upsert_review
from app.models import Organization, Product, TimelinePost, UserProfile

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
        self.assertNotIn("organization", kinds)
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
        self.assertFalse(
            any(r["kind"] == "organization" for r in user_latest.json()["results"])
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


class GlobalSearchBlockFilterTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.alice = User.objects.create_user(
            email="block-alice@ex.com",
            password="pass12345",
            username="block_alice_us",
        )
        alice_profile, _ = UserProfile.objects.get_or_create(user=self.alice)
        alice_profile.name = "ブロック検証アリス"
        alice_profile.bio = "unique_alice_bio_token_xyz"
        alice_profile.department = "ブロック検証学部"
        alice_profile.save(update_fields=["name", "bio", "department"])

        self.bob = User.objects.create_user(
            email="block-bob@ex.com",
            password="pass12345",
            username="block_bob_us",
        )
        bob_profile, _ = UserProfile.objects.get_or_create(user=self.bob)
        bob_profile.name = "ブロック検証ボブ"
        bob_profile.save(update_fields=["name"])

        self.carol = User.objects.create_user(
            email="block-carol@ex.com",
            password="pass12345",
            username="block_carol_us",
        )
        carol_profile, _ = UserProfile.objects.get_or_create(user=self.carol)
        carol_profile.name = "ブロック検証キャロル"
        carol_profile.save(update_fields=["name"])

        from app.ugc_services import block_user

        block_user(self.alice, self.bob)

    def _search_as(self, user, q: str, tab: str):
        self.client.force_login(user)
        return self.client.get("/api/v1/search/", {"q": q, "tab": tab})

    def _user_ids(self, payload):
        return [u.get("id") for u in payload.get("users") or []]

    def _mixed_user_ids(self, payload):
        ids = []
        for row in payload.get("results") or []:
            if row.get("kind") == "user":
                user = row.get("user") or {}
                ids.append(user.get("id"))
        return ids

    def test_blocker_does_not_see_blocked_user_in_users_tab(self):
        res = self._search_as(self.alice, "block_bob_us", "users")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertNotIn(self.bob.pk, self._user_ids(data))
        self.assertEqual(data["user_count"], 0)

    def test_blocked_user_does_not_see_blocker_in_users_tab(self):
        res = self._search_as(self.bob, "block_alice_us", "users")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertNotIn(self.alice.pk, self._user_ids(data))
        self.assertEqual(data["user_count"], 0)

    def test_blocked_user_does_not_see_blocker_in_mixed_all_tab(self):
        res = self._search_as(self.bob, "block_alice_us", "all")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertNotIn(self.alice.pk, self._user_ids(data))
        self.assertNotIn(self.alice.pk, self._mixed_user_ids(data))
        self.assertEqual(data["user_count"], 0)

    def test_display_name_and_bio_search_also_hide_blocked_counterpart(self):
        by_name = self._search_as(self.bob, "ブロック検証アリス", "users")
        self.assertNotIn(self.alice.pk, self._user_ids(by_name.json()))
        by_bio = self._search_as(self.bob, "unique_alice_bio_token_xyz", "users")
        self.assertNotIn(self.alice.pk, self._user_ids(by_bio.json()))
        by_dept = self._search_as(self.bob, "ブロック検証学部", "users")
        self.assertNotIn(self.alice.pk, self._user_ids(by_dept.json()))
        partial = self._search_as(self.bob, "block_alice", "users")
        self.assertNotIn(self.alice.pk, self._user_ids(partial.json()))

    def test_unblocked_user_still_appears(self):
        res = self._search_as(self.alice, "block_carol_us", "users")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn(self.carol.pk, self._user_ids(data))
        self.assertGreaterEqual(data["user_count"], 1)


def _make_search_org(**kwargs) -> Organization:
    kwargs.setdefault("status", Organization.Status.ACTIVE)
    kwargs.setdefault("is_listed", True)
    kwargs.setdefault("is_verified", False)
    kwargs.setdefault("category", Organization.Category.CIRCLE)
    return Organization.objects.create(**kwargs)


class OrganizationSearchTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            email="org-search@ex.com",
            password="pass12345",
            username="org_search_user",
        )
        profile, _ = UserProfile.objects.get_or_create(user=self.user)
        profile.name = "検索ユーザー"
        profile.save(update_fields=["name"])
        self.client.force_login(self.user)

        self.exact = _make_search_org(
            name="わせわせサークル",
            slug="wase-circle",
            is_verified=True,
        )
        self.partial = _make_search_org(
            name="わせわせ研究会",
            slug="wase-kenkyukai",
        )
        self.contained = _make_search_org(
            name="公認わせわせサークル",
            slug="official-wase-circle",
        )
        self.english = _make_search_org(
            name="Waseda Festival",
            slug="waseda-festival",
        )
        self.unlisted = _make_search_org(
            name="わせわせサークル下書き掲載なし",
            slug="wase-unlisted",
            is_listed=False,
        )
        self.draft = _make_search_org(
            name="わせわせサークル下書き",
            slug="wase-draft",
            status=Organization.Status.DRAFT,
            is_listed=True,
        )
        self.suspended = _make_search_org(
            name="わせわせサークル停止",
            slug="wase-suspended",
            status=Organization.Status.SUSPENDED,
            is_listed=True,
        )
        self.unverified = _make_search_org(
            name="未確認サークルABC",
            slug="unverified-abc",
            is_verified=False,
        )

    def _search(self, q: str, tab: str):
        return self.client.get("/api/v1/search/", {"q": q, "tab": tab})

    def _org_ids(self, payload):
        return [row["id"] for row in payload.get("organizations") or []]

    def _mixed_org_ids(self, payload):
        ids = []
        for row in payload.get("results") or []:
            if row.get("kind") == "organization":
                ids.append((row.get("organization") or {}).get("id"))
        return ids

    def test_empty_query_includes_organization_keys(self):
        data = self._search("", "all").json()
        self.assertEqual(data["organizations"], [])
        self.assertEqual(data["organization_count"], 0)

    def test_exact_name_match_ranks_above_partial(self):
        data = self._search("わせわせサークル", "users").json()
        ids = self._org_ids(data)
        self.assertIn(self.exact.pk, ids)
        self.assertIn(self.contained.pk, ids)
        self.assertLess(ids.index(self.exact.pk), ids.index(self.contained.pk))
        mixed = self._mixed_org_ids(data)
        self.assertEqual(mixed[0], self.exact.pk)
        self.assertGreaterEqual(data["results"][0]["relevance"], 1_000_000)

    def test_prefix_match_beats_other_partial(self):
        prefix_org = _make_search_org(name="Wase Dance", slug="wase-dance")
        other = _make_search_org(name="Club Wase", slug="club-wase")
        data = self._search("Wase", "users").json()
        ids = self._org_ids(data)
        self.assertLess(ids.index(prefix_org.pk), ids.index(other.pk))

    def test_japanese_partial_match(self):
        data = self._search("わせわせ", "all").json()
        self.assertIn(self.exact.pk, self._org_ids(data))
        self.assertIn(self.partial.pk, self._org_ids(data))
        self.assertIn(self.exact.pk, self._mixed_org_ids(data))

    def test_english_name_and_case_insensitive_slug(self):
        by_name = self._search("Waseda Festival", "users").json()
        self.assertIn(self.english.pk, self._org_ids(by_name))
        by_partial = self._search("festival", "users").json()
        self.assertIn(self.english.pk, self._org_ids(by_partial))
        by_slug = self._search("WASE-CIRCLE", "users").json()
        self.assertIn(self.exact.pk, self._org_ids(by_slug))

    def test_zero_results(self):
        data = self._search("存在しない団体XYZ999", "users").json()
        self.assertEqual(data["organizations"], [])
        self.assertEqual(data["organization_count"], 0)
        self.assertFalse(any(r["kind"] == "organization" for r in data["results"]))

    def test_unlisted_draft_and_suspended_are_excluded(self):
        data = self._search("わせわせサークル", "users").json()
        ids = self._org_ids(data)
        self.assertNotIn(self.unlisted.pk, ids)
        self.assertNotIn(self.draft.pk, ids)
        self.assertNotIn(self.suspended.pk, ids)

    def test_unverified_listed_org_is_included_without_requiring_badge(self):
        data = self._search("未確認サークルABC", "users").json()
        self.assertIn(self.unverified.pk, self._org_ids(data))
        row = next(
            item
            for item in data["organizations"]
            if item["id"] == self.unverified.pk
        )
        self.assertFalse(row["is_verified"])
        self.assertEqual(row["slug"], "unverified-abc")

    def test_verified_org_payload_includes_badge_flag(self):
        data = self._search("わせわせサークル", "users").json()
        row = next(item for item in data["organizations"] if item["id"] == self.exact.pk)
        self.assertTrue(row["is_verified"])
        self.assertEqual(row["name"], "わせわせサークル")
        self.assertEqual(row["slug"], "wase-circle")

    def test_users_tab_keeps_personal_users_and_adds_orgs(self):
        data = self._search("検索ユーザー", "users").json()
        self.assertGreaterEqual(data["user_count"], 1)
        self.assertTrue(any(u["display_name"] == "検索ユーザー" for u in data["users"]))
        org_data = self._search("わせわせサークル", "users").json()
        kinds = {r["kind"] for r in org_data["results"]}
        self.assertIn("organization", kinds)
        self.assertNotIn("post", kinds)

    def test_all_tab_mixes_organizations_latest_does_not(self):
        all_data = self._search("わせわせサークル", "all").json()
        self.assertIn(self.exact.pk, self._mixed_org_ids(all_data))
        self.assertGreaterEqual(all_data["organization_count"], 1)
        latest = self._search("わせわせサークル", "latest").json()
        self.assertEqual(latest.get("organizations") or [], [])
        self.assertEqual(latest.get("organization_count") or 0, 0)
        self.assertNotIn("organization", {r["kind"] for r in latest["results"]})

    def test_existing_product_and_course_search_still_work(self):
        Product.objects.create(
            seller=self.user,
            name="団体検索回帰教科書",
            description="回帰",
            price=500,
            category="教科書",
        )
        products = self._search("団体検索回帰教科書", "products").json()
        self.assertGreaterEqual(products["product_count"], 1)
        users = self._search("org_search_user", "users").json()
        self.assertGreaterEqual(users["user_count"], 1)
