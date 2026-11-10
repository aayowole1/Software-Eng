from .models import Notification


def unread_notification_count(request):
    if not request.user.is_authenticated:
        return {"unread_notification_count": 0}
    count = Notification.objects.filter(user=request.user, is_read=False).count()
    return {"unread_notification_count": count}
