"""手動運用スポンサー広告（AdMob とは別系統）。Feature Flag 既定 OFF。"""

from __future__ import annotations

from typing import Any

from django.conf import settings
from django.db.models import F, QuerySet
from django.http import HttpRequest
from django.utils import timezone

from .models import SponsoredAd, SponsoredAdPlacement

# ホームフィード: 通常投稿2件の直後に1枠
HOME_FEED_INSERT_AFTER = 2
HOME_FEED_LIMIT = 1
DISCOVER_FEATURED_LIMIT = 3

SERVED_PLACEMENTS = frozenset(
    {
        SponsoredAdPlacement.Placement.HOME_FEED,
        SponsoredAdPlacement.Placement.DISCOVER_FEATURED,
    }
)


def is_sponsor_ads_enabled() -> bool:
    """本番既定 False。ローカル検証時のみ True にする。"""
    return bool(getattr(settings, "WASE_SPONSOR_ADS_ENABLED", False))


def viewer_can_see_sponsor_ads(request: HttpRequest | None) -> bool:
    """認証済みユーザー（早稲田生）のみ。ゲスト／browse には出さない。"""
    if not is_sponsor_ads_enabled():
        return False
    if request is None:
        return False
    user = getattr(request, "user", None)
    return bool(user is not None and getattr(user, "is_authenticated", False))


def active_ads_queryset(placement: str) -> QuerySet[SponsoredAd]:
    now = timezone.now()
    return (
        SponsoredAd.objects.filter(
            is_active=True,
            starts_at__lte=now,
            ends_at__gt=now,
            placements__placement=placement,
            placements__is_enabled=True,
        )
        .distinct()
        .order_by("priority", "pk")
    )


def list_active_ads_for_placement(
    placement: str, *, limit: int
) -> list[SponsoredAd]:
    if placement not in SERVED_PLACEMENTS:
        return []
    return list(active_ads_queryset(placement)[: max(0, limit)])


def serialize_sponsor_ad(ad: SponsoredAd, *, placement: str) -> dict[str, Any]:
    image_url = None
    if ad.image:
        try:
            image_url = ad.image.url
        except ValueError:
            image_url = None
    return {
        "id": ad.pk,
        "kind": ad.kind,
        "badge_label": ad.badge_label,
        "sponsor_name": ad.sponsor_name,
        "title": ad.title,
        "description": ad.description or "",
        "image_url": image_url,
        "cta_url": ad.cta_url,
        "cta_label": ad.cta_label or "詳しく見る",
        "placement": placement,
    }


def home_feed_sponsor_payload(request: HttpRequest) -> dict[str, Any]:
    """タイムライン `ads.sponsor` 用。Flag OFF / 未ログイン / 在庫なしは enabled=false。"""
    if not viewer_can_see_sponsor_ads(request):
        return {
            "enabled": False,
            "insert_after": HOME_FEED_INSERT_AFTER,
            "items": [],
        }
    ads = list_active_ads_for_placement(
        SponsoredAdPlacement.Placement.HOME_FEED,
        limit=HOME_FEED_LIMIT,
    )
    items = [
        serialize_sponsor_ad(
            ad, placement=SponsoredAdPlacement.Placement.HOME_FEED
        )
        for ad in ads
    ]
    return {
        "enabled": bool(items),
        "insert_after": HOME_FEED_INSERT_AFTER,
        "items": items,
    }


def discover_featured_sponsor_items(request: HttpRequest) -> list[dict[str, Any]]:
    if not viewer_can_see_sponsor_ads(request):
        return []
    ads = list_active_ads_for_placement(
        SponsoredAdPlacement.Placement.DISCOVER_FEATURED,
        limit=DISCOVER_FEATURED_LIMIT,
    )
    return [
        serialize_sponsor_ad(
            ad, placement=SponsoredAdPlacement.Placement.DISCOVER_FEATURED
        )
        for ad in ads
    ]


def record_sponsor_event(
    *,
    ad_id: int,
    placement: str,
    event: str,
) -> SponsoredAdPlacement | None:
    """event: impression | click。掲載枠行が無い／無効なら None。"""
    if event not in ("impression", "click"):
        return None
    if placement not in {
        choice.value for choice in SponsoredAdPlacement.Placement
    }:
        return None
    now = timezone.now()
    row = (
        SponsoredAdPlacement.objects.select_related("ad")
        .filter(
            ad_id=ad_id,
            placement=placement,
            is_enabled=True,
            ad__is_active=True,
            ad__starts_at__lte=now,
            ad__ends_at__gt=now,
        )
        .first()
    )
    if row is None:
        return None
    if event == "impression":
        SponsoredAdPlacement.objects.filter(pk=row.pk).update(
            impression_count=F("impression_count") + 1
        )
    else:
        SponsoredAdPlacement.objects.filter(pk=row.pk).update(
            click_count=F("click_count") + 1
        )
    row.refresh_from_db(
        fields=["impression_count", "click_count", "updated_at"]
    )
    return row
