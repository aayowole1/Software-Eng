from .services import visible_notifications


def unread_notification_count(request):
    if not request.user.is_authenticated:
        return {"unread_notification_count": 0}
    count = visible_notifications(request.user).filter(is_read=False).count()
    return {"unread_notification_count": count}
