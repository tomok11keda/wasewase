"""広告表示制御（DISABLE_ADS / IS_APP / インフィード間隔）。"""

from __future__ import annotations

from django.conf import settings


def is_ads_disabled() -> bool:
    """審査・緊急停止用。True のとき広告 HTML / AdMob を一切出さない。"""
    return bool(getattr(settings, "WASE_DISABLE_ADS", False))


def detect_is_native_app(request) -> bool:
    """
    Capacitor ネイティブアプリかどうかを推定する。
    - User-Agent に Capacitor / アプリ名
    - Cookie wase_is_app=1（JS が起動時に付与）
    - クエリ ?is_app=1（検証用）
    Web 版は現状インフィードを出さず、将来の出し分け用にフラグだけ用意する。
    """
    if request is None:
        return False
    if request.GET.get("is_app") == "1":
        return True
    if request.COOKIES.get("wase_is_app") == "1":
        return True
    ua = (request.META.get("HTTP_USER_AGENT") or "").lower()
    if "capacitor" in ua:
        return True
    if "wasewase" in ua and ("iphone" in ua or "ipad" in ua or "android" in ua):
        return True
    return False


def get_infeed_ad_interval() -> int:
    interval = int(getattr(settings, "WASE_INFEED_AD_INTERVAL", 3) or 3)
    return max(1, interval)


def should_show_timeline_infeed_ads(request) -> bool:
    """
    タイムラインにインフィード広告カードを描画するか。
    DISABLE_ADS が ON なら必ず False（DOM ごと出さない）。
    現状はアプリ版のみ True（Web は準備のみ）。
    """
    if is_ads_disabled():
        return False
    if not getattr(settings, "WASE_INFEED_ADS_APP_ONLY", True):
        return True
    return detect_is_native_app(request)
