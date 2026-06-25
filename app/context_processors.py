from .models import ContentReport, Notification


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
