from .models import Notification


def notification_badge(request):
    if request.user.is_authenticated:
        unread = Notification.objects.filter(
            recipient=request.user, is_read=False
        ).count()
    else:
        unread = 0
    return {"unread_notifications": unread}
