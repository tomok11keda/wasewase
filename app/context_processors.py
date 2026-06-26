from .board_services import get_quotable_post
from .forms import TimelinePostForm
from .models import ContentReport, Notification


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
    if request.user.is_authenticated:
        unread = Notification.objects.filter(
            recipient=request.user, is_read=False
        ).count()
    else:
        unread = 0
    return {"unread_notifications": unread}


def ugc_safety(request):
    return {
        "report_reason_choices": ContentReport.Reason.choices,
        "ugc_report_enabled": request.user.is_authenticated,
    }
