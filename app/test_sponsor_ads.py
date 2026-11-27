"""スポンサー広告 MVP — Flag OFF 回帰と枠別計測。"""

from __future__ import annotations

from datetime import timedelta

from django.core.exceptions import ValidationError
from django.test import Client, TestCase, override_settings
from django.utils import timezone

from .models import SponsoredAd, SponsoredAdPlacement, TimelinePost, User
from .sponsor_ads_services import (
    discover_featured_sponsor_items,
    home_feed_sponsor_payload,
    record_sponsor_event,
)


def _window(**extra):
    now = timezone.now()
    data = {
        "starts_at": now - timedelta(hours=1),
        "ends_at": now + timedelta(days=7),
        "is_active": True,
        "cta_url": "https://example.com/fictional-sponsor",
        "sponsor_name": "架空スポンサー株式会社",
        "title": "テスト用架空キャンペーン",
        "description": "本番には載せない架空広告です。",
        "kind": SponsoredAd.Kind.SPONSORED,
    }
    data.update(extra)
    return data


def _make_ad(*, placements: list[str], **extra) -> SponsoredAd:
    ad = SponsoredAd.objects.create(**_window(**extra))
    for key in placements:
        SponsoredAdPlacement.objects.create(ad=ad, placement=key, is_enabled=True)
    return ad


