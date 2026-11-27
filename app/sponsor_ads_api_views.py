"""スポンサー広告の表示・クリック計測 API（AdMob 非関連）。"""

from __future__ import annotations

import json

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_POST

from .sponsor_ads_services import (
    is_sponsor_ads_enabled,
    record_sponsor_event,
)


def _json_error(code: str, *, status: int = 400, **extra) -> JsonResponse:
    payload = {"ok": False, "error": code}
    payload.update(extra)
    return JsonResponse(payload, status=status)


def _parse_body(request: HttpRequest) -> dict:
    if request.content_type and "application/json" in request.content_type:
        try:
            data = json.loads(request.body.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            return {}
        return data if isinstance(data, dict) else {}
    return {
        "placement": request.POST.get("placement") or "",
    }


@login_required
@require_POST
def api_v1_sponsor_ad_impression(request: HttpRequest, pk: int) -> JsonResponse:
    """POST /api/v1/sponsor-ads/<pk>/impression/  body: {placement}"""
    if not is_sponsor_ads_enabled():
        return _json_error("sponsor_ads_disabled", status=404)
    data = _parse_body(request)
    placement = str(data.get("placement") or "").strip()
    if not placement:
        return _json_error("placement_required")
    row = record_sponsor_event(
        ad_id=pk, placement=placement, event="impression"
    )
    if row is None:
        return _json_error("not_found", status=404)
    return JsonResponse(
        {
            "ok": True,
            "ad_id": pk,
            "placement": placement,
            "impression_count": int(row.impression_count),
        }
    )


@login_required
@require_POST
def api_v1_sponsor_ad_click(request: HttpRequest, pk: int) -> JsonResponse:
    """POST /api/v1/sponsor-ads/<pk>/click/  body: {placement}"""
    if not is_sponsor_ads_enabled():
        return _json_error("sponsor_ads_disabled", status=404)
    data = _parse_body(request)
    placement = str(data.get("placement") or "").strip()
    if not placement:
        return _json_error("placement_required")
    row = record_sponsor_event(ad_id=pk, placement=placement, event="click")
    if row is None:
        return _json_error("not_found", status=404)
    return JsonResponse(
        {
            "ok": True,
            "ad_id": pk,
            "placement": placement,
            "click_count": int(row.click_count),
            "cta_url": row.ad.cta_url,
        }
    )
