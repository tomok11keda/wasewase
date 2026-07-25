import logging

from .board_services import get_quotable_post
from .forms import TimelinePostForm
from .models import ContentReport
from .notification_services import get_unread_notification_count
from .inbox_services import get_unread_inbox_message_count

logger = logging.getLogger(__name__)


def timeline_compose(request):
    timeline_form = None
    quote_post = None
    if request.user.is_authenticated:
        timeline_form = TimelinePostForm()
        quote_param = request.GET.get("quote", "").strip()
        if quote_param.isdigit():
            quote_post = get_quotable_post(int(quote_param), request.user)
    return {
        "timeline_form": timeline_form,
        "quote_post": quote_post,
    }


def notification_badge(request):
    return {
        "unread_notifications": get_unread_notification_count(request.user),
    }


def dm_badge(request):
    user = getattr(request, "user", None)
    if user is None or not getattr(user, "is_authenticated", False):
        return {"unread_dm_messages": 0}

    try:
        unread_count = get_unread_inbox_message_count(user)
    except Exception as exc:
        # バッジ取得失敗でページ全体を 500 にしないための保険。
        logger.warning("dm_badge context failed: %s", exc)
        unread_count = 0

    return {
        "unread_dm_messages": unread_count,
    }


def ugc_safety(request):
    return {
        "report_reason_choices": ContentReport.Reason.choices,
        "ugc_report_enabled": request.user.is_authenticated,
    }


def ads_config(request):
    from .ads_services import (
        detect_is_native_app,
        get_infeed_ad_interval,
        is_ads_disabled,
        should_show_timeline_infeed_ads,
    )

    ads_disabled = is_ads_disabled()
    is_app = detect_is_native_app(request)
    return {
        "ads_disabled": ads_disabled,
        "is_native_app": is_app,
        # 将来 Web でも出す場合の出し分け用（現状アプリのみ True）
        "IS_APP": is_app,
        "infeed_ad_interval": get_infeed_ad_interval(),
        "show_timeline_infeed_ads": should_show_timeline_infeed_ads(request),
        "timeline_ad_offset": 0,
    }