@override_settings(
    BROWSE_MODE_GATE_ENABLED=False,
    WASE_SPONSOR_ADS_ENABLED=True,
)
class SponsorAdsApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="sponsor-viewer@waseda.jp",
            password="test-pass-12345",
        )
        self.author = User.objects.create_user(
            email="sponsor-author@waseda.jp",
            password="test-pass-12345",
        )
        for i in range(3):
            TimelinePost.objects.create(
                author=self.author,
                body=f"post-{i}",
                like_count=0,
            )
        self.ad = _make_ad(
            placements=[
                SponsoredAdPlacement.Placement.HOME_FEED,
                SponsoredAdPlacement.Placement.DISCOVER_FEATURED,
            ]
        )
        self.client = Client()

    def test_feature_flag_off_hides_inventory(self):
        with override_settings(WASE_SPONSOR_ADS_ENABLED=False):
            self.client.force_login(self.user)
            timeline = self.client.get("/api/v1/timeline/").json()
            self.assertFalse(timeline["ads"]["sponsor"]["enabled"])
            self.assertEqual(timeline["ads"]["sponsor"]["items"], [])
            search = self.client.get("/api/v1/search/").json()
            self.assertEqual(search["discover"]["sponsor_ads"], [])

    def test_anonymous_never_sees_sponsor_ads(self):
        timeline = self.client.get("/api/v1/timeline/").json()
        self.assertFalse(timeline["ads"]["sponsor"]["enabled"])
        search = self.client.get("/api/v1/search/").json()
        self.assertEqual(search["discover"]["sponsor_ads"], [])

    def test_home_and_discover_both_serve_same_ad(self):
        self.client.force_login(self.user)
        timeline = self.client.get("/api/v1/timeline/").json()
        sponsor = timeline["ads"]["sponsor"]
        self.assertTrue(sponsor["enabled"])
        self.assertEqual(sponsor["insert_after"], 2)
        self.assertEqual(len(sponsor["items"]), 1)
        self.assertEqual(sponsor["items"][0]["id"], self.ad.pk)
        self.assertEqual(sponsor["items"][0]["placement"], "home_feed")
        self.assertEqual(sponsor["items"][0]["badge_label"], "スポンサー")

        search = self.client.get("/api/v1/search/").json()
        featured = search["discover"]["sponsor_ads"]
        self.assertEqual(len(featured), 1)
        self.assertEqual(featured[0]["id"], self.ad.pk)
        self.assertEqual(featured[0]["placement"], "discover_featured")

    def test_inactive_ad_hidden(self):
        self.ad.is_active = False
        self.ad.save(update_fields=["is_active"])
        self.client.force_login(self.user)
        timeline = self.client.get("/api/v1/timeline/").json()
        self.assertFalse(timeline["ads"]["sponsor"]["enabled"])
        search = self.client.get("/api/v1/search/").json()
        self.assertEqual(search["discover"]["sponsor_ads"], [])

    def test_load_more_does_not_repeat_sponsor(self):
        self.client.force_login(self.user)
        page2 = self.client.get("/api/v1/timeline/?offset=25").json()
        self.assertFalse(page2["ads"]["sponsor"]["enabled"])
        self.assertEqual(page2["ads"]["sponsor"]["items"], [])

    def test_impression_and_click_counted_per_placement(self):
        self.client.force_login(self.user)
        home = SponsoredAdPlacement.Placement.HOME_FEED
        discover = SponsoredAdPlacement.Placement.DISCOVER_FEATURED

        r1 = self.client.post(
            f"/api/v1/sponsor-ads/{self.ad.pk}/impression/",
            data={"placement": home},
            content_type="application/json",
        )
        self.assertEqual(r1.status_code, 200)
        r2 = self.client.post(
            f"/api/v1/sponsor-ads/{self.ad.pk}/impression/",
            data={"placement": discover},
            content_type="application/json",
        )
        self.assertEqual(r2.status_code, 200)
        r3 = self.client.post(
            f"/api/v1/sponsor-ads/{self.ad.pk}/click/",
            data={"placement": home},
            content_type="application/json",
        )
        self.assertEqual(r3.status_code, 200)

        home_row = SponsoredAdPlacement.objects.get(ad=self.ad, placement=home)
        discover_row = SponsoredAdPlacement.objects.get(
            ad=self.ad, placement=discover
        )
        self.assertEqual(home_row.impression_count, 1)
        self.assertEqual(home_row.click_count, 1)
        self.assertEqual(discover_row.impression_count, 1)
        self.assertEqual(discover_row.click_count, 0)

    def test_https_required_on_cta(self):
        ad = SponsoredAd(
            **_window(cta_url="http://insecure.example/"),
        )
        with self.assertRaises(ValidationError):
            ad.full_clean()

    def test_internal_promotion_badge(self):
        promo = _make_ad(
            placements=[SponsoredAdPlacement.Placement.DISCOVER_FEATURED],
            kind=SponsoredAd.Kind.INTERNAL_PROMOTION,
            sponsor_name="わせわせ運営",
            title="公式のお知らせ",
        )
        self.client.force_login(self.user)
        search = self.client.get("/api/v1/search/").json()
        labels = {row["id"]: row["badge_label"] for row in search["discover"]["sponsor_ads"]}
        self.assertEqual(labels[promo.pk], "公式からのお知らせ")
        self.assertEqual(labels[self.ad.pk], "スポンサー")

    def test_record_helpers_ignore_disabled_flag_paths(self):
        from django.test import RequestFactory

        request = RequestFactory().get("/")
        request.user = self.user
        with override_settings(WASE_SPONSOR_ADS_ENABLED=False):
            payload = home_feed_sponsor_payload(request)
            self.assertFalse(payload["enabled"])
            self.assertEqual(discover_featured_sponsor_items(request), [])


@override_settings(WASE_SPONSOR_ADS_ENABLED=False)
class SponsorAdsFlagOffRegressionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="flag-off@waseda.jp",
            password="test-pass-12345",
        )
        _make_ad(placements=[SponsoredAdPlacement.Placement.HOME_FEED])
        self.client = Client()
        self.client.force_login(self.user)

    def test_timeline_ads_meta_keeps_admob_shape(self):
        data = self.client.get("/api/v1/timeline/").json()
        self.assertIn("show_infeed", data["ads"])
        self.assertIn("interval", data["ads"])
        self.assertIn("disabled", data["ads"])
        self.assertFalse(data["ads"]["sponsor"]["enabled"])

    def test_tracking_endpoints_404_when_flag_off(self):
        res = self.client.post(
            "/api/v1/sponsor-ads/1/impression/",
            data={"placement": "home_feed"},
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 404)


class SponsorAdsRecordUnitTests(TestCase):
    def test_unknown_placement_ignored(self):
        ad = _make_ad(placements=[SponsoredAdPlacement.Placement.HOME_FEED])
        self.assertIsNone(
            record_sponsor_event(
                ad_id=ad.pk, placement="not_a_real_slot", event="impression"
            )
        )
